"""Structured agent execution loop for multi-step tool-calling workflows.

Inspired by OpenClaw's agent loop, this module implements a proper agentic
cycle:  prompt → model → tool calls → execute → feed results → loop until
the model returns a final text response.

The loop respects the confirmation gate for dangerous operations and supports
streaming responses.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Protocol

from loguru import logger

from src.aradhya.audit_logger import get_audit_logger

from src.aradhya.json_extractor import (
    JSONExtractionError,
    extract_json_from_llm_response,
)
from src.aradhya.model_provider import ModelChatResult, ModelResult, ModelToolCall


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
    ) -> None:
        self.model_provider = model_provider
        self.tool_executor = tool_executor
        self.confirmation_gate = confirmation_gate
        self.max_iterations = max_iterations
        self.max_repeated_tool_calls = max_repeated_tool_calls

    def run(
        self,
        user_message: str,
        system_prompt: str,
        history: list[dict[str, Any]] | None = None,
        thinking: ThinkingLevel = ThinkingLevel.MEDIUM,
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

        for iteration in range(self.max_iterations):
            turn.iterations = iteration + 1

            try:
                response = self._call_model(messages)
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

    def _call_model(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        """Call the model provider with messages and available tools."""

        tools = self._tool_definitions()

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

    def _execute_with_gate(self, tool_call: ToolCall) -> ToolResult:
        """Execute a tool call, applying the confirmation gate if needed."""
        assert self.tool_executor is not None
        audit = get_audit_logger()

        dangerous_tools = {
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
        }

        if tool_call.name in dangerous_tools and self.confirmation_gate:
            approved = self.confirmation_gate(tool_call.name, tool_call.arguments)
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
            return ToolResult(
                tool_call_id=tool_call.id,
                name=tool_call.name,
                output=f"[Error executing '{tool_call.name}': {error}]",
                success=False,
            )

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
