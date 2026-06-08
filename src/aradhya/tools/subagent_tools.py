"""Subagent tools — model-callable tools for spawning and managing subagents.

These tools let the main agent delegate work to background subagents,
check on their progress, send messages, and retrieve results.

All tools follow the ``@tool_definition`` decorator pattern and are
registered in ``assistant_core._build_tool_registry_from_policy()``.
"""

from __future__ import annotations

import json

from loguru import logger

from src.aradhya.tools.tool_registry import tool_definition
from src.aradhya.agents.subagent_runner import SubagentRunner
from src.aradhya.agents.subagent_messenger import SubagentMessenger
from src.aradhya.agents.subagent_registry import SubagentRegistry, SubagentStatus


@tool_definition(
    name="spawn_subagent",
    description=(
        "Spawn a background subagent to work on a subtask in parallel. "
        "The subagent runs in a background thread with its own agent loop. "
        "Returns the subagent_id which can be used to check status or get results. "
        "Use this for: long-running searches, parallel research tasks, "
        "or delegating work while you continue with other tasks."
    ),
    parameters={
        "type": "object",
        "properties": {
            "role": {
                "type": "string",
                "description": (
                    "A short name for the subagent's role, e.g. 'researcher', "
                    "'code-reviewer', 'file-searcher'."
                ),
            },
            "prompt": {
                "type": "string",
                "description": (
                    "The task instruction for the subagent. Be specific about "
                    "what the subagent should do and what to return."
                ),
            },
            "max_turns": {
                "type": "integer",
                "description": (
                    "Maximum number of ReAct iterations the subagent may run "
                    "(default 10)."
                ),
            },
        },
        "required": ["role", "prompt"],
    },
)
def spawn_subagent(
    role: str,
    prompt: str,
    max_turns: int = 10,
) -> str:
    """Spawn a subagent and return its ID."""
    try:
        runner = SubagentRunner.instance()
        sid = runner.spawn(
            role=role,
            prompt=prompt,
            parent_id="main",
            max_turns=max_turns,
        )
        return json.dumps({
            "status": "spawned",
            "subagent_id": sid,
            "role": role,
            "message": f"Subagent '{role}' spawned. Use check_subagent with id '{sid[:8]}...' to check progress.",
        })
    except RuntimeError as exc:
        return json.dumps({
            "status": "error",
            "message": str(exc),
        })


@tool_definition(
    name="check_subagent",
    description=(
        "Check the status of a running subagent, or retrieve its result "
        "if it has completed. Provide the subagent_id returned by spawn_subagent."
    ),
    parameters={
        "type": "object",
        "properties": {
            "subagent_id": {
                "type": "string",
                "description": "The subagent ID to check.",
            },
            "wait_seconds": {
                "type": "number",
                "description": (
                    "How long to wait for the result if the subagent is still "
                    "running (default 5 seconds). Set to 0 for a non-blocking check."
                ),
            },
        },
        "required": ["subagent_id"],
    },
)
def check_subagent(
    subagent_id: str,
    wait_seconds: float = 5.0,
) -> str:
    """Check a subagent's status and optionally wait for its result."""
    runner = SubagentRunner.instance()
    registry = SubagentRegistry.instance()

    info = registry.get(subagent_id)
    if info is None:
        return json.dumps({
            "status": "not_found",
            "message": f"No subagent found with id '{subagent_id}'.",
        })

    if info.status in (SubagentStatus.COMPLETED, SubagentStatus.FAILED, SubagentStatus.CANCELLED):
        result = runner.get_result(subagent_id, timeout=0.1)
        return json.dumps({
            "status": info.status.name.lower(),
            "role": info.role,
            "output": result.output[:4000] if result else "",
            "error": result.error if result else info.error,
        })

    if wait_seconds > 0:
        result = runner.get_result(subagent_id, timeout=wait_seconds)
        if result is not None:
            return json.dumps({
                "status": result.status.name.lower(),
                "role": result.role,
                "output": result.output[:4000],
                "error": result.error,
                "elapsed_seconds": round(result.elapsed_seconds, 1),
            })

    return json.dumps({
        "status": info.status.name.lower(),
        "role": info.role,
        "message": f"Subagent '{info.role}' is still {info.status.name.lower()}.",
    })


@tool_definition(
    name="message_subagent",
    description=(
        "Send a message to a running subagent. Useful for providing "
        "additional instructions or context to a subagent that is already working."
    ),
    parameters={
        "type": "object",
        "properties": {
            "subagent_id": {
                "type": "string",
                "description": "The subagent ID to message.",
            },
            "message": {
                "type": "string",
                "description": "The message to send to the subagent.",
            },
        },
        "required": ["subagent_id", "message"],
    },
)
def message_subagent(subagent_id: str, message: str) -> str:
    """Send a message to a subagent."""
    messenger = SubagentMessenger.instance()
    registry = SubagentRegistry.instance()

    info = registry.get(subagent_id)
    if info is None:
        return json.dumps({
            "status": "error",
            "message": f"No subagent found with id '{subagent_id}'.",
        })

    messenger.send("main", subagent_id, message)
    return json.dumps({
        "status": "sent",
        "message": f"Message sent to subagent '{info.role}'.",
    })


@tool_definition(
    name="list_subagents",
    description=(
        "List all active (running or pending) subagents. Shows each "
        "subagent's ID, role, and current status."
    ),
    parameters={
        "type": "object",
        "properties": {},
    },
)
def list_subagents() -> str:
    """List all active subagents."""
    registry = SubagentRegistry.instance()
    active = registry.list_active()

    if not active:
        return json.dumps({
            "status": "empty",
            "message": "No active subagents.",
            "subagents": [],
        })

    agents = [
        {
            "subagent_id": a.subagent_id,
            "role": a.role,
            "status": a.status.name.lower(),
            "created_at": a.created_at,
        }
        for a in active
    ]
    return json.dumps({
        "status": "ok",
        "count": len(agents),
        "subagents": agents,
    })


@tool_definition(
    name="kill_subagent",
    description=(
        "Cancel a running subagent. Use when a subagent is no longer "
        "needed or is taking too long."
    ),
    parameters={
        "type": "object",
        "properties": {
            "subagent_id": {
                "type": "string",
                "description": "The subagent ID to cancel.",
            },
        },
        "required": ["subagent_id"],
    },
)
def kill_subagent(subagent_id: str) -> str:
    """Cancel a running subagent."""
    runner = SubagentRunner.instance()
    killed = runner.kill(subagent_id)
    if killed:
        return json.dumps({
            "status": "cancelled",
            "message": f"Subagent '{subagent_id}' cancellation requested.",
        })
    return json.dumps({
        "status": "not_found",
        "message": f"No active subagent found with id '{subagent_id}'.",
    })


ALL_SUBAGENT_TOOLS = [
    spawn_subagent,
    check_subagent,
    message_subagent,
    list_subagents,
    kill_subagent,
]
