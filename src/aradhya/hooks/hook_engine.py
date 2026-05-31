"""Hook engine — event-driven gates for ARADHYA tool calls.

Implements a protocol compatible with Claude Code's hook system:
- Hooks receive JSON on stdin and return JSON on stdout
- Hooks can allow, deny, or modify tool calls
- Hooks always fail-open (exit 0 on error)
- Configurable timeout per hook

Supported events:
    PreToolUse    — fires before a tool executes (can block/modify)
    PostToolUse   — fires after a tool succeeds (can replace output)
    Stop          — fires when agent turn ends
    SessionStart  — fires when a new session begins
    UserPromptSubmit — fires when user sends a message
"""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from loguru import logger


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

class HookEvent(str, Enum):
    """All supported hook event types."""
    PRE_TOOL_USE = "PreToolUse"
    POST_TOOL_USE = "PostToolUse"
    POST_TOOL_USE_FAILURE = "PostToolUseFailure"
    STOP = "Stop"
    SESSION_START = "SessionStart"
    SESSION_END = "SessionEnd"
    USER_PROMPT_SUBMIT = "UserPromptSubmit"


class HookDecision(str, Enum):
    """Decision returned by a PreToolUse hook."""
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"         # fall through to confirmation gate
    BLOCK = "block"     # hard block, no user override


class HookType(str, Enum):
    """Type of hook implementation."""
    COMMAND = "command"       # shell command
    CALLABLE = "callable"     # Python callable (internal)


@dataclass
class HookDefinition:
    """A single hook bound to an event."""
    event: HookEvent
    hook_type: HookType
    command: str = ""
    callable_fn: Callable[..., dict[str, Any]] | None = None
    timeout_seconds: int = 10
    once: bool = False
    matcher: str | None = None  # tool name filter for PreToolUse/PostToolUse


@dataclass
class HookResult:
    """Result returned by a hook execution."""
    decision: HookDecision = HookDecision.ALLOW
    system_message: str = ""
    updated_input: dict[str, Any] | None = None
    updated_output: str | None = None
    additional_context: str = ""
    error: str = ""
    duration_ms: float = 0.0


# ---------------------------------------------------------------------------
# Hook Engine
# ---------------------------------------------------------------------------

