"""Assistant orchestration layer for wake, planning, confirmation, and execution."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Callable

from loguru import logger

from src.aradhya.paths import get_project_root
from src.aradhya.agent_loop import AgentLoop
from src.aradhya.assistant_indexer import DirectoryIndexManager
from src.aradhya.assistant_models import (
    AssistantPreferences,
    AssistantResponse,
    AssistantState,
    ExecutionResult,
    PlanKind,
    WakeSource,
    load_preferences,
)
from src.aradhya.assistant_planner import IntentPlanner
from src.aradhya.audit_logger import get_audit_logger
from src.aradhya.context_engine import ContextEngine
from src.aradhya.model_provider import TextModelProvider
from src.aradhya.session_manager import Session, SessionManager
from src.aradhya.assistant_system_tools import SystemToolbox
from src.aradhya.skills.skill_models import SkillRegistry
from src.aradhya.tools.browser_tools import ALL_BROWSER_TOOLS
from src.aradhya.tools.file_tools import ALL_FILE_TOOLS
from src.aradhya.tools.power_tools import ALL_POWER_TOOLS
from src.aradhya.tools.session_tools import ALL_SESSION_TOOLS
from src.aradhya.tools.shell_tools import ALL_SHELL_TOOLS
from src.aradhya.tools.system_tools import ALL_SYSTEM_TOOLS
from src.aradhya.tools.tool_registry import ToolRegistry
from src.aradhya.tools.runtime_policy import ToolRuntimePolicy
from src.aradhya.tools.vision_tools import ALL_VISION_TOOLS
from src.aradhya.tools.web_tools import ALL_WEB_TOOLS
from src.aradhya.tools.subagent_tools import ALL_SUBAGENT_TOOLS
from src.aradhya.tools.maintenance_tools import ALL_MAINTENANCE_TOOLS
from src.aradhya.tools.hardware_tools import ALL_HARDWARE_TOOLS
from src.aradhya.turn_context import build_turn_context
from src.aradhya.context_compressor import (
    TruncationPolicy,
    compact_history,
)
from src.aradhya.skills.skill_installer import ALL_SKILL_INSTALLER_TOOLS
from src.aradhya.learnings.learnings_engine import ALL_LEARNINGS_TOOLS, LearningsEngine
from src.aradhya.tools.scheduler_tool import ALL_SCHEDULER_TOOLS
from src.aradhya.tools.web_tools import set_active_network_policy
from src.aradhya.tools.vision_tools import set_active_vision_provider
from src.aradhya.hooks.hook_config import load_hooks
from src.aradhya.hooks.hook_engine import HookEngine, HookEvent
from src.aradhya.agents.agent_defs import AgentRegistry, load_agents
from src.aradhya.agents.subagent_runner import SubagentRunner
from src.aradhya.permission_rules import PermissionEngine, load_permissions
from src.aradhya.history_processors import default_pipeline
from src.aradhya.confirmation_gates import CliConfirmationGate
from src.aradhya.planning_workflow import (
    ComplexityDetector,
    PlanGenerator,
    TaskPlan,
    COMPLEXITY_THRESHOLD,
)

MAX_AGENT_CONTEXT_CHARS = 8000
MAX_AGENT_HISTORY_MESSAGES = 40
DEFAULT_HISTORY_TOKEN_LIMIT = 8000


class AradhyaAssistant:
    """Stateful assistant core aligned to the updated Aradhya product spec."""

    def __init__(
        self,
        preferences: AssistantPreferences,
        model_provider: TextModelProvider | None = None,
        now_provider: Callable[[], datetime] | None = None,
        skill_registry: SkillRegistry | None = None,
        session_manager: SessionManager | None = None,
        project_root: Path | None = None,
    ):
        self.preferences = preferences
        self.project_root = project_root or get_project_root()
        self.model_provider = model_provider
        self.now_provider = now_provider or datetime.now
        self.state = AssistantState()
        self.skill_registry = skill_registry
        self.index_manager = DirectoryIndexManager(
            preferences,
            now_provider=self.now_provider,
        )
        self.session_manager = session_manager or SessionManager(
            preferences.context_cache_dir / "sessions"
        )
        self.session_manager.load_or_create("main")
        self.context_engine = ContextEngine(
            preferences,
            index_manager=self.index_manager,
            skill_registry=skill_registry,
            session_manager=self.session_manager,
            learnings_engine=self._init_learnings_engine(),
        )
        self.toolbox = SystemToolbox(preferences, self.index_manager)
        self.planner = IntentPlanner(
            self.toolbox,
            self.now_provider,
            model_provider=model_provider,
            skill_registry=skill_registry,
        )
        self._confirmation_phrases = {
            self._normalize_phrase(phrase)
            for phrase in self.preferences.confirmation_phrases
        }

        # ── Parasite OS subsystems ────────────────────────────────────
        self.hook_engine = self._load_hook_engine()
        self.agent_registry = self._load_agent_registry()
        self.permission_engine = self._load_permission_engine()

        self.mcp_manager = self._load_mcp_manager()

        # ── Subagent orchestration ────────────────────────────────────
        self._init_subagent_runner()

        # ── LLM-backed session summarizer ─────────────────────────────
        self._wire_session_summarizer()

        # ── Planning workflow ─────────────────────────────────────────
        self.complexity_detector = ComplexityDetector(model_provider)
        self.plan_generator = (
            PlanGenerator(model_provider) if model_provider else None
        )
        self._active_plan: TaskPlan | None = None

    @classmethod
    def from_project_root(
        cls,
        project_root: Path | None = None,
        model_provider: TextModelProvider | None = None,
        skill_registry: SkillRegistry | None = None,
        session_manager: SessionManager | None = None,
    ) -> "AradhyaAssistant":
        root = project_root or get_project_root()
        return cls(
            load_preferences(root),
            model_provider=model_provider,
            skill_registry=skill_registry,
            session_manager=session_manager,
            project_root=root,
        )

    def _load_hook_engine(self) -> HookEngine:
        """Load hooks from user and project-level config."""
        try:
            engine = load_hooks(project_root=self.project_root)
            if engine.total_hooks > 0:
                logger.info(
                    "Parasite OS: {} hook(s) armed",
                    engine.total_hooks,
                )
                # Fire SessionStart hook
                engine.fire(HookEvent.SESSION_START, {
                    "session_name": "main",
                    "project_root": str(self.project_root),
                })
            return engine
        except Exception as exc:
            logger.warning("Hook engine failed to load (non-fatal): {}", exc)
            return HookEngine()

    def _load_agent_registry(self) -> AgentRegistry:
        """Load agent definitions from user and project directories."""
        try:
            return load_agents(project_root=self.project_root)
        except Exception as exc:
            logger.warning("Agent registry failed to load (non-fatal): {}", exc)
            return AgentRegistry()

    def _load_permission_engine(self) -> PermissionEngine:
        """Load permission rules from user and project config."""
        try:
            return load_permissions(project_root=self.project_root)
        except Exception as exc:
            logger.warning("Permission engine failed to load (non-fatal): {}", exc)
            return PermissionEngine()

    def _load_mcp_manager(self):
        try:
            from src.aradhya.mcp_client import MCPManager
        except ModuleNotFoundError as error:
            missing_name = error.name or ""
            if missing_name != "mcp" and not missing_name.startswith("mcp."):
                raise
            logger.warning("MCP support disabled because the mcp package is not installed.")
            return None

        manager = MCPManager()
        manager.load_from_profile(self.project_root / "core" / "memory" / "profile.json")
        return manager

    def _init_learnings_engine(self) -> LearningsEngine | None:
        """Initialise the learnings engine for cross-session knowledge."""
        try:
            return LearningsEngine(self.project_root)
        except Exception as exc:
            logger.debug("Learnings engine init failed (non-fatal): {}", exc)
            return None

    def _init_subagent_runner(self) -> None:
        """Set up the SubagentRunner with a loop factory.

        The factory creates a scoped AgentLoop for each subagent.  We
        only wire it if a model provider is available.
        """
        if self.model_provider is None:
            return

        try:
            runner = SubagentRunner.instance()

            # Capture 'self' for the closure
            assistant = self

            def _subagent_loop_factory(
                *,
                subagent_id: str,
                role: str,
                prompt: str,
                tools: list[str] | None = None,
                model: str = "",
                max_turns: int = 10,
                system_prompt: str = "",
            ) -> str:
                """Run a subagent's ReAct loop and return the final response."""
                policy = assistant._build_runtime_policy(mutation_granted=False)
                registry = assistant._build_tool_registry_from_policy(policy)

                # Build a minimal system prompt for the subagent
                sub_system = system_prompt or (
                    f"You are a subagent with the role '{role}'. "
                    f"Complete the following task and provide a clear, "
                    f"concise result. Use tools as needed but be efficient."
                )

                gate = CliConfirmationGate()  # subagents still respect gates
                loop = AgentLoop(
                    assistant.model_provider,
                    tool_executor=registry,
                    confirmation_gate=gate,
                    max_iterations=max_turns,
                    max_repeated_tool_calls=3,
                    hook_engine=assistant.hook_engine,
                    history_pipeline=default_pipeline(),
                    permission_engine=assistant.permission_engine,
                )

                turn = loop.run(prompt, sub_system, history=[])
                return turn.final_response.strip() or "[Subagent finished without output]"

            runner.set_loop_factory(_subagent_loop_factory)
            logger.info("SubagentRunner initialised with loop factory")

        except Exception as exc:
            logger.warning(
                "SubagentRunner init failed (non-fatal): {}", exc
            )

    def _wire_session_summarizer(self) -> None:
        """Wire an LLM-backed summarizer into SessionManager.

        The summarizer uses the active model provider to generate
        concise summaries of older messages during session compaction.
        Falls back gracefully if no model is available.
        """
        if self.model_provider is None:
            return

        provider = self.model_provider

        def _llm_summarizer(messages: list) -> str:
            """Summarize a list of Message objects using the LLM."""
            # Build a compact transcript of older messages
            lines = []
            for m in messages:
                role = getattr(m, "role", "unknown")
                content = getattr(m, "content", str(m))
                lines.append(f"[{role}] {content[:300]}")

            transcript = "\n".join(lines[-20:])  # last 20 messages max

            try:
                result = provider.chat(
                    messages=[{
                        "role": "user",
                        "content": (
                            "Summarize this conversation excerpt in 3-5 sentences. "
                            "Focus on: what the user asked, key decisions made, "
                            "tools used, and outcomes. Be concise.\n\n"
                            f"{transcript}"
                        ),
                    }],
                    system_prompt=(
                        "You are a conversation summarizer. Output ONLY "
                        "the summary, no preamble."
                    ),
                    tools=None,
                )
                return result.text.strip()
            except Exception as error:
                logger.debug("LLM summarizer failed: {}", error)
                # Fallback to extractive
                user_msgs = [
                    getattr(m, "content", "")[:120]
                    for m in messages
                    if getattr(m, "role", "") == "user"
                ]
                return "Earlier topics: " + "; ".join(user_msgs[-10:])

        self.session_manager.set_summarizer(_llm_summarizer)
        logger.info("LLM session summarizer wired")

    def handle_wake(self, source: WakeSource) -> AssistantResponse:
        self.state.is_awake = True
        self.state.pending_plan = None
        snapshot = None
        logger.info("Aradhya woke via {}", source.value)

        if self.preferences.directory_index_policy.refresh_on_wake:
            snapshot = self.index_manager.refresh_if_stale("wake")

        source_label = source.value.replace("_", " ")
        message = f"Aradhya is awake via {source_label}. Tell me what you want to do."
        if snapshot is not None:
            if snapshot.refreshed:
                message += " I refreshed the local directory index."
            else:
                message += " I reused the fresh local directory cache."

        return AssistantResponse(
            spoken_response=message,
            index_snapshot=snapshot,
        )

    def go_idle(self) -> AssistantResponse:
        self.state.is_awake = False
        self.state.pending_plan = None
        logger.info("Aradhya returned to idle state")
        return AssistantResponse(spoken_response="Aradhya is going idle.")

    def handle_transcript(
        self, transcript: str, stream_handler: Callable[..., str] | None = None,
        session_name: str | None = None,
    ) -> AssistantResponse:
        logger.info("Handling transcript: {}", transcript)
        if not self.state.is_awake:
            return AssistantResponse(
                spoken_response=(
                    "Wake me first with the floating icon or the Ctrl plus Win shortcut."
                ),
                transcript_echo=transcript,
            )

        normalized = self._normalize_phrase(transcript)
        if not normalized:
            return AssistantResponse(
                spoken_response="I did not catch any usable speech in that transcript.",
                transcript_echo=transcript,
            )

        if self.state.pending_plan and self._is_cancel_phrase(normalized):
            self.state.pending_plan = None
            logger.info("Canceled pending plan after transcript '{}'", transcript)
            return AssistantResponse(
                spoken_response="I canceled the pending task.",
                transcript_echo=transcript,
            )

        if self.state.pending_plan and self._is_confirmation_phrase(normalized):
            plan = self.state.pending_plan
            self.state.pending_plan = None
            # Execution happens only after an explicit confirmation phrase,
            # which is the main safety barrier in the current assistant.
            result = self._execute_plan(plan, stream_handler=stream_handler, session_name=session_name)
            logger.info("Executed confirmed plan {} with success={}", plan.kind, result.success)
            return AssistantResponse(
                spoken_response=result.message,
                transcript_echo=transcript,
                plan=plan,
                result=result,
            )

        replacing_pending = self.state.pending_plan is not None
        plan = self.planner.build_plan(transcript, self.state)
        self.state.pending_plan = None

        # Intercept complex agent tasks → upgrade to structured plans
        if plan.kind == PlanKind.AGENT_TASK and plan.ready:
            planned = self.maybe_plan_complex_request(transcript)
            if planned is not None:
                plan = planned
                self._active_plan = plan.metadata.get("task_plan")
                logger.info(
                    "Upgraded agent task to planned task (complexity {:.0%})",
                    plan.metadata.get("complexity_score", 0),
                )

        snapshot = None
        if (
            plan.uses_local_data
            and self.preferences.directory_index_policy.refresh_on_local_query
        ):
            snapshot = self.index_manager.last_snapshot

        if plan.kind == PlanKind.UNKNOWN or not plan.ready:
            logger.info("Planner returned non-executable plan {}", plan.kind)
            return AssistantResponse(
                spoken_response=plan.summary,
                transcript_echo=transcript,
                plan=plan,
                index_snapshot=snapshot,
            )

        if plan.requires_confirmation:
            # The pending plan is stored here so the next "yes proceed" can
            # execute exactly this action and not a newer transcript.
            self.state.pending_plan = plan
            logger.info("Stored pending plan {} awaiting confirmation", plan.kind)
            prefix = "I replaced the earlier pending task. " if replacing_pending else ""
            return AssistantResponse(
                spoken_response=(
                    f"{prefix}{plan.summary} Say 'yes proceed' when you want me "
                    "to execute it."
                ),
                transcript_echo=transcript,
                plan=plan,
                awaiting_confirmation=True,
                index_snapshot=snapshot,
            )

        result = self._execute_plan(plan, stream_handler=stream_handler, session_name=session_name)
        logger.info("Executed immediate plan {} with success={}", plan.kind, result.success)
        return AssistantResponse(
            spoken_response=result.message,
            transcript_echo=transcript,
            plan=plan,
            result=result,
            index_snapshot=snapshot,
        )

    def _normalize_phrase(self, phrase: str) -> str:
        return " ".join(re.findall(r"[a-z0-9]+", phrase.lower()))

    def _is_confirmation_phrase(self, normalized: str) -> bool:
        return normalized in self._confirmation_phrases

    def _is_cancel_phrase(self, normalized: str) -> bool:
        return normalized in {"cancel", "stop", "never mind", "nevermind", "no cancel"}

    def _execute_plan(
        self, plan, stream_handler: Callable[..., str] | None = None,
        session_name: str | None = None,
    ) -> ExecutionResult:
        if plan.kind == PlanKind.AGENT_TASK:
            return self._execute_agent_task(plan, stream_handler=stream_handler, session_name=session_name)
        if plan.kind == PlanKind.PLANNED_TASK:
            return self._execute_planned_task(plan, stream_handler=stream_handler, session_name=session_name)
        if plan.kind == PlanKind.GENERAL_CHAT:
            return self._execute_general_chat(plan, stream_handler=stream_handler, session_name=session_name)
        return self.toolbox.execute(plan, self.state)

    def _execute_general_chat(
        self, plan, stream_handler: Callable[..., str] | None = None,
        session_name: str | None = None,
    ) -> ExecutionResult:
        if self.model_provider is None:
            return ExecutionResult(False, "No model provider configured.")

        request = str(plan.metadata.get("request") or "").strip()
        if not request:
            return ExecutionResult(False, "Chat plan missing request.")

        session = self.session_manager.active_session or self.session_manager.load_or_create(session_name or "main")
        history = self._build_agent_history(session)

        try:
            # Bypass tool registry completely for fast response
            messages = list(history)
            messages.append({"role": "user", "content": request})

            system_prompt = (
                "You are Aradhya, a concise local assistant. "
                "Answer the user directly without using any system tools."
            )

            if stream_handler is not None and hasattr(self.model_provider, "chat_stream"):
                stream = self.model_provider.chat_stream(
                    messages=messages,
                    system_prompt=system_prompt,
                )
                response_text = stream_handler(stream)
            else:
                chat_result = self.model_provider.chat(
                    messages=messages,
                    system_prompt=system_prompt,
                    tools=None,  # No tools injected!
                )
                response_text = chat_result.text

            session.add_message("user", request, plan_kind=PlanKind.GENERAL_CHAT.value)
            session.add_message("assistant", response_text, plan_kind=PlanKind.GENERAL_CHAT.value)
            self.session_manager.save(session)

            return ExecutionResult(True, response_text)

        except Exception as e:
            return ExecutionResult(False, f"[Chat Error: {e}]")

    def _execute_agent_task(
        self, plan, stream_handler: Callable[..., str] | None = None,
        session_name: str | None = None,
    ) -> ExecutionResult:
        if self.model_provider is None:
            return ExecutionResult(
                False,
                "The model-driven agent path needs a configured backend model.",
            )

        request = str(plan.metadata.get("request") or "").strip()
        if not request:
            return ExecutionResult(False, "The agent task did not include a request.")

        # Gap G: named session per channel (NanoClaw pattern)
        session = self.session_manager.active_session or self.session_manager.load_or_create(session_name or "main")
        history = self._build_agent_history(session)

        # Build runtime policy and turn context (Codex-inspired)
        policy = self._build_runtime_policy(mutation_granted=True)
        turn_ctx = build_turn_context(
            policy=policy,
            session_id=session.id,
        )

        # Log turn start via event-sourced audit
        audit = get_audit_logger()
        audit.set_session_id(session.id)
        audit.log_turn_start(
            user_message=request,
            turn_id=turn_ctx.turn_id,
            context=turn_ctx.to_dict(),
        )

        system_prompt = self._build_agent_system_prompt(session, turn_ctx, user_prompt=request)
        registry = self._build_tool_registry_from_policy(policy)

        # ── Gap A: CLI confirmation gate (now a reusable typed class) ──
        gate = CliConfirmationGate()

        loop = AgentLoop(
            self.model_provider,
            tool_executor=registry,
            confirmation_gate=gate,
            max_iterations=10,
            max_repeated_tool_calls=3,
            hook_engine=self.hook_engine,
            history_pipeline=default_pipeline(),
            permission_engine=self.permission_engine,
        )

        # Gap E: set active network policy so web_fetch/web_search can check it
        set_active_network_policy(policy)
        # P1-3: expose the model provider to describe_screen for this turn
        set_active_vision_provider(self.model_provider)
        try:
            turn = loop.run(request, system_prompt, history=history, stream_handler=stream_handler)
        finally:
            set_active_network_policy(None)  # always clear after turn
            set_active_vision_provider(None)
        final_text = turn.final_response.strip() or "The agent stopped without a final answer."

        # Log turn end
        success = not final_text.startswith("[Error") and not final_text.startswith(
            "[Agent loop"
        )
        audit.log_turn_end(
            turn_id=turn_ctx.turn_id,
            iterations=turn.iterations,
            tool_calls_count=len(turn.tool_calls_made),
            success=success,
            final_response_preview=final_text,
        )

        self.session_manager.append_message(
            "user",
            request,
            session=session,
            plan_kind=PlanKind.AGENT_TASK.value,
        )
        self.session_manager.append_message(
            "assistant",
            final_text,
            session=session,
            plan_kind=PlanKind.AGENT_TASK.value,
            iterations=turn.iterations,
            tool_calls=[tool.name for tool in turn.tool_calls_made],
            tool_success=[result.success for result in turn.tool_results],
        )
        self.session_manager.compact_session(session)

        failed_tool_names = tuple(
            result.name for result in turn.tool_results if not result.success
        )
        return ExecutionResult(
            success=success,
            message=final_text,
            artifacts=failed_tool_names,
        )

    def _execute_planned_task(
        self, plan, stream_handler: Callable[..., str] | None = None,
        session_name: str | None = None,
    ) -> ExecutionResult:
        """Execute a structured multi-step plan.

        Each step is run through the agent loop with a focused prompt.
        Progress is tracked on the ``TaskPlan`` object and reported
        to the user at the end.
        """
        task_plan: TaskPlan | None = plan.metadata.get("task_plan")
        if task_plan is None:
            return ExecutionResult(
                False,
                "No task plan found in plan metadata.",
            )

        if self.model_provider is None:
            return ExecutionResult(
                False,
                "The planned task path needs a configured backend model.",
            )

        session = (
            self.session_manager.active_session
            or self.session_manager.load_or_create(session_name or "main")
        )

        step_results: list[str] = []

        while not task_plan.is_complete:
            step = task_plan.get_next_step()
            if step is None:
                break

            step.status = step.status.__class__("in_progress")
            step_prompt = (
                f"You are executing step {step.index + 1} of a {task_plan.total_steps}-step plan.\n"
                f"Goal: {task_plan.goal}\n"
                f"Current step: {step.title}\n"
                f"Instructions: {step.description}\n\n"
                f"Complete this step and provide a clear result summary."
            )

            logger.info(
                "Executing plan step {}/{}: {}",
                step.index + 1,
                task_plan.total_steps,
                step.title,
            )

            try:
                # Build a single-step agent task and execute it
                step_plan = PlanAction(
                    kind=PlanKind.AGENT_TASK,
                    summary=step.title,
                    requires_confirmation=False,
                    metadata={"request": step_prompt},
                )
                step_result = self._execute_agent_task(
                    step_plan,
                    stream_handler=stream_handler,
                    session_name=session_name,
                )
                task_plan.advance(
                    result=step_result.message[:500],
                    success=step_result.success,
                )
                step_results.append(
                    f"**Step {step.index + 1} ({step.title})**: "
                    f"{'✅' if step_result.success else '❌'} "
                    f"{step_result.message[:200]}"
                )
            except Exception as exc:
                task_plan.advance(result=str(exc), success=False)
                step_results.append(
                    f"**Step {step.index + 1} ({step.title})**: ❌ Error: {exc}"
                )
                logger.error("Plan step {} failed: {}", step.index + 1, exc)

        # Build consolidated report
        report_lines = [
            f"📋 **Plan completed: {task_plan.goal}**",
            f"Progress: {task_plan.progress_summary}",
            "",
            *step_results,
        ]
        report = "\n".join(report_lines)

        self._active_plan = None  # Clear the plan
        return ExecutionResult(
            success=task_plan.completed_steps == task_plan.total_steps,
            message=report,
        )

    def maybe_plan_complex_request(
        self, request: str
    ) -> PlanAction | None:
        """Check if a request is complex enough to warrant planning.

        Returns a ``PLANNED_TASK`` PlanAction if planning is warranted,
        or ``None`` if the request should proceed as a normal agent task.
        """
        if self.plan_generator is None:
            return None

        score, reasoning = self.complexity_detector.score(request)
        logger.debug(
            "Complexity score for '{}': {:.2f} ({})",
            request[:60], score, reasoning,
        )

        if score < COMPLEXITY_THRESHOLD:
            return None

        # Generate a structured plan
        task_plan = self.plan_generator.generate(request, score)

        return PlanAction(
            kind=PlanKind.PLANNED_TASK,
            summary=task_plan.format_for_user(),
            requires_confirmation=True,
            metadata={
                "request": request,
                "task_plan": task_plan,
                "complexity_score": score,
                "complexity_reasoning": reasoning,
            },
        )

    def _build_runtime_policy(self, *, mutation_granted: bool) -> ToolRuntimePolicy:
        """Build a ToolRuntimePolicy from current preferences."""
        return ToolRuntimePolicy(
            allowed_roots=self.preferences.user_roots,
            live_execution_enabled=self.preferences.allow_live_execution,
            mutation_granted=mutation_granted,
        )

    def _build_tool_registry_from_policy(self, policy: ToolRuntimePolicy) -> ToolRegistry:
        """Build a tool registry from an existing policy."""
        registry = ToolRegistry(policy=policy)
        for tool in (
            *ALL_FILE_TOOLS,
            *ALL_SHELL_TOOLS,
            *ALL_SYSTEM_TOOLS,
            *ALL_SESSION_TOOLS,
            *ALL_WEB_TOOLS,
            *ALL_POWER_TOOLS,
            *ALL_BROWSER_TOOLS,
            *ALL_VISION_TOOLS,
            *ALL_SKILL_INSTALLER_TOOLS,
            *ALL_LEARNINGS_TOOLS,
            *ALL_SCHEDULER_TOOLS,   # Gap F: expose scheduler to model
            *ALL_SUBAGENT_TOOLS,    # Subagent orchestration tools
            *ALL_MAINTENANCE_TOOLS,  # P1-2: read-only disk-usage analysis
            *ALL_HARDWARE_TOOLS,     # P1-6: hardware profile + model recommendations
        ):
            registry.register_function(tool)

        if self.mcp_manager is not None:
            self.mcp_manager.connect_and_register_tools(registry)

        return registry

    def _build_tool_registry(self, *, mutation_granted: bool) -> ToolRegistry:
        """Build a tool registry (backward compatible entry point)."""
        policy = self._build_runtime_policy(mutation_granted=mutation_granted)
        return self._build_tool_registry_from_policy(policy)

    def _build_agent_system_prompt(
        self,
        session: Session | None,
        turn_ctx: "object | None" = None,
        user_prompt: str = "",
    ) -> str:
        parts = [
            (
                "You are Aradhya, a local model-driven Windows assistant. "
                "Use tools to inspect real state before making claims. "
                "Do not invent tool results. Stop when the task is complete and "
                "answer with a concise final summary."
            ),
            (
                "Reads, directory listings, searches, web fetches, and web searches "
                "may run automatically. Shell commands, launches, clipboard writes, "
                "and file writes are controlled by runtime policy."
            ),
        ]

        parts.append(self._mentor_mode_block())

        # Inject per-turn context (Codex-style permission matrix)
        if turn_ctx is not None and hasattr(turn_ctx, "to_prompt_block"):
            parts.append(turn_ctx.to_prompt_block())
        elif not self.preferences.allow_live_execution:
            parts.append(
                "Current policy: allow_live_execution is false, so machine-changing "
                "tools will be blocked even after task confirmation. Explain policy "
                "blocks plainly and continue with read-only work where useful."
            )

        try:
            parts.append(self.context_engine.build_snapshot(session).to_prompt_block())
        except Exception as error:
            logger.debug("Context snapshot failed: {}", error)

        user_context = self._read_user_context()
        if user_context:
            parts.append(user_context)

        if self.skill_registry is not None:
            # Inject only the skills whose intents match this turn's request,
            # so the prompt stays focused instead of carrying every skill.
            skill_instructions = self.skill_registry.instructions_for_prompt(user_prompt)
            if skill_instructions:
                parts.append("[Active skills]\n" + skill_instructions[:MAX_AGENT_CONTEXT_CHARS])

        return "\n\n".join(part for part in parts if part.strip())

    MENTOR_MODES = ("do", "teach")

    def set_mentor_mode(self, mode: str, skill_level: str | None = None) -> str:
        """Set mentor mode to 'do' or 'teach' (optionally a skill level).

        Returns a short human-readable confirmation. Raises ValueError for an
        unknown mode so callers can surface a usage hint.
        """
        normalized = (mode or "").strip().lower()
        if normalized not in self.MENTOR_MODES:
            raise ValueError(
                f"Unknown mentor mode '{mode}'. Use one of: {', '.join(self.MENTOR_MODES)}."
            )
        self.state.mentor_mode = normalized
        if skill_level is not None:
            self.state.skill_level = skill_level.strip().lower()

        if normalized == "teach":
            detail = "I'll guide you step by step and let you do each action yourself."
        else:
            detail = "I'll carry out tasks for you directly (still policy-gated)."
        level = f" (skill level: {self.state.skill_level})" if self.state.skill_level else ""
        return f"Mentor mode is now '{normalized}'{level}. {detail}"

    def _mentor_mode_block(self) -> str:
        """Return the do/teach pedagogy instructions for the agent prompt."""
        level = self.state.skill_level
        level_line = (
            f" The user's self-described skill level is '{level}'; pace accordingly."
            if level
            else ""
        )
        if self.state.mentor_mode == "teach":
            return (
                "Mentor mode: TEACH. Do NOT perform actions for the user. Instead, "
                "guide them: explain what to do, one small step at a time, and wait "
                "for them to do it. Use read-only tools to see current state and "
                "verify their progress, but let the user click, type, and decide. "
                "Explain the why, not just the how, and check understanding before "
                "moving on." + level_line
            )
        return (
            "Mentor mode: DO. Carry out the task for the user directly, using tools "
            "as needed (machine-changing actions stay policy-gated). Be concise; "
            "report what you did and the outcome." + level_line
        )

    def _read_user_context(self) -> str:
        context_dir = self.project_root / "core" / "memory" / "user_context"
        parts: list[str] = []
        for filename in ("rules.md", "notes.md"):
            path = context_dir / filename
            if not path.is_file():
                continue
            try:
                content = path.read_text(encoding="utf-8").strip()
            except OSError:
                continue
            if content:
                parts.append(f"[{filename}]\n{content[:MAX_AGENT_CONTEXT_CHARS]}")
        return "\n\n".join(parts)

    def _build_agent_history(self, session: Session | None) -> list[dict[str, str]]:
        """Build agent history with token-aware context compression.

        Applies the Codex-inspired truncation policy: if the history
        exceeds the token budget, older messages are summarized into
        a compact system message.
        """
        if session is None:
            return []

        # Collect raw messages
        raw_messages: list[dict[str, str]] = []
        for message in session.recent_messages(MAX_AGENT_HISTORY_MESSAGES):
            role = message.role
            if role == "summary":
                role = "system"
            if role not in {"system", "user", "assistant"}:
                continue
            if not message.content.strip():
                continue
            raw_messages.append({"role": role, "content": message.content})

        if not raw_messages:
            return []

        # Apply token-aware compaction
        policy = TruncationPolicy(
            mode="tokens",
            limit=DEFAULT_HISTORY_TOKEN_LIMIT,
        )
        compacted, result = compact_history(raw_messages, policy=policy)

        if result.compacted:
            logger.info(
                "History compacted: {} → {} messages ({} → {} est. tokens)",
                result.original_messages,
                result.kept_messages + 1,
                result.estimated_tokens_before,
                result.estimated_tokens_after,
            )
            # ── Gap B: emit 'compacted' audit event so the trail is never broken ──
            try:
                get_audit_logger().log_event(
                    "compacted",
                    {
                        "original_messages": result.original_messages,
                        "kept_messages": result.kept_messages,
                        "original_tokens": result.estimated_tokens_before,
                        "compacted_tokens": result.estimated_tokens_after,
                        "strategy": "extractive",
                    },
                )
            except Exception:  # pragma: no cover
                pass  # audit must never crash the agent

        return compacted
