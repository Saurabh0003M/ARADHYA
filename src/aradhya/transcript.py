"""Structured conversation transcript logger.

Records every turn of a conversation — user inputs, model responses,
tool calls, tool results, system messages, and planning steps — into
a JSONL file for full session replay and debugging.

Inspired by Antigravity's ``transcript.jsonl`` format.  Each line in
the file is a self-contained JSON object representing a single
``TranscriptEntry``.

Usage::

    from src.aradhya.transcript import ConversationTranscript

    tx = ConversationTranscript("session_abc123")
    tx.log_user_input("What time is it?")
    tx.log_model_response("It is 10:07 AM IST.", thinking="User wants current time")
    tx.log_tool_call("get_time", {"timezone": "Asia/Kolkata"}, result="10:07")
    tx.log_system_message("Session resumed from checkpoint")
    tx.log_planning_step("Step 1: identify intent", metadata={"confidence": 0.95})

    # Read back
    entries = tx.read_all()
    recent  = tx.read_since(step_index=5)
    print(tx.summary(max_entries=10))
"""

from __future__ import annotations

import dataclasses
import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

from src.aradhya.paths import sessions_dir as _resolve_sessions_dir


# ---------------------------------------------------------------------------
# Transcript entry
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TranscriptEntry:
    """Immutable record of a single conversation event.

    Fields
    ------
    step_index : int
        Monotonically increasing index within the transcript.
    timestamp : str
        ISO-8601 timestamp (UTC) of when the entry was created.
    source : str
        Who produced this entry: ``USER``, ``MODEL``, ``SYSTEM``, ``TOOL``.
    entry_type : str
        Semantic type: ``USER_INPUT``, ``MODEL_RESPONSE``, ``TOOL_CALL``,
        ``TOOL_RESULT``, ``SYSTEM_MESSAGE``, ``PLANNING_STEP``.
    status : str
        Completion state: ``DONE``, ``ERROR``, ``PENDING``.
    content : str
        The primary textual payload.
    thinking : str
        Chain-of-thought reasoning from the model (if available).
    tool_calls : list[dict]
        Structured tool-call payloads attached to a model response.
    metadata : dict
        Arbitrary key-value pairs for extensibility.
    """

    step_index: int
    timestamp: str
    source: str
    entry_type: str
    status: str
    content: str
    thinking: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    # -- Serialisation helpers ------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Convert to a plain dict suitable for JSON serialisation."""
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TranscriptEntry:
        """Reconstruct from a JSON-decoded dict."""
        return cls(
            step_index=data.get("step_index", 0),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", "SYSTEM"),
            entry_type=data.get("entry_type", "SYSTEM_MESSAGE"),
            status=data.get("status", "DONE"),
            content=data.get("content", ""),
            thinking=data.get("thinking", ""),
            tool_calls=data.get("tool_calls", []),
            metadata=data.get("metadata", {}),
        )


# ---------------------------------------------------------------------------
# Conversation transcript
# ---------------------------------------------------------------------------

