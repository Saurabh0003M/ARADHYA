"""Assistant orchestration layer for wake, planning, confirmation, and execution."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Callable

from loguru import logger

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
from src.aradhya.context_engine import ContextEngine
from src.aradhya.model_provider import TextModelProvider
from src.aradhya.session_manager import Session, SessionManager
from src.aradhya.assistant_system_tools import SystemToolbox
from src.aradhya.skills.skill_models import SkillRegistry
from src.aradhya.tools.file_tools import ALL_FILE_TOOLS
from src.aradhya.tools.session_tools import ALL_SESSION_TOOLS
from src.aradhya.tools.shell_tools import ALL_SHELL_TOOLS
from src.aradhya.tools.system_tools import ALL_SYSTEM_TOOLS
from src.aradhya.tools.tool_registry import ToolRegistry
from src.aradhya.tools.runtime_policy import ToolRuntimePolicy
from src.aradhya.tools.web_tools import ALL_WEB_TOOLS

MAX_AGENT_CONTEXT_CHARS = 8000
MAX_AGENT_HISTORY_MESSAGES = 20


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
        self.project_root = project_root or Path(__file__).resolve().parents[2]
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

    @classmethod
    def from_project_root(
        cls,
        project_root: Path | None = None,
        model_provider: TextModelProvider | None = None,
        skill_registry: SkillRegistry | None = None,
        session_manager: SessionManager | None = None,
    ) -> "AradhyaAssistant":
        root = project_root or Path(__file__).resolve().parents[2]
        return cls(
            load_preferences(root),
            model_provider=model_provider,
            skill_registry=skill_registry,
            session_manager=session_manager,
            project_root=root,
        )

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

    def handle_transcript(self, transcript: str) -> AssistantResponse:
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
            result = self._execute_plan(plan)
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

        result = self._execute_plan(plan)
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

    def _execute_plan(self, plan) -> ExecutionResult:
        if plan.kind == PlanKind.AGENT_TASK:
            return self._execute_agent_task(plan)
        return self.toolbox.execute(plan, self.state)

    def _execute_agent_task(self, plan) -> ExecutionResult:
        if self.model_provider is None:
            return ExecutionResult(
                False,
                "The model-driven agent path needs a configured backend model.",
            )

        request = str(plan.metadata.get("request") or "").strip()
        if not request:
            return ExecutionResult(False, "The agent task did not include a request.")

        session = self.session_manager.active_session or self.session_manager.load_or_create("main")
        history = self._build_agent_history(session)
        system_prompt = self._build_agent_system_prompt(session)
        registry = self._build_tool_registry(mutation_granted=True)
        loop = AgentLoop(
            self.model_provider,
            tool_executor=registry,
            max_iterations=10,
            max_repeated_tool_calls=3,
        )

        turn = loop.run(request, system_prompt, history=history)
        final_text = turn.final_response.strip() or "The agent stopped without a final answer."

        session.add_message(
            "user",
            request,
            plan_kind=PlanKind.AGENT_TASK.value,
        )
        session.add_message(
            "assistant",
            final_text,
            plan_kind=PlanKind.AGENT_TASK.value,
            iterations=turn.iterations,
            tool_calls=[tool.name for tool in turn.tool_calls_made],
            tool_success=[result.success for result in turn.tool_results],
        )
        self.session_manager.save(session)
        self.session_manager.compact_session(session)

        failed_tool_names = tuple(
            result.name for result in turn.tool_results if not result.success
        )
        success = not final_text.startswith("[Error") and not final_text.startswith(
            "[Agent loop"
        )
        return ExecutionResult(
            success=success,
            message=final_text,
            artifacts=failed_tool_names,
        )

    def _build_tool_registry(self, *, mutation_granted: bool) -> ToolRegistry:
        policy = ToolRuntimePolicy(
            allowed_roots=self.preferences.user_roots,
            live_execution_enabled=self.preferences.allow_live_execution,
            mutation_granted=mutation_granted,
        )
        registry = ToolRegistry(policy=policy)
        for tool in (
            *ALL_FILE_TOOLS,
            *ALL_SHELL_TOOLS,
            *ALL_SYSTEM_TOOLS,
            *ALL_SESSION_TOOLS,
            *ALL_WEB_TOOLS,
        ):
            registry.register_function(tool)
        return registry

    def _build_agent_system_prompt(self, session: Session | None) -> str:
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
        if not self.preferences.allow_live_execution:
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
            skill_instructions = self.skill_registry.active_instructions()
            if skill_instructions:
                parts.append("[Active skills]\n" + skill_instructions[:MAX_AGENT_CONTEXT_CHARS])

        return "\n\n".join(part for part in parts if part.strip())

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
        if session is None:
            return []

        history: list[dict[str, str]] = []
        for message in session.recent_messages(MAX_AGENT_HISTORY_MESSAGES):
            role = message.role
            if role == "summary":
                role = "system"
            if role not in {"system", "user", "assistant"}:
                continue
            if not message.content.strip():
                continue
            history.append({"role": role, "content": message.content})
        return history
