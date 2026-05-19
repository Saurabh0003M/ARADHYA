"""SQLite-backed state store for sessions, messages, and audit events.

Replaces loose JSON files with a single ``state.sqlite`` database that
provides atomic writes, instant queries, and crash recovery.  Inspired
by Codex's ``state_5.sqlite`` + ``logs_2.sqlite`` dual-store model.

Schema
------
- ``sessions`` – one row per conversation session
- ``messages`` – one row per message in a session (FK → sessions)
- ``audit_events`` – immutable event log (mirrors JSONL audit trail)

The module is designed to be used by ``SessionManager`` and can also be
queried directly for cross-session search and analytics.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator

from loguru import logger

DEFAULT_STATE_DIR = Path.home() / ".aradhya"
DB_FILENAME = "state.sqlite"
SCHEMA_VERSION = 1


# ── Schema DDL ────────────────────────────────────────────────────────

_SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    compacted   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role        TEXT NOT NULL,
    content     TEXT NOT NULL,
    timestamp   TEXT NOT NULL,
    metadata    TEXT NOT NULL DEFAULT '{}',
    sort_order  INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_messages_session
    ON messages(session_id, sort_order);

CREATE TABLE IF NOT EXISTS audit_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL DEFAULT '',
    turn_id     TEXT NOT NULL DEFAULT '',
    event_type  TEXT NOT NULL,
    payload     TEXT NOT NULL DEFAULT '{}',
    ts          TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_session
    ON audit_events(session_id, ts);
CREATE INDEX IF NOT EXISTS idx_audit_type
    ON audit_events(event_type, ts);
"""


