"""Leaf data types shared between the agent loop and the tool registry.

``ToolCall`` and ``ToolResult`` live here — rather than in ``agent_loop`` — so
that ``tool_registry`` can import them without recreating the import cycle
``agent_loop -> tools -> tool_registry -> agent_loop``.

This module must stay dependency-free: it imports nothing from
``src.aradhya`` so it can sit at the bottom of the dependency graph.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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