class ConversationTranscript:
    """Append-only, thread-safe JSONL conversation transcript.

    One transcript exists per session.  Entries are written atomically
    (write + flush) and protected by a ``threading.Lock`` so concurrent
    callers never interleave writes.

    Parameters
    ----------
    session_id : str
        Unique identifier for the session.
    base_dir : Path | None
        Override for the sessions root directory.  Defaults to
        ``~/.aradhya/sessions`` via ``paths.sessions_dir()``.
    """

    def __init__(self, session_id: str, base_dir: Path | None = None) -> None:
        self._session_id = session_id
        self._base_dir = base_dir or _resolve_sessions_dir()

        # Ensure the per-session directory exists
        self._session_dir = self._base_dir / session_id
        self._session_dir.mkdir(parents=True, exist_ok=True)

        self._path = self._session_dir / "transcript.jsonl"
        self._lock = threading.Lock()
        self._step_index = self._recover_step_index()

        logger.debug(
            "Transcript initialised for session '{}' at {}",
            session_id,
            self._path,
        )

    # -- Properties -----------------------------------------------------------

    @property
    def session_id(self) -> str:
        """The session this transcript belongs to."""
        return self._session_id

    @property
    def path(self) -> Path:
        """Absolute path to the transcript JSONL file."""
        return self._path

    @property
    def step_index(self) -> int:
        """Current (next-to-be-written) step index."""
        return self._step_index

    # -- Public logging helpers -----------------------------------------------

    def log_user_input(self, content: str) -> TranscriptEntry:
        """Record a user input turn."""
        entry = self._make_entry(
            source="USER",
            entry_type="USER_INPUT",
            status="DONE",
            content=content,
        )
        self._append(entry)
        return entry

    def log_model_response(
        self,
        content: str,
        thinking: str = "",
        tool_calls: list[dict[str, Any]] | None = None,
    ) -> TranscriptEntry:
        """Record a model response, optionally with chain-of-thought and tool calls."""
        entry = self._make_entry(
            source="MODEL",
            entry_type="MODEL_RESPONSE",
            status="DONE",
            content=content,
            thinking=thinking,
            tool_calls=tool_calls or [],
        )
        self._append(entry)
        return entry

    def log_tool_call(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        result: str = "",
        status: str = "DONE",
    ) -> TranscriptEntry:
        """Record a tool invocation and its result.

        The ``tool_calls`` field carries a single-element list with
        ``name``, ``arguments``, and ``result`` for uniformity with
        the model-response format.
        """
        entry = self._make_entry(
            source="TOOL",
            entry_type="TOOL_CALL",
            status=status,
            content=result,
            tool_calls=[{
                "name": tool_name,
                "arguments": arguments,
                "result": result,
            }],
        )
        self._append(entry)
        return entry

    def log_system_message(self, content: str) -> TranscriptEntry:
        """Record a system-level message (e.g. session resumed, error)."""
        entry = self._make_entry(
            source="SYSTEM",
            entry_type="SYSTEM_MESSAGE",
            status="DONE",
            content=content,
        )
        self._append(entry)
        return entry

    def log_planning_step(
        self,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> TranscriptEntry:
        """Record an intermediate planning/reasoning step."""
        entry = self._make_entry(
            source="MODEL",
            entry_type="PLANNING_STEP",
            status="DONE",
            content=content,
            metadata=metadata or {},
        )
        self._append(entry)
        return entry

    # -- Read helpers ---------------------------------------------------------

    def read_all(self) -> list[TranscriptEntry]:
        """Read every entry from the transcript file."""
        return self._read_entries()

    def read_since(self, step_index: int) -> list[TranscriptEntry]:
        """Read entries whose ``step_index`` is ≥ *step_index*."""
        return [
            e for e in self._read_entries()
            if e.step_index >= step_index
        ]

    def summary(self, max_entries: int = 10) -> str:
        """Generate a compact, human-readable summary of the transcript.

        Shows at most *max_entries* from the tail of the transcript
        with one line per entry.
        """
        entries = self._read_entries()
        if not entries:
            return f"[Transcript for session '{self._session_id}' is empty]"

        tail = entries[-max_entries:]
        lines: list[str] = [
            f"── Transcript ({len(entries)} entries, "
            f"showing last {len(tail)}) ──",
        ]
        for e in tail:
            prefix = f"[{e.step_index:>4}] {e.source:<6} {e.entry_type:<16}"
            # Truncate content for readability
            snippet = e.content.replace("\n", " ")[:120]
            status_tag = f" ({e.status})" if e.status != "DONE" else ""
            lines.append(f"{prefix} {snippet}{status_tag}")

        return "\n".join(lines)

    # -- Internal helpers -----------------------------------------------------

    def _make_entry(
        self,
        *,
        source: str,
        entry_type: str,
        status: str,
        content: str,
        thinking: str = "",
        tool_calls: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TranscriptEntry:
        """Build a new ``TranscriptEntry`` with auto-incremented index."""
        entry = TranscriptEntry(
            step_index=self._step_index,
            timestamp=datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            source=source,
            entry_type=entry_type,
            status=status,
            content=content,
            thinking=thinking,
            tool_calls=tool_calls or [],
            metadata=metadata or {},
        )
        self._step_index += 1
        return entry

    def _append(self, entry: TranscriptEntry) -> None:
        """Atomically append a single entry to the JSONL file.

        Writes are protected by a threading lock.  After writing the
        JSON line, the file handle is flushed to ensure durability.
        """
        line = json.dumps(entry.to_dict(), default=str, ensure_ascii=True) + "\n"

        with self._lock:
            try:
                with open(self._path, "a", encoding="utf-8") as fh:
                    fh.write(line)
                    fh.flush()
            except OSError as exc:
                logger.error(
                    "Failed to write transcript entry (step {}): {}",
                    entry.step_index,
                    exc,
                )

    def _read_entries(self) -> list[TranscriptEntry]:
        """Parse the entire JSONL file into a list of entries."""
        if not self._path.is_file():
            return []
        try:
            text = self._path.read_text(encoding="utf-8").strip()
            if not text:
                return []
            entries: list[TranscriptEntry] = []
            for lineno, line in enumerate(text.splitlines(), start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(TranscriptEntry.from_dict(json.loads(line)))
                except (json.JSONDecodeError, KeyError) as exc:
                    logger.warning(
                        "Skipping malformed transcript line {} in '{}': {}",
                        lineno,
                        self._path.name,
                        exc,
                    )
            return entries
        except OSError as exc:
            logger.error("Failed to read transcript '{}': {}", self._path, exc)
            return []

    def _recover_step_index(self) -> int:
        """Resume step numbering from an existing transcript file.

        Reads the last non-empty line to find the highest step_index,
        then returns ``highest + 1``.  Falls back to ``0`` on any error.
        """
        if not self._path.is_file():
            return 0
        try:
            text = self._path.read_text(encoding="utf-8").strip()
            if not text:
                return 0
            # Walk backwards through lines to find the last valid entry
            for line in reversed(text.splitlines()):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    return int(data.get("step_index", 0)) + 1
                except (json.JSONDecodeError, ValueError):
                    continue
            return 0
        except OSError:
            return 0