class StateStore:
    """Thread-safe SQLite state store for Aradhya.

    Usage::

        store = StateStore()           # opens/creates ~/.aradhya/state.sqlite
        store.upsert_session(...)
        store.add_message(...)
        sessions = store.list_sessions()
    """

    def __init__(self, state_dir: Path | None = None) -> None:
        self._dir = state_dir or DEFAULT_STATE_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._db_path = self._dir / DB_FILENAME
        self._local = threading.local()
        self._initialize_schema()

    @property
    def db_path(self) -> Path:
        return self._db_path

    # ── Connection management ─────────────────────────────────────────

    def _get_connection(self) -> sqlite3.Connection:
        """Return a thread-local connection (one per thread)."""
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(
                str(self._db_path),
                timeout=10,
                check_same_thread=False,
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA foreign_keys = ON")
            self._local.conn = conn
        return conn

    @contextmanager
    def _transaction(self) -> Generator[sqlite3.Cursor, None, None]:
        """Context manager for an atomic transaction."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def _initialize_schema(self) -> None:
        """Create tables if they don't exist."""
        conn = self._get_connection()
        conn.executescript(_SCHEMA_SQL)

        # Check/set schema version
        cursor = conn.execute("SELECT version FROM schema_version LIMIT 1")
        row = cursor.fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO schema_version (version) VALUES (?)",
                (SCHEMA_VERSION,),
            )
            conn.commit()

    def close(self) -> None:
        """Close the thread-local connection."""
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    # ── Session CRUD ──────────────────────────────────────────────────

    def upsert_session(
        self,
        session_id: str,
        title: str = "",
        created_at: str = "",
        updated_at: str = "",
        compacted: bool = False,
    ) -> None:
        """Insert or update a session record."""
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._transaction() as cur:
            cur.execute(
                """
                INSERT INTO sessions (id, title, created_at, updated_at, compacted)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title = excluded.title,
                    updated_at = excluded.updated_at,
                    compacted = excluded.compacted
                """,
                (
                    session_id,
                    title,
                    created_at or now,
                    updated_at or now,
                    int(compacted),
                ),
            )

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        """Load session metadata by ID."""
        conn = self._get_connection()
        row = conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "title": row["title"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "compacted": bool(row["compacted"]),
        }

    def delete_session(self, session_id: str) -> None:
        """Delete a session and all its messages."""
        with self._transaction() as cur:
            cur.execute("DELETE FROM sessions WHERE id = ?", (session_id,))

    def list_sessions(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return recent sessions sorted by last update (descending)."""
        conn = self._get_connection()
        rows = conn.execute(
            """
            SELECT s.*, COUNT(m.id) AS message_count
            FROM sessions s
            LEFT JOIN messages m ON m.session_id = s.id
            GROUP BY s.id
            ORDER BY s.updated_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [
            {
                "id": r["id"],
                "title": r["title"],
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
                "compacted": bool(r["compacted"]),
                "messages": str(r["message_count"]),
            }
            for r in rows
        ]

    def search_sessions(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Search sessions by title (case-insensitive LIKE)."""
        conn = self._get_connection()
        rows = conn.execute(
            """
            SELECT s.*, COUNT(m.id) AS message_count
            FROM sessions s
            LEFT JOIN messages m ON m.session_id = s.id
            WHERE s.title LIKE ?
            GROUP BY s.id
            ORDER BY s.updated_at DESC
            LIMIT ?
            """,
            (f"%{query}%", limit),
        ).fetchall()
        return [
            {
                "id": r["id"],
                "title": r["title"],
                "updated_at": r["updated_at"],
                "messages": str(r["message_count"]),
            }
            for r in rows
        ]

    # ── Message CRUD ──────────────────────────────────────────────────

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        timestamp: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """Insert a message and return its row ID."""
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        meta_json = json.dumps(metadata or {}, default=str, ensure_ascii=False)

        with self._transaction() as cur:
            # Get the next sort_order for this session
            row = cur.execute(
                "SELECT COALESCE(MAX(sort_order), -1) + 1 AS next_order "
                "FROM messages WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            next_order = row["next_order"] if row else 0

            cur.execute(
                """
                INSERT INTO messages (session_id, role, content, timestamp, metadata, sort_order)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (session_id, role, content, timestamp or now, meta_json, next_order),
            )

            # Touch the session's updated_at
            cur.execute(
                "UPDATE sessions SET updated_at = ? WHERE id = ?",
                (now, session_id),
            )
            return cur.lastrowid or 0

    def get_messages(
        self,
        session_id: str,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Return messages for a session, ordered chronologically.

        If ``limit`` is set, returns the last N messages.
        """
        conn = self._get_connection()

        if limit is not None:
            rows = conn.execute(
                """
                SELECT * FROM (
                    SELECT * FROM messages
                    WHERE session_id = ?
                    ORDER BY sort_order DESC
                    LIMIT ?
                ) sub ORDER BY sort_order ASC
                """,
                (session_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM messages WHERE session_id = ? ORDER BY sort_order ASC",
                (session_id,),
            ).fetchall()

        return [
            {
                "id": r["id"],
                "role": r["role"],
                "content": r["content"],
                "timestamp": r["timestamp"],
                "metadata": json.loads(r["metadata"]) if r["metadata"] else {},
            }
            for r in rows
        ]

    def replace_messages(
        self,
        session_id: str,
        messages: list[dict[str, Any]],
    ) -> None:
        """Atomically replace all messages in a session (used for compaction)."""
        with self._transaction() as cur:
            cur.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            for i, msg in enumerate(messages):
                meta_json = json.dumps(
                    msg.get("metadata", {}), default=str, ensure_ascii=False
                )
                cur.execute(
                    """
                    INSERT INTO messages (session_id, role, content, timestamp, metadata, sort_order)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        msg["role"],
                        msg["content"],
                        msg.get("timestamp", ""),
                        meta_json,
                        i,
                    ),
                )
            cur.execute(
                "UPDATE sessions SET compacted = 1 WHERE id = ?",
                (session_id,),
            )

    def message_count(self, session_id: str) -> int:
        """Return the number of messages in a session."""
        conn = self._get_connection()
        row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM messages WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return row["cnt"] if row else 0

    # ── Audit events ──────────────────────────────────────────────────

    def log_audit_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        session_id: str = "",
        turn_id: str = "",
        ts: str = "",
    ) -> None:
        """Insert an audit event."""
        now = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        payload_json = json.dumps(payload, default=str, ensure_ascii=False)
        with self._transaction() as cur:
            cur.execute(
                """
                INSERT INTO audit_events (session_id, turn_id, event_type, payload, ts)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, turn_id, event_type, payload_json, ts or now),
            )

    def recent_audit_events(
        self,
        count: int = 20,
        event_type: str | None = None,
        session_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Query recent audit events with optional filters."""
        conn = self._get_connection()
        clauses: list[str] = []
        params: list[Any] = []

        if event_type:
            clauses.append("event_type = ?")
            params.append(event_type)
        if session_id:
            clauses.append("session_id = ?")
            params.append(session_id)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(count)

        rows = conn.execute(
            f"""
            SELECT * FROM audit_events
            {where}
            ORDER BY id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()

        return [
            {
                "id": r["id"],
                "session_id": r["session_id"],
                "turn_id": r["turn_id"],
                "event_type": r["event_type"],
                "payload": json.loads(r["payload"]) if r["payload"] else {},
                "ts": r["ts"],
            }
            for r in reversed(rows)  # Return in chronological order
        ]

    # ── Migration ─────────────────────────────────────────────────────

    def migrate_json_sessions(self, sessions_dir: Path) -> int:
        """Import existing JSON session files into SQLite.

        Returns the number of sessions migrated.
        """
        if not sessions_dir.is_dir():
            return 0

        migrated = 0
        for session_file in sessions_dir.glob("*.json"):
            if session_file.name == "session_index.jsonl":
                continue
            try:
                raw = session_file.read_text(encoding="utf-8")
                data = json.loads(raw)
                session_id = data.get("id", session_file.stem)

                # Skip if already migrated
                if self.get_session(session_id) is not None:
                    continue

                self.upsert_session(
                    session_id=session_id,
                    title=data.get("title", ""),
                    created_at=data.get("created_at", ""),
                    updated_at=data.get("updated_at", ""),
                    compacted=data.get("compacted", False),
                )

                for i, msg in enumerate(data.get("messages", [])):
                    meta_json = json.dumps(
                        msg.get("metadata", {}), default=str, ensure_ascii=False
                    )
                    conn = self._get_connection()
                    conn.execute(
                        """
                        INSERT INTO messages
                            (session_id, role, content, timestamp, metadata, sort_order)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            session_id,
                            msg.get("role", "user"),
                            msg.get("content", ""),
                            msg.get("timestamp", ""),
                            meta_json,
                            i,
                        ),
                    )
                    conn.commit()

                migrated += 1
                logger.info(
                    "Migrated session '{}' ({} messages)",
                    session_id,
                    len(data.get("messages", [])),
                )
            except (json.JSONDecodeError, KeyError, OSError) as error:
                logger.warning("Failed to migrate '{}': {}", session_file.name, error)
                continue

        return migrated

    def migrate_audit_jsonl(self, audit_path: Path) -> int:
        """Import existing JSONL audit entries into SQLite.

        Returns the number of events imported.
        """
        if not audit_path.is_file():
            return 0

        imported = 0
        try:
            for line in audit_path.read_text(encoding="utf-8").strip().splitlines():
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                event_type = entry.pop("type", "unknown")
                ts = entry.pop("ts", "")
                session_id = entry.pop("session_id", "")
                turn_id = entry.pop("turn_id", "")
                entry.pop("pid", None)  # Don't store PID in payload

                self.log_audit_event(
                    event_type=event_type,
                    payload=entry,
                    session_id=session_id,
                    turn_id=turn_id,
                    ts=ts,
                )
                imported += 1
        except OSError as error:
            logger.warning("Failed to read audit JSONL: {}", error)

        return imported
