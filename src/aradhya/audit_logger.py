"""Event-sourced audit logger for all tool executions and system actions.

Every tool call, command execution, turn lifecycle event, and state change
is logged to a JSONL file with session and turn identifiers for full
session replay.  Inspired by Codex's event-sourced session protocol.

Event types
-----------
- ``session_meta``  – emitted once per session start with config snapshot
- ``turn_start``    – emitted at the beginning of each user turn
- ``turn_end``      – emitted at the end of each turn with summary stats
- ``tool_call``     – each tool invocation (enhanced with wall_time_ms)
- ``command``       – user slash-commands
- ``state_change``  – assistant state transitions
- ``security``      – blocked actions, policy denials
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

DEFAULT_AUDIT_DIR = Path.home() / ".aradhya" / "audit"
MAX_LOG_SIZE_MB = 10
MAX_LOG_FILES = 5


def _generate_turn_id() -> str:
    """Generate a compact, unique turn identifier."""
    return f"turn_{uuid.uuid4().hex[:12]}"


class AuditLogger:
    """Append-only JSONL audit logger with session/turn tracking.

    All entries are written to ``audit.jsonl``.  When the file exceeds
    ``MAX_LOG_SIZE_MB``, it is rotated (renamed with a timestamp suffix)
    and a new file is started.  Up to ``MAX_LOG_FILES`` rotated files
    are kept.

    Every entry includes ``session_id`` and ``turn_id`` fields so that
    the full session can be replayed from the log alone.
    """

    def __init__(self, audit_dir: Path | None = None) -> None:
        self._dir = audit_dir or DEFAULT_AUDIT_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / "audit.jsonl"
        self._lock = threading.Lock()
        self._session_id: str = ""
        self._turn_id: str = ""

    # ── Session / turn lifecycle ──────────────────────────────────────

    def set_session_id(self, session_id: str) -> None:
        """Bind subsequent events to a session."""
        self._session_id = session_id

    @property
    def current_turn_id(self) -> str:
        return self._turn_id

    def log_session_meta(
        self,
        session_id: str,
        config_snapshot: dict[str, Any] | None = None,
    ) -> None:
        """Emit a session_meta event (once at session start)."""
        self._session_id = session_id
        self._write({
            "type": "session_meta",
            "session_id": session_id,
            "config": config_snapshot or {},
        })

    def log_turn_start(
        self,
        user_message: str,
        turn_id: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> str:
        """Emit a turn_start event and return the assigned turn_id."""
        self._turn_id = turn_id or _generate_turn_id()
        self._write({
            "type": "turn_start",
            "turn_id": self._turn_id,
            "user_message": user_message[:500],
            "context": context or {},
        })
        return self._turn_id

    def log_turn_end(
        self,
        turn_id: str | None = None,
        iterations: int = 0,
        tool_calls_count: int = 0,
        success: bool = True,
        final_response_preview: str = "",
    ) -> None:
        """Emit a turn_end event with summary statistics."""
        self._write({
            "type": "turn_end",
            "turn_id": turn_id or self._turn_id,
            "iterations": iterations,
            "tool_calls_count": tool_calls_count,
            "success": success,
            "response_preview": final_response_preview[:300],
        })
        self._turn_id = ""

    # ── Tool calls ────────────────────────────────────────────────────

    def log_tool_call(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        success: bool | None = None,
        output_preview: str = "",
        source: str = "agent",
        wall_time_ms: int | None = None,
        exit_code: int | None = None,
    ) -> None:
        """Log a tool call with its arguments, result, and timing."""
        entry: dict[str, Any] = {
            "type": "tool_call",
            "tool": tool_name,
            "args": _sanitize_args(arguments or {}),
            "success": success,
            "output": output_preview[:500],
            "source": source,
        }
        if wall_time_ms is not None:
            entry["wall_time_ms"] = wall_time_ms
        if exit_code is not None:
            entry["exit_code"] = exit_code
        self._write(entry)

    # ── Commands & state ──────────────────────────────────────────────

    def log_command(
        self,
        command: str,
        source: str = "cli",
        result: str = "",
    ) -> None:
        """Log a user command or slash command."""
        self._write({
            "type": "command",
            "command": command[:200],
            "source": source,
            "result": result[:200],
        })

    def log_state_change(
        self,
        field: str,
        old_value: Any,
        new_value: Any,
    ) -> None:
        """Log an assistant state transition."""
        self._write({
            "type": "state_change",
            "field": field,
            "old": str(old_value)[:100],
            "new": str(new_value)[:100],
        })

    def log_security_event(
        self,
        event: str,
        details: str = "",
        severity: str = "info",
    ) -> None:
        """Log a security-relevant event (blocked action, policy denial, etc)."""
        self._write({
            "type": "security",
            "event": event,
            "details": details[:500],
            "severity": severity,
        })

    def log_event(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        """Generic event logger for one-off event types (e.g. 'compacted').

        Codex emits a ``compacted`` event whenever session history is
        replaced with a summarised version, so the full session can still
        be replayed from the audit log.  Use this method for any event type
        that doesn't fit the existing typed helpers.
        """
        entry: dict[str, Any] = {"type": event_type}
        if payload:
            entry.update(payload)
        self._write(entry)

    # ── Read helpers ──────────────────────────────────────────────────

    def recent_entries(self, count: int = 20) -> list[dict[str, Any]]:
        """Read the most recent N audit entries."""
        if not self._path.is_file():
            return []
        try:
            lines = self._path.read_text(encoding="utf-8").strip().splitlines()
            entries = []
            for line in lines[-count:]:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
            return entries
        except OSError:
            return []

    # ── Internal ──────────────────────────────────────────────────────

    def _write(self, entry: dict[str, Any]) -> None:
        """Write a single entry to the audit log (thread-safe)."""
        entry["ts"] = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        entry["pid"] = os.getpid()

        # Inject session/turn context into every event
        if self._session_id and "session_id" not in entry:
            entry["session_id"] = self._session_id
        if self._turn_id and "turn_id" not in entry:
            entry["turn_id"] = self._turn_id

        line = json.dumps(entry, default=str, ensure_ascii=True) + "\n"

        with self._lock:
            try:
                self._rotate_if_needed()
                with open(self._path, "a", encoding="utf-8") as f:
                    f.write(line)
            except OSError as exc:
                logger.debug("Audit write failed: {}", exc)

    def _rotate_if_needed(self) -> None:
        """Rotate the log file if it exceeds the size limit."""
        if not self._path.is_file():
            return
        try:
            size_mb = self._path.stat().st_size / (1024 * 1024)
        except OSError:
            return

        if size_mb < MAX_LOG_SIZE_MB:
            return

        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        rotated = self._dir / f"audit-{stamp}.jsonl"
        try:
            self._path.rename(rotated)
        except OSError:
            return

        # Clean up old rotated files
        rotated_files = sorted(
            self._dir.glob("audit-*.jsonl"),
            key=lambda p: p.stat().st_mtime,
        )
        while len(rotated_files) > MAX_LOG_FILES:
            oldest = rotated_files.pop(0)
            try:
                oldest.unlink()
            except OSError:
                pass


def _sanitize_args(args: dict[str, Any]) -> dict[str, Any]:
    """Strip sensitive values from tool arguments before logging."""
    sanitized = {}
    sensitive_keys = {"password", "token", "secret", "api_key", "key", "credential"}
    for k, v in args.items():
        if any(s in k.lower() for s in sensitive_keys):
            sanitized[k] = "***REDACTED***"
        elif isinstance(v, str) and len(v) > 500:
            sanitized[k] = v[:500] + "...[truncated]"
        else:
            sanitized[k] = v
    return sanitized


# ── Global audit logger instance ──────────────────────────────────────
_global_audit: AuditLogger | None = None


def get_audit_logger(audit_dir: Path | None = None) -> AuditLogger:
    """Return the global audit logger, creating it on first call."""
    global _global_audit
    if _global_audit is None:
        _global_audit = AuditLogger(audit_dir)
    return _global_audit
