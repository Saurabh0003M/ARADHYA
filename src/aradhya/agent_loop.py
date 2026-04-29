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
        self, name: str, arguments: dict[str, Any]
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
    ) -> None:
        self.model_provider = model_provider
        self.tool_executor = tool_executor
        self.confirmation_gate = confirmation_gate
        self.max_iterations = max_iterations

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
        """Call the model provider with the current message list.

        This is a thin wrapper that delegates to the model provider's
        completion method.  For now it uses a simple prompt-based call;
        full function-calling support will be added when providers
        implement the OpenAI-compatible function calling API.
        """

        # Build a flat prompt from messages for providers that only support
        # simple text completion (like the current Ollama provider).
        prompt_parts: list[str] = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if content:
                prompt_parts.append(f"[{role}] {content}")

        full_prompt = "\n\n".join(prompt_parts)

        # Use the model provider's generate method
        if hasattr(self.model_provider, "generate"):
            response_text = self.model_provider.generate(full_prompt)
        elif hasattr(self.model_provider, "query"):
            response_text = self.model_provider.query(full_prompt)
        else:
            response_text = str(self.model_provider)

        return {"text": response_text, "tool_calls": []}

    def _extract_tool_calls(self, response: dict[str, Any]) -> list[ToolCall]:
        """Extract tool calls from a model response.

        When providers support native function calling, this will parse
        the structured tool_calls array.  For now, we also attempt to
        detect JSON-encoded tool calls in the response text.
        """

        # Native tool calls from the response
        raw_calls = response.get("tool_calls", [])
        if raw_calls:
            return [
                ToolCall(
                    name=tc.get("function", {}).get("name", ""),
                    arguments=json.loads(
                        tc.get("function", {}).get("arguments", "{}")
                    ),
                    id=tc.get("id", f"tc_{time.time_ns()}"),
                )
                for tc in raw_calls
            ]

        # Attempt to detect tool calls embedded in text
        text = response.get("text", "")
        try:
            if '"tool_call"' in text or '"name"' in text:
                parsed = json.loads(text)
                if isinstance(parsed, dict) and "name" in parsed:
                    return [
                        ToolCall(
                            name=parsed["name"],
                            arguments=parsed.get("arguments", {}),
                            id=f"tc_{time.time_ns()}",
                        )
                    ]
        except (json.JSONDecodeError, TypeError):
            pass

        return []

    def _extract_text(self, response: dict[str, Any]) -> str:
        """Extract the final text content from a model response."""
        return response.get("text", "").strip()

    def _execute_with_gate(self, tool_call: ToolCall) -> ToolResult:
        """Execute a tool call, applying the confirmation gate if needed."""
        assert self.tool_executor is not None

        # Check if this tool requires confirmation
        dangerous_tools = {
            "run_command",
            "write_file",
            "delete_file",
            "move_file",
            "browser_click",
            "browser_type",
            "browser_submit",
        }

        if tool_call.name in dangerous_tools and self.confirmation_gate:
            approved = self.confirmation_gate(tool_call.name, tool_call.arguments)
            if not approved:
                return ToolResult(
                    tool_call_id=tool_call.id,
                    name=tool_call.name,
                    output=f"[Tool '{tool_call.name}' was denied by user]",
                    success=False,
                    requires_confirmation=True,
                )

        try:
            return self.tool_executor.execute_tool(
                tool_call.name, tool_call.arguments
            )
        except Exception as error:
            logger.error(
                "Tool execution failed for '{}': {}", tool_call.name, error
            )
            return ToolResult(
                tool_call_id=tool_call.id,
                name=tool_call.name,
                output=f"[Error executing '{tool_call.name}': {error}]",
                success=False,
            )