class HookEngine:
    """Central dispatcher for hook events.

    Usage::

        engine = HookEngine()
        engine.register(HookDefinition(
            event=HookEvent.PRE_TOOL_USE,
            hook_type=HookType.COMMAND,
            command="python hooks/pretooluse.py",
            timeout_seconds=10,
        ))

        # Before executing a tool:
        result = engine.fire(HookEvent.PRE_TOOL_USE, {
            "tool_name": "run_command",
            "tool_input": {"command": "rm -rf /tmp/junk"},
        })
        if result.decision == HookDecision.DENY:
            return blocked_result
    """

    def __init__(self) -> None:
        self._hooks: dict[HookEvent, list[HookDefinition]] = {
            event: [] for event in HookEvent
        }
        self._fired_once: set[int] = set()  # ids of once-hooks already fired

    # -- Registration ------------------------------------------------------

    def register(self, hook: HookDefinition) -> None:
        """Register a hook for an event."""
        self._hooks[hook.event].append(hook)
        logger.debug(
            "Hook registered: event={} type={} cmd={}",
            hook.event.value,
            hook.hook_type.value,
            hook.command or "<callable>",
        )

    def register_all(self, hooks: list[HookDefinition]) -> None:
        """Register multiple hooks at once."""
        for hook in hooks:
            self.register(hook)

    def clear(self, event: HookEvent | None = None) -> None:
        """Clear hooks for a specific event, or all hooks."""
        if event is not None:
            self._hooks[event] = []
        else:
            for ev in HookEvent:
                self._hooks[ev] = []
            self._fired_once.clear()

    # -- Firing ------------------------------------------------------------

    def fire(
        self,
        event: HookEvent,
        payload: dict[str, Any],
    ) -> HookResult:
        """Fire all hooks for an event and return the merged result.

        For PreToolUse, hooks are evaluated in order.  The first hook that
        returns a non-allow decision wins.  For PostToolUse, the last
        ``updated_output`` wins.

        All hooks fail-open: if a hook errors, it is logged and treated as
        ALLOW.
        """
        hooks = self._hooks.get(event, [])
        if not hooks:
            return HookResult()

        merged = HookResult()

        for hook in hooks:
            # Skip once-hooks that already fired
            hook_id = id(hook)
            if hook.once and hook_id in self._fired_once:
                continue

            # Matcher filter: only fire for matching tool names
            if hook.matcher and event in (
                HookEvent.PRE_TOOL_USE,
                HookEvent.POST_TOOL_USE,
                HookEvent.POST_TOOL_USE_FAILURE,
            ):
                tool_name = payload.get("tool_name", "")
                if hook.matcher != "*" and hook.matcher != tool_name:
                    continue

            # Execute the hook
            result = self._execute_hook(hook, payload)

            # Mark once-hooks as fired
            if hook.once:
                self._fired_once.add(hook_id)

            # Merge results
            if result.system_message:
                merged.system_message = result.system_message
            if result.additional_context:
                merged.additional_context = result.additional_context
            if result.updated_input is not None:
                merged.updated_input = result.updated_input
            if result.updated_output is not None:
                merged.updated_output = result.updated_output
            if result.error:
                merged.error = result.error
            merged.duration_ms += result.duration_ms

            # For PreToolUse: first deny/block wins
            if event == HookEvent.PRE_TOOL_USE:
                if result.decision in (HookDecision.DENY, HookDecision.BLOCK):
                    merged.decision = result.decision
                    return merged

        return merged

    # -- Internal ----------------------------------------------------------

    def _execute_hook(
        self,
        hook: HookDefinition,
        payload: dict[str, Any],
    ) -> HookResult:
        """Execute a single hook and parse the result."""
        t0 = time.perf_counter()

        try:
            if hook.hook_type == HookType.CALLABLE and hook.callable_fn:
                raw = hook.callable_fn(payload)
            elif hook.hook_type == HookType.COMMAND and hook.command:
                raw = self._run_command_hook(hook.command, payload, hook.timeout_seconds)
            else:
                return HookResult()

            result = self._parse_hook_output(raw)
            result.duration_ms = (time.perf_counter() - t0) * 1000
            return result

        except Exception as exc:
            elapsed = (time.perf_counter() - t0) * 1000
            logger.warning(
                "Hook failed (non-fatal): cmd={} error={} elapsed={:.0f}ms",
                hook.command or "<callable>",
                exc,
                elapsed,
            )
            # Fail-open: treat errors as ALLOW
            return HookResult(
                error=str(exc),
                duration_ms=elapsed,
            )

    def _run_command_hook(
        self,
        command: str,
        payload: dict[str, Any],
        timeout: int,
    ) -> dict[str, Any]:
        """Execute a shell command hook with JSON stdin/stdout protocol."""
        input_json = json.dumps(payload, default=str)

        import shlex
        proc = subprocess.run(
            shlex.split(command),
            input=input_json,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )

        if proc.returncode == 2:
            # Exit code 2 = explicit block (Claude Code convention)
            return {"decision": "block"}

        if proc.stdout.strip():
            try:
                return json.loads(proc.stdout.strip())
            except json.JSONDecodeError:
                logger.debug("Hook stdout was not valid JSON: {}", proc.stdout[:200])

        return {}

    def _parse_hook_output(self, raw: dict[str, Any]) -> HookResult:
        """Parse raw hook output dict into a HookResult."""
        if not raw or not isinstance(raw, dict):
            return HookResult()

        decision_str = raw.get("decision", "allow")
        try:
            decision = HookDecision(decision_str)
        except ValueError:
            decision = HookDecision.ALLOW

        return HookResult(
            decision=decision,
            system_message=raw.get("systemMessage", ""),
            updated_input=raw.get("updatedInput"),
            updated_output=raw.get("updatedOutput"),
            additional_context=raw.get("additionalContext", ""),
        )

    # -- Introspection -----------------------------------------------------

    def hooks_for(self, event: HookEvent) -> list[HookDefinition]:
        """Return all registered hooks for an event."""
        return list(self._hooks.get(event, []))

    @property
    def total_hooks(self) -> int:
        """Total number of registered hooks across all events."""
        return sum(len(hooks) for hooks in self._hooks.values())
