"""Audit logger for all tool executions and system actions.

Every tool call, command execution, and state change is logged to a
JSONL file for transparency, debugging, and safety review.  Inspired
by GStack's security logging and Career-Ops' pipeline verification.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

DEFAULT_AUDIT_DIR = Path.home() / ".aradhya" / "audit"
MAX_LOG_SIZE_MB = 10
MAX_LOG_FILES = 5


class AuditLogger:
    """Append-only JSONL audit logger with automatic rotation.

    All entries are written to ``audit.jsonl``.  When the file exceeds
    ``MAX_LOG_SIZE_MB``, it is rotated (renamed with a timestamp suffix)
    and a new file is started.  Up to ``MAX_LOG_FILES`` rotated files
    are kept.
    """

    def __init__(self, audit_dir: Path | None = None) -> None:
        self._dir = audit_dir or DEFAULT_AUDIT_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / "audit.jsonl"
        self._lock = threading.Lock()

    def log_tool_call(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        success: bool | None = None,
        output_preview: str = "",
        source: str = "agent",
    ) -> None:
        """Log a tool call with its arguments and result."""
        self._write({
            "type": "tool_call",
            "tool": tool_name,
            "args": _sanitize_args(arguments or {}),
            "success": success,
            "output": output_preview[:500],
            "source": source,
        })

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

    def _write(self, entry: dict[str, Any]) -> None:
        """Write a single entry to the audit log (thread-safe)."""
        entry["ts"] = datetime.now().isoformat(timespec="seconds")
        entry["pid"] = os.getpid()

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
