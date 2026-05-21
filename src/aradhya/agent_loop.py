"""Structured agent execution loop for multi-step tool-calling workflows.

Inspired by OpenClaw's agent loop, this module implements a proper agentic
cycle:  prompt → model → tool calls → execute → feed results → loop until
the model returns a final text response.

The loop respects the confirmation gate for dangerous operations and supports
streaming responses.  Hooks (PreToolUse / PostToolUse) provide event-driven
gates that can intercept, modify, or block any tool call.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Protocol, TYPE_CHECKING

from loguru import logger

from src.aradhya.audit_logger import get_audit_logger
# NOTE: approved_rules is imported lazily inside _execute_with_gate to avoid
# the circular import chain: agent_loop -> tools/__init__ -> tool_registry -> agent_loop

from src.aradhya.utils.json_extractor import (
    JSONExtractionError,
    extract_json_from_llm_response,
)
from src.aradhya.model_provider import ModelChatResult, ModelResult, ModelToolCall

if TYPE_CHECKING:
    from src.aradhya.hooks.hook_engine import HookEngine
    from src.aradhya.history_processors import HistoryProcessorPipeline


class ThinkingLevel(Enum):
    """Controls how much reasoning the model should expose."""
    LOW = auto()
    MEDIUM = auto()
    HIGH = auto()


@dataclass
class ToolCall:
    """A single tool call requested by the model."""
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    id: str = ""


@dataclass
class ToolResult:
    """The result of executing a tool call."""
    tool_call_id: str
    name: str
    output: str
    success: bool = True
    requires_confirmation: bool = False


@dataclass
class AgentTurn:
    """A complete turn in the agent loop (may span multiple tool calls)."""
    user_message: str
    system_prompt: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    tool_calls_made: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    final_response: str = ""
    iterations: int = 0
    thinking_level: ThinkingLevel = ThinkingLevel.MEDIUM


class ToolExecutor(Protocol):
    """Protocol for executing tool calls."""
    def execute_tool(
        self, name: str, arguments: dict[str, Any], tool_call_id: str = ""
    ) -> ToolResult: ...

    def list_tools(self) -> list[dict[str, Any]]: ...


class AgentLoop:
    """Orchestrates the prompt → tool call → execute → respond cycle.

    Parameters
    ----------
    model_provider
        A text model provider that supports chat completions.
    tool_executor
        An object that can execute named tool calls and return results.
    confirmation_gate
        An optional callback that is invoked when a tool call requires
        user confirmation.  It receives the tool name and arguments and
        returns True if the user approves.
    max_iterations
        Safety limit on the number of tool-call rounds per turn.
    """

    def __init__(
        self,
        model_provider: Any,
        tool_executor: ToolExecutor | None = None,
        confirmation_gate: Callable[[str, dict[str, Any]], bool] | None = None,
        max_iterations: int = 10,
        max_repeated_tool_calls: int = 3,
        turn_token_budget: int = 6000,
        hook_engine: HookEngine | None = None,
        history_pipeline: HistoryProcessorPipeline | None = None,
    ) -> None:
        self.model_provider = model_provider
        self.tool_executor = tool_executor
        self.confirmation_gate = confirmation_gate
        self.max_iterations = max_iterations
        self.max_repeated_tool_calls = max_repeated_tool_calls
        self.turn_token_budget = turn_token_budget
        self.hook_engine = hook_engine
        self.history_pipeline = history_pipeline

    def run(
        self,
        user_message: str,
        system_prompt: str,
        history: list[dict[str, Any]] | None = None,
        thinking: ThinkingLevel = ThinkingLevel.MEDIUM,
        stream_handler: Callable[..., str] | None = None,
    ) -> AgentTurn:
        """Execute a full agent turn.

        Returns an ``AgentTurn`` with the final response text and all
        intermediate tool calls/results.
        """

        turn = AgentTurn(
            user_message=user_message,
            system_prompt=system_prompt,
            thinking_level=thinking,
        )

        # Build initial message list
        messages: list[dict[str, Any]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        turn.messages = messages

        # Per-turn token accumulator — prevents single-turn context overflow
        # from accumulating huge tool outputs across many iterations.
        accumulated_result_tokens = 0

        for iteration in range(self.max_iterations):
            turn.iterations = iteration + 1

            try:
                response = self._call_model(messages, stream_handler=stream_handler)
            except Exception as error:
                logger.error("Agent loop model call failed: {}", error)
                turn.final_response = f"[Error calling model: {error}]"
                break

            # Check if model returned tool calls
            tool_calls = self._extract_tool_calls(response)

            if not tool_calls:
                # Model returned a final text response
                turn.final_response = self._extract_text(response)
                break

            # Execute tool calls
            for tool_call in tool_calls:
                if self._is_repeated_tool_call(turn.tool_calls_made, tool_call):
                    turn.final_response = (
                        "[Agent loop stopped because the model repeated the same "
                        f"tool call too many times: {tool_call.name}]"
                    )
                    logger.warning(
                        "Agent loop stopped on repeated tool call {} with args {}",
                        tool_call.name,
                        tool_call.arguments,
                    )
                    return turn

                turn.tool_calls_made.append(tool_call)

                if self.tool_executor is None:
                    result = ToolResult(
                        tool_call_id=tool_call.id,
                        name=tool_call.name,
                        output=f"[Tool '{tool_call.name}' not available — no executor configured]",
                        success=False,
                    )
                else:
                    result = self._execute_with_gate(tool_call)

                turn.tool_results.append(result)

                # ── Per-turn token budget guard (Gap 3) ──────────────────
                # Count tokens in this tool result and bail if we've
                # accumulated too many, preventing context overflow.
                result_tokens = max(1, len(result.output or "") // 4)
                accumulated_result_tokens += result_tokens
                if accumulated_result_tokens > self.turn_token_budget:
                    logger.warning(
                        "Turn token budget exceeded ({} > {}), injecting trim notice",
                        accumulated_result_tokens,
                        self.turn_token_budget,
                    )
                    # Add a trim notice so the model knows it hit the limit
                    messages.append({
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": tool_call.id,
                                "type": "function",
                                "function": {
                                    "name": tool_call.name,
                                    "arguments": json.dumps(tool_call.arguments),
                                },
                            }
                        ],
                    })
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": (
                            result.output[:500]
                            + f"\n\n[Output trimmed — turn token budget ({self.turn_token_budget} tokens) reached. "
                            "Summarize findings and respond now.]"
                        ),
                    })
                    # Force one final model call to summarise
                    try:
                        final_resp = self._call_model(messages)
                        turn.final_response = self._extract_text(final_resp)
                    except Exception:
                        turn.final_response = "[Tool results were trimmed due to token budget. Please ask a more focused question.]"
                    return turn

                # Add tool call and result to message history
                messages.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": tool_call.id,
                            "type": "function",
                            "function": {
                                "name": tool_call.name,
                                "arguments": json.dumps(tool_call.arguments),
                            },
                        }
                    ],
                })
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result.output,
                })
        else:
            turn.final_response = (
                "[Agent loop reached maximum iterations without completing]"
            )

        return turn

    def _call_model(
        self,
        messages: list[dict[str, Any]],
        stream_handler: Callable[..., str] | None = None,
    ) -> dict[str, Any]:
        """Call the model provider with messages and available tools.

        If a history_pipeline is configured, messages are compressed
        through it before being sent to the model.
        """
        # Apply history processing pipeline to compress context
        if self.history_pipeline is not None:
            messages = self.history_pipeline(messages)

        tools = self._tool_definitions()

        if stream_handler and hasattr(self.model_provider, "chat_stream"):
            system_prompt = ""
            if tools:
                system_prompt = (
                    "Available tools are provided as JSON Schema definitions below. "
                    "You MUST wrap any internal thoughts or reasoning in <thought> tags before calling a tool. "
                    "To call a tool, reply with JSON like "
                    '{"name":"tool_name","arguments":{...}} outside the thought tags.\n'
                    + json.dumps(tools, indent=2)
                )
            stream = self.model_provider.chat_stream(
                messages=messages,
                system_prompt=system_prompt,
            )
            # Pass style="dim" to stream handler for thoughts
            response_text = stream_handler(stream, "dim")
            return {"text": response_text, "tool_calls": []}

        if hasattr(self.model_provider, "chat"):
            result = self.model_provider.chat(messages, tools=tools)
            if isinstance(result, ModelChatResult):
                return {
                    "text": result.text,
                    "tool_calls": [
                        self._model_tool_call_to_raw(tool_call)
                        for tool_call in result.tool_calls
                    ],
                }
            return self._coerce_chat_result(result)

        prompt = self._build_text_completion_prompt(messages, tools)
        if hasattr(self.model_provider, "generate"):
            result = self.model_provider.generate(prompt)
        elif hasattr(self.model_provider, "query"):
            result = self.model_provider.query(prompt)
        else:
            result = str(self.model_provider)

        if isinstance(result, ModelResult):
            response_text = result.text
        else:
            response_text = str(result)

        return {"text": response_text, "tool_calls": []}

    def _build_text_completion_prompt(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> str:
        prompt_parts: list[str] = []
        if tools:
            prompt_parts.append(
                "Available tools are provided as JSON Schema definitions below. "
                "To call one tool, reply only with JSON like "
                '{"name":"tool_name","arguments":{...}}. '
                "To call multiple tools, reply only with JSON like "
                '{"tool_calls":[{"name":"tool_name","arguments":{...}}]}. '
                "After tool results are returned, reply with final text.\n"
                + json.dumps(tools, indent=2)
            )

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if content:
                prompt_parts.append(f"[{role}] {content}")

        return "\n\n".join(prompt_parts)

    def _coerce_chat_result(self, result: Any) -> dict[str, Any]:
        text = getattr(result, "text", "")
        raw_tool_calls = getattr(result, "tool_calls", ())
        return {
            "text": str(text or ""),
            "tool_calls": [
                self._model_tool_call_to_raw(tool_call)
                for tool_call in raw_tool_calls
            ],
        }

    def _model_tool_call_to_raw(self, tool_call: Any) -> dict[str, Any]:
        if isinstance(tool_call, ModelToolCall):
            name = tool_call.name
            arguments = tool_call.arguments
            call_id = tool_call.id
        else:
            name = getattr(tool_call, "name", "")
            arguments = getattr(tool_call, "arguments", {})
            call_id = getattr(tool_call, "id", "")

        return {
            "id": call_id or f"tc_{time.time_ns()}",
            "type": "function",
            "function": {
                "name": name,
                "arguments": json.dumps(arguments or {}),
            },
        }

    def _extract_tool_calls(self, response: dict[str, Any]) -> list[ToolCall]:
        """Extract native or JSON-encoded tool calls from a model response."""

        raw_calls = response.get("tool_calls", [])
        if raw_calls:
            return [
                ToolCall(
                    name=str(tc.get("function", {}).get("name", "") or ""),
                    arguments=self._parse_arguments(
                        tc.get("function", {}).get("arguments", {})
                    ),
                    id=str(tc.get("id", "") or f"tc_{time.time_ns()}"),
                )
                for tc in raw_calls
            ]

        text = str(response.get("text", "") or "")
        payload = self._extract_json_payload(text)
        if payload is None:
            return []

        if isinstance(payload, dict) and "tool_calls" in payload:
            calls = payload.get("tool_calls", [])
            if isinstance(calls, list):
                return [
                    self._json_payload_to_tool_call(call)
                    for call in calls
                    if isinstance(call, dict)
                ]

        if isinstance(payload, dict) and "tool_call" in payload:
            call = payload.get("tool_call")
            if isinstance(call, dict):
                return [self._json_payload_to_tool_call(call)]

        if isinstance(payload, dict) and "name" in payload:
            return [self._json_payload_to_tool_call(payload)]

        return []

    def _extract_json_payload(self, text: str) -> Any | None:
        if '"tool_call"' not in text and '"tool_calls"' not in text and '"name"' not in text:
            return None
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            try:
                return extract_json_from_llm_response(text)
            except JSONExtractionError:
                return None

    def _json_payload_to_tool_call(self, payload: dict[str, Any]) -> ToolCall:
        return ToolCall(
            name=str(payload.get("name", "") or ""),
            arguments=self._parse_arguments(payload.get("arguments", {})),
            id=str(payload.get("id", "") or f"tc_{time.time_ns()}"),
        )

    def _parse_arguments(self, raw_arguments: Any) -> dict[str, Any]:
        if isinstance(raw_arguments, dict):
            return raw_arguments
        if isinstance(raw_arguments, str):
            try:
                parsed = json.loads(raw_arguments)
            except (json.JSONDecodeError, TypeError):
                return {}
            return parsed if isinstance(parsed, dict) else {}
        return {}

    def _extract_text(self, response: dict[str, Any]) -> str:
        """Extract the final text content from a model response."""
        return str(response.get("text", "") or "").strip()

    # ── Dangerous tool set ─────────────────────────────────────────────
    # Any tool in this set requires either explicit user confirmation
    # OR live_execution_enabled to be True at the policy level.
    # When neither is available the call is blocked with a policy-denial
    # result — this closes the silent bypass that existed when
    # confirmation_gate was None (e.g. streaming mode).
    DANGEROUS_TOOLS: frozenset[str] = frozenset({
        "run_command",
        "write_file",
        "delete_file",
        "move_file",
        "browser_click",
        "browser_type",
        "browser_submit",
        "open_path",
        "open_url",
        "clipboard_write",
    })

    def _execute_with_gate(self, tool_call: ToolCall) -> ToolResult:
        """Execute a tool call, applying hooks and the confirmation gate.

        Safety contract
        ---------------
        Dangerous tools are blocked in three layers:

        0. **Hook gate** — ``PreToolUse`` hooks can deny/block/modify the call
           before any other check runs.

        1. If a ``confirmation_gate`` is set — the user is asked interactively.
           The tool runs only if they approve.

        2. If ``confirmation_gate`` is *not* set (e.g. streaming / headless
           mode) — the tool is blocked with a policy-denial result.  This
           closes the silent bypass that previously allowed dangerous tools
           to execute unchallenged in streaming mode.
        """
        assert self.tool_executor is not None
        audit = get_audit_logger()
        # Lazy import avoids the circular dependency chain
        from src.aradhya.tools.approved_rules import get_approved_rules  # noqa: PLC0415
        rules = get_approved_rules()

        # ── Layer 0: Hook gate (PreToolUse) ───────────────────────────
        if self.hook_engine is not None:
            from src.aradhya.hooks.hook_engine import HookEvent, HookDecision  # noqa: PLC0415
            hook_result = self.hook_engine.fire(
                HookEvent.PRE_TOOL_USE,
                {
                    "tool_name": tool_call.name,
                    "tool_input": tool_call.arguments,
                },
            )
            if hook_result.decision in (HookDecision.DENY, HookDecision.BLOCK):
                audit.log_security_event(
                    "tool_blocked_by_hook",
                    f"Hook denied tool '{tool_call.name}': {hook_result.system_message}",
                    severity="warning",
                )
                return ToolResult(
                    tool_call_id=tool_call.id,
                    name=tool_call.name,
                    output=(
                        f"[Tool '{tool_call.name}' was blocked by a PreToolUse hook. "
                        f"{hook_result.system_message}]"
                    ),
                    success=False,
                    requires_confirmation=False,
                )
            # Apply input modifications from hooks
            if hook_result.updated_input is not None:
                tool_call = ToolCall(
                    name=tool_call.name,
                    arguments=hook_result.updated_input,
                    id=tool_call.id,
                )

        # ── Layer 1 fix + Gap A: allow-list + dry-run guard ───────────
        if tool_call.name in self.DANGEROUS_TOOLS:
            # Check allow-list first — skip prompt for pre-approved calls
            if rules.is_approved(tool_call.name, tool_call.arguments):
                logger.debug(
                    "Tool '{}' auto-approved from allow-list", tool_call.name
                )
            elif self.confirmation_gate:
                # Interactive path — ask the user
                # Gate returns (approved: bool, persist: bool)
                # persist=True when user answered 'always' instead of 'yes'
                gate_result = self.confirmation_gate(
                    tool_call.name, tool_call.arguments
                )
                # Support both old bool return and new (bool, bool) tuple
                if isinstance(gate_result, tuple):
                    approved, persist = gate_result
                else:
                    approved, persist = bool(gate_result), False

                if not approved:
                    audit.log_security_event(
                        "tool_denied",
                        f"User denied tool '{tool_call.name}'",
                        severity="warning",
                    )
                    return ToolResult(
                        tool_call_id=tool_call.id,
                        name=tool_call.name,
                        output=f"[Tool '{tool_call.name}' was denied by user]",
                        success=False,
                        requires_confirmation=True,
                    )
                # Record the approval in the allow-list
                rules.record_approval(
                    tool_call.name, tool_call.arguments, persist=persist
                )
                if persist:
                    logger.info(
                        "Tool '{}' permanently approved — won't ask again",
                        tool_call.name,
                    )
            else:
                # No gate at all — dry-run / headless mode.  Block the call.
                audit.log_security_event(
                    "tool_blocked_dry_run",
                    f"Dangerous tool '{tool_call.name}' blocked — no confirmation gate (dry-run mode)",
                    severity="warning",
                )
                return ToolResult(
                    tool_call_id=tool_call.id,
                    name=tool_call.name,
                    output=(
                        f"[Tool '{tool_call.name}' requires confirmation but no gate is "
                        "configured (dry-run mode). Enable live execution or provide a "
                        "confirmation_gate to run this tool.]"
                    ),
                    success=False,
                    requires_confirmation=True,
                )

        try:
            result = self.tool_executor.execute_tool(
                tool_call.name, tool_call.arguments, tool_call.id
            )
            audit.log_tool_call(
                tool_call.name,
                arguments=tool_call.arguments,
                success=result.success,
                output_preview=result.output[:200] if result.output else "",
            )
            # ── PostToolUse hook ──────────────────────────────────────────
            if self.hook_engine is not None:
                from src.aradhya.hooks.hook_engine import HookEvent as _HE  # noqa: PLC0415
                post_event = _HE.POST_TOOL_USE if result.success else _HE.POST_TOOL_USE_FAILURE
                post_result = self.hook_engine.fire(
                    post_event,
                    {
                        "tool_name": tool_call.name,
                        "tool_input": tool_call.arguments,
                        "output": result.output,
                        "success": result.success,
                    },
                )
                if post_result.updated_output is not None:
                    result = ToolResult(
                        tool_call_id=result.tool_call_id,
                        name=result.name,
                        output=post_result.updated_output,
                        success=result.success,
                        requires_confirmation=result.requires_confirmation,
                    )
            # ── Gap 2: auto-log tool failures to learnings engine ────────
            if not result.success:
                self._auto_log_tool_failure(tool_call.name, result.output or "")
            return result
        except Exception as error:
            logger.error(
                "Tool execution failed for '{}': {}", tool_call.name, error
            )
            audit.log_tool_call(
                tool_call.name,
                arguments=tool_call.arguments,
                success=False,
                output_preview=str(error)[:200],
            )
            error_msg = f"[Error executing '{tool_call.name}': {error}]"
            self._auto_log_tool_failure(tool_call.name, str(error))
            return ToolResult(
                tool_call_id=tool_call.id,
                name=tool_call.name,
                output=error_msg,
                success=False,
            )

    def _auto_log_tool_failure(self, tool_name: str, error_msg: str) -> None:
        """Silently log a tool failure to the learnings engine.

        This closes the loop: tool failures now *automatically* feed the
        self-improvement system without relying on the model choosing to
        call log_error itself.
        """
        try:
            from pathlib import Path as _Path
            from src.aradhya.learnings.learnings_engine import LearningsEngine
            _root = _Path(__file__).resolve().parents[2]
            LearningsEngine(_root).log_error(
                tool_name=tool_name,
                error_message=error_msg[:400],
                context="auto-logged by agent_loop on tool failure",
            )
        except Exception as _exc:
            # Never let learnings logging crash the agent loop
            logger.debug("Auto-learnings log failed (non-fatal): {}", _exc)

    def _tool_definitions(self) -> list[dict[str, Any]]:
        if self.tool_executor is None:
            return []
        try:
            return self.tool_executor.list_tools()
        except Exception as error:
            logger.warning("Could not list agent tools: {}", error)
            return []

    def _is_repeated_tool_call(
        self,
        existing_calls: list[ToolCall],
        candidate: ToolCall,
    ) -> bool:
        key = self._tool_call_key(candidate)
        seen_count = sum(1 for call in existing_calls if self._tool_call_key(call) == key)
        return seen_count >= self.max_repeated_tool_calls

    def _tool_call_key(self, tool_call: ToolCall) -> str:
        return json.dumps(
            {"name": tool_call.name, "arguments": tool_call.arguments},
            sort_keys=True,
            default=str,
        )
