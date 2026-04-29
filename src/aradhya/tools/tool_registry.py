"""Central registry for model-callable tools.

Each tool is a Python function with a JSON Schema definition that the model
can invoke during the agent loop.  The ToolRegistry holds all registered
tools and provides execution dispatch.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from loguru import logger

from src.aradhya.agent_loop import ToolResult
from src.aradhya.tools.runtime_policy import ToolRuntimePolicy


@dataclass
class ToolDefinition:
    """A registered tool with its callable and schema."""
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., str]
    requires_confirmation: bool = False


def tool_definition(
    name: str,
    description: str,
    parameters: dict[str, Any] | None = None,
    requires_confirmation: bool = False,
) -> Callable:
    """Decorator to register a function as a model-callable tool."""
    def decorator(func: Callable[..., str]) -> Callable[..., str]:
        func._tool_def = ToolDefinition(  # type: ignore[attr-defined]
            name=name,
            description=description,
            parameters=parameters or {"type": "object", "properties": {}},
            handler=func,
            requires_confirmation=requires_confirmation,
        )
        return func
    return decorator


class ToolRegistry:
    """Registry of all available model-callable tools.

    Implements the ``ToolExecutor`` protocol expected by ``AgentLoop``.
    """

    def __init__(self, policy: ToolRuntimePolicy | None = None) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        self.policy = policy

    def register(self, tool_def: ToolDefinition) -> None:
        """Register a tool definition."""
        self._tools[tool_def.name] = tool_def
        logger.debug("Registered tool: {}", tool_def.name)

    def register_function(self, func: Callable) -> None:
        """Register a decorated function as a tool."""
        tool_def = getattr(func, "_tool_def", None)
        if tool_def is None:
            raise ValueError(
                f"Function {func.__name__} is not decorated with @tool_definition"
            )
        self.register(tool_def)

    def execute_tool(
        self, name: str, arguments: dict[str, Any], tool_call_id: str = ""
    ) -> ToolResult:
        """Execute a tool by name with the given arguments."""
        tool_def = self._tools.get(name)
        if tool_def is None:
            return ToolResult(
                tool_call_id=tool_call_id,
                name=name,
                output=f"Unknown tool: {name}",
                success=False,
            )

        if self.policy is not None:
            decision = self.policy.check(
                name,
                arguments,
                requires_confirmation=tool_def.requires_confirmation,
            )
            if not decision.allowed:
                return ToolResult(
                    tool_call_id=tool_call_id,
                    name=name,
                    output=decision.message,
                    success=False,
                    requires_confirmation=decision.requires_confirmation,
                )

        try:
            output = tool_def.handler(**arguments)
            return ToolResult(
                tool_call_id=tool_call_id,
                name=name,
                output=str(output),
                success=True,
                requires_confirmation=tool_def.requires_confirmation,
            )
        except Exception as error:
            return ToolResult(
                tool_call_id=tool_call_id,
                name=name,
                output=f"Error: {error}",
                success=False,
            )

    def list_tools(self) -> list[dict[str, Any]]:
        """Return JSON Schema definitions for all registered tools."""
        return [
            {
                "type": "function",
                "function": {
                    "name": td.name,
                    "description": td.description,
                    "parameters": td.parameters,
                },
            }
            for td in self._tools.values()
        ]

    def get(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    @property
    def count(self) -> int:
        return len(self._tools)
