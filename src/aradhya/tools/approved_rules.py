"""Command allow-list — inspired by Codex's ``prefix_rule`` mechanism.

When a user approves a dangerous tool call, the tool name and a hash of
its arguments are persisted to ``~/.aradhya/approved_rules.jsonl``.
On subsequent identical calls, the confirmation gate is bypassed
automatically — no more re-approving ``pytest`` twenty times per session.

The allow-list is keyed by ``(tool_name, args_hash)`` where ``args_hash``
is a stable SHA-256 of the JSON-serialised arguments (sorted keys, so
argument ordering doesn't matter).

Session scope vs. persistent scope
------------------------------------
- ``"session"``  entries survive only until the process exits.
- ``"persistent"`` entries are written to disk and survive restarts.

By default, approvals are **session-scoped**.  The user can promote an
approval to persistent scope by responding with "always" instead of "yes"
when the confirmation gate asks.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

from src.aradhya.paths import aradhya_path as _aradhya_path

DEFAULT_RULES_FILE: Path | None = None  # resolved lazily via aradhya_path()


def _args_hash(tool_name: str, arguments: dict[str, Any]) -> str:
    """Return a stable SHA-256 hash of (tool_name, sorted arguments)."""
    payload = json.dumps(
        {"tool": tool_name, "args": arguments},
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


class ApprovedRules:
    """Thin allow-list that prevents re-asking for already-approved tool calls.

    Thread-safe: all mutations go through ``_lock``.
    """

    def __init__(self, rules_file: Path | None = None) -> None:
        self._file = rules_file or _aradhya_path("approved_rules.jsonl")
        self._lock = threading.Lock()

        # session_cache: set of (tool_name, args_hash) approved this session
        self._session_cache: set[str] = set()

        # persistent_cache: loaded from disk on init
        self._persistent_cache: set[str] = set()

        self._load_persistent()

    # ── Public API ────────────────────────────────────────────────────

    def is_approved(self, tool_name: str, arguments: dict[str, Any]) -> bool:
        """Return True if this exact tool call was previously approved."""
        key = _args_hash(tool_name, arguments)
        with self._lock:
            return key in self._session_cache or key in self._persistent_cache

    def record_approval(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        persist: bool = False,
    ) -> None:
        """Record that the user approved this tool call.

        Parameters
        ----------
        tool_name:
            Name of the approved tool.
        arguments:
            Arguments the tool was called with.
        persist:
            If True, write to disk so the approval survives restarts.
        """
        key = _args_hash(tool_name, arguments)
        with self._lock:
            self._session_cache.add(key)
            if persist:
                self._write_persistent(tool_name, arguments, key)
                self._persistent_cache.add(key)

    def clear_session(self) -> None:
        """Drop all session-scoped approvals (call on shutdown)."""
        with self._lock:
            self._session_cache.clear()

    # ── Disk persistence ──────────────────────────────────────────────

    def _load_persistent(self) -> None:
        """Load previously persisted rules from disk (non-fatal on error)."""
        if not self._file.is_file():
            return
        try:
            for line in self._file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    self._persistent_cache.add(entry["key"])
                except (json.JSONDecodeError, KeyError):
                    continue
        except OSError as exc:
            logger.debug("Could not load approved_rules: {}", exc)

    def _write_persistent(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        key: str,
    ) -> None:
        """Append a persistent rule to disk."""
        try:
            self._file.parent.mkdir(parents=True, exist_ok=True)
            entry = {
                "key": key,
                "tool": tool_name,
                "args_preview": str(arguments)[:120],
                "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            with self._file.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=True) + "\n")
        except OSError as exc:
            logger.debug("Could not persist approval rule: {}", exc)


# ── Global instance ───────────────────────────────────────────────────────────
_global_rules: ApprovedRules | None = None


def get_approved_rules(rules_file: Path | None = None) -> ApprovedRules:
    """Return the global ApprovedRules instance (created lazily)."""
    global _global_rules
    if _global_rules is None:
        _global_rules = ApprovedRules(rules_file)
    return _global_rules
