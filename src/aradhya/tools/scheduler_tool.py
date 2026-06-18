"""Scheduler tool — exposes TaskScheduler to the model-driven agent loop.

Inspired by Codex's ``automation_update`` dynamic tool, this module lets
the model create, list, and delete scheduled tasks without requiring the
user to manually edit ``~/.aradhya/schedules.json``.

Supported actions
-----------------
- ``shell``       — run a shell command on a cron-like interval
- ``agent_think`` — re-invoke the assistant with a prompt on an interval
                    (heartbeat continuation pattern)
- ``message``     — display a reminder message at a set interval
"""
from __future__ import annotations

import uuid

from loguru import logger

from src.aradhya.tools.tool_registry import tool_definition


# ── Tool definitions ──────────────────────────────────────────────────────────


@tool_definition(
    name="schedule_task",
    description=(
        "Create or update a recurring scheduled task. "
        "Actions: 'shell' (run a command), 'agent_think' (re-prompt the assistant), "
        "'message' (show a reminder). The task runs in the background at the given interval."
    ),
    parameters={
        "type": "object",
        "properties": {
            "task_id": {
                "type": "string",
                "description": (
                    "Unique identifier for the task. "
                    "Omit to auto-generate. Use the same ID to update an existing task."
                ),
            },
            "description": {
                "type": "string",
                "description": "Human-readable description of what this task does.",
            },
            "action": {
                "type": "string",
                "enum": ["shell", "agent_think", "message"],
                "description": "Type of action to perform.",
            },
            "payload": {
                "type": "string",
                "description": (
                    "For 'shell': the shell command to run. "
                    "For 'agent_think': the prompt to send to the assistant. "
                    "For 'message': the reminder text to display."
                ),
            },
            "interval_minutes": {
                "type": "integer",
                "description": "How often to run this task in minutes. Default 60.",
            },
        },
        "required": ["description", "action", "payload"],
    },
    requires_confirmation=True,
)
def schedule_task(
    description: str,
    action: str,
    payload: str,
    task_id: str = "",
    interval_minutes: int = 60,
) -> str:
    """Create or update a scheduled task via the global TaskScheduler."""
    from src.aradhya.scheduler import TaskScheduler  # lazy to avoid circular import

    tid = task_id.strip() or f"task_{uuid.uuid4().hex[:8]}"

    if action not in {"shell", "agent_think", "message"}:
        return f"Error: unknown action '{action}'. Must be shell, agent_think, or message."
    if interval_minutes < 1:
        return "Error: interval_minutes must be >= 1."

    try:
        scheduler = TaskScheduler()
        scheduler.add_task(
            task_id=tid,
            description=description,
            action=action,
            payload=payload,
            interval_minutes=interval_minutes,
        )
        logger.info("schedule_task tool: created task '{}' (action={}, interval={}m)", tid, action, interval_minutes)
        return (
            f"Scheduled task '{tid}' created.\n"
            f"  Description : {description}\n"
            f"  Action      : {action}\n"
            f"  Payload     : {payload[:100]}\n"
            f"  Interval    : every {interval_minutes} minute(s)\n"
            f"Run '/scheduler' to view all tasks."
        )
    except Exception as exc:
        return f"Error creating task: {exc}"


@tool_definition(
    name="list_scheduled_tasks",
    description="List all currently scheduled background tasks.",
    parameters={"type": "object", "properties": {}},
)
def list_scheduled_tasks() -> str:
    """Return a formatted list of all scheduled tasks."""
    from src.aradhya.scheduler import TaskScheduler  # lazy import

    try:
        scheduler = TaskScheduler()
        tasks = scheduler.list_tasks()
        if not tasks:
            return "No scheduled tasks configured. Use schedule_task to create one."
        lines = [f"Scheduled tasks ({len(tasks)}):"]
        for t in tasks:
            status = "enabled" if t.enabled else "disabled"
            last = t.last_run or "never"
            lines.append(
                f"  [{status}] {t.id} — {t.description}\n"
                f"    action={t.action}  interval={t.interval_minutes}m  last_run={last}"
            )
        return "\n".join(lines)
    except Exception as exc:
        return f"Error listing tasks: {exc}"


@tool_definition(
    name="delete_scheduled_task",
    description="Delete a scheduled background task by its ID.",
    parameters={
        "type": "object",
        "properties": {
            "task_id": {
                "type": "string",
                "description": "ID of the task to delete (from list_scheduled_tasks).",
            },
        },
        "required": ["task_id"],
    },
)
def delete_scheduled_task(task_id: str) -> str:
    """Remove a scheduled task by ID."""
    from src.aradhya.scheduler import TaskScheduler  # lazy import

    try:
        scheduler = TaskScheduler()
        removed = scheduler.remove_task(task_id.strip())
        if removed:
            return f"Task '{task_id}' deleted."
        return f"No task found with ID '{task_id}'."
    except Exception as exc:
        return f"Error deleting task: {exc}"


ALL_SCHEDULER_TOOLS = [schedule_task, list_scheduled_tasks, delete_scheduled_task]
