"""Session management for persistent conversation history.

Sessions are stored as JSON files in ``~/.aradhya/sessions/``.  Each session
captures the chronological list of messages exchanged between the user and
Aradhya, along with metadata for compaction and pruning.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

DEFAULT_SESSIONS_DIR = Path.home() / ".aradhya" / "sessions"
MAX_FULL_MESSAGES = 40
COMPACTION_TRIGGER = 60


@dataclass
class Message:
    """A single message in a session."""

    role: str  # "user" | "assistant" | "system" | "summary"
    content: str
    timestamp: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat(timespec="seconds")


@dataclass
class Session:
    """A conversation session with message history."""

    id: str
    messages: list[Message] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    title: str = ""
    compacted: bool = False

    def __post_init__(self) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now

    def add_message(self, role: str, content: str, **metadata: Any) -> None:
        """Append a message and update the session timestamp."""
        self.messages.append(Message(role=role, content=content, metadata=metadata))
        self.updated_at = datetime.now().isoformat(timespec="seconds")
        if not self.title and role == "user" and content.strip():
            self.title = content.strip()[:80]

    @property
    def message_count(self) -> int:
        return len(self.messages)

    def recent_messages(self, count: int = MAX_FULL_MESSAGES) -> list[Message]:
        """Return the last N messages for full-fidelity prompt building."""
        return self.messages[-count:]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "compacted": self.compacted,
            "messages": [asdict(m) for m in self.messages],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Session":
        messages = [
            Message(**m) for m in data.get("messages", [])
        ]
        return cls(
            id=data["id"],
            messages=messages,
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            title=data.get("title", ""),
            compacted=data.get("compacted", False),
        )


class SessionManager:
    """Manages session persistence and lifecycle.

    Sessions are stored as individual JSON files named ``<session-id>.json``.
    """

    def __init__(self, sessions_dir: Path | None = None) -> None:
        self.sessions_dir = sessions_dir or DEFAULT_SESSIONS_DIR
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self._active_session: Session | None = None

    @property
    def active_session(self) -> Session | None:
        return self._active_session

    def create_session(self, session_id: str | None = None) -> Session:
        """Create and activate a new session."""
        if session_id is None:
            session_id = f"session_{int(time.time() * 1000)}"
        session = Session(id=session_id)
        self._active_session = session
        self.save(session)
        logger.info("Created new session '{}'", session_id)
        return session

    def load_session(self, session_id: str) -> Session | None:
        """Load a session from disk and make it active."""
        session_path = self.sessions_dir / f"{session_id}.json"
        if not session_path.is_file():
            return None

        try:
            raw = session_path.read_text(encoding="utf-8")
            data = json.loads(raw)
            session = Session.from_dict(data)
            self._active_session = session
            logger.info(
                "Loaded session '{}' with {} messages",
                session_id,
                session.message_count,
            )
            return session
        except (json.JSONDecodeError, KeyError) as error:
            logger.warning("Failed to load session '{}': {}", session_id, error)
            return None

    def save(self, session: Session | None = None) -> None:
        """Persist a session to disk."""
        session = session or self._active_session
        if session is None:
            return

        session_path = self.sessions_dir / f"{session.id}.json"
        session_path.write_text(
            json.dumps(session.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def list_sessions(self, limit: int = 20) -> list[dict[str, str]]:
        """Return metadata for recent sessions, sorted by last update."""
        sessions: list[dict[str, str]] = []
        for session_file in sorted(
            self.sessions_dir.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        ):
            try:
                raw = session_file.read_text(encoding="utf-8")
                data = json.loads(raw)
                sessions.append({
                    "id": data.get("id", session_file.stem),
                    "title": data.get("title", ""),
                    "updated_at": data.get("updated_at", ""),
                    "messages": str(len(data.get("messages", []))),
                })
            except (json.JSONDecodeError, KeyError):
                continue

            if len(sessions) >= limit:
                break

        return sessions

    def load_or_create(self, session_id: str | None = None) -> Session:
        """Load the most recent session, or create one if none exist."""
        if session_id:
            loaded = self.load_session(session_id)
            if loaded:
                return loaded

        # Try loading the most recent session
        recent = self.list_sessions(limit=1)
        if recent:
            loaded = self.load_session(recent[0]["id"])
            if loaded:
                return loaded

        return self.create_session(session_id)

    def compact_session(
        self,
        session: Session | None = None,
        summarizer: Any = None,
    ) -> bool:
        """Compact older messages into a summary to reduce context size.

        If ``summarizer`` is provided, it is called with the older messages to
        produce a summary string.  Otherwise, a simple concatenation is used.
        """
        session = session or self._active_session
        if session is None or session.message_count <= COMPACTION_TRIGGER:
            return False

        keep_count = MAX_FULL_MESSAGES
        older_messages = session.messages[:-keep_count]
        recent_messages = session.messages[-keep_count:]

        if summarizer is not None:
            try:
                summary_text = summarizer(older_messages)
            except Exception as error:
                logger.warning("Compaction summarizer failed: {}", error)
                summary_text = self._simple_summary(older_messages)
        else:
            summary_text = self._simple_summary(older_messages)

        summary_message = Message(
            role="summary",
            content=f"[Compacted summary of {len(older_messages)} earlier messages]\n\n{summary_text}",
        )

        session.messages = [summary_message] + recent_messages
        session.compacted = True
        self.save(session)
        logger.info(
            "Compacted session '{}': {} messages summarized into 1",
            session.id,
            len(older_messages),
        )
        return True

    def _simple_summary(self, messages: list[Message]) -> str:
        """Create a basic summary by extracting key user requests."""
        user_messages = [m.content for m in messages if m.role == "user"]
        if not user_messages:
            return "No user messages in compacted range."
        return "Earlier topics discussed: " + "; ".join(
            msg[:120] for msg in user_messages[-10:]
        )
