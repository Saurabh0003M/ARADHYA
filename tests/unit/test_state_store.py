"""Tests for the SQLite state store and SQLite-backed session manager."""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Dependency handling lives in tests/conftest.py — see the note there on why
# module-level sys.modules mocks are gone.
from src.aradhya.state_store import StateStore
from src.aradhya.session_manager import Message, Session, SessionManager


# ── StateStore tests ──────────────────────────────────────────────────


def test_state_store_creates_database(tmp_path):
    store = StateStore(state_dir=tmp_path)
    assert (tmp_path / "state.sqlite").is_file()
    store.close()


def test_state_store_upsert_and_get_session(tmp_path):
    store = StateStore(state_dir=tmp_path)
    store.upsert_session(
        session_id="s1",
        title="Test Session",
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:01:00",
    )

    result = store.get_session("s1")
    assert result is not None
    assert result["id"] == "s1"
    assert result["title"] == "Test Session"
    assert result["compacted"] is False
    store.close()


def test_state_store_upsert_updates_existing(tmp_path):
    store = StateStore(state_dir=tmp_path)
    store.upsert_session(session_id="s1", title="Original")
    store.upsert_session(session_id="s1", title="Updated", updated_at="2026-06-01")

    result = store.get_session("s1")
    assert result["title"] == "Updated"
    store.close()


def test_state_store_list_sessions(tmp_path):
    store = StateStore(state_dir=tmp_path)
    store.upsert_session(session_id="s1", title="First", updated_at="2026-01-01")
    store.upsert_session(session_id="s2", title="Second", updated_at="2026-01-02")

    result = store.list_sessions(limit=10)
    assert len(result) == 2
    assert result[0]["id"] == "s2"  # Most recent first
    store.close()


def test_state_store_add_and_get_messages(tmp_path):
    store = StateStore(state_dir=tmp_path)
    store.upsert_session(session_id="s1", title="Chat")

    store.add_message("s1", "user", "Hello")
    store.add_message("s1", "assistant", "Hi there!")
    store.add_message("s1", "user", "How are you?")

    messages = store.get_messages("s1")
    assert len(messages) == 3
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Hello"
    assert messages[2]["content"] == "How are you?"
    store.close()


def test_state_store_get_messages_with_limit(tmp_path):
    store = StateStore(state_dir=tmp_path)
    store.upsert_session(session_id="s1", title="Chat")

    for i in range(10):
        store.add_message("s1", "user", f"Message {i}")

    # Get last 3 messages
    messages = store.get_messages("s1", limit=3)
    assert len(messages) == 3
    assert messages[0]["content"] == "Message 7"
    assert messages[2]["content"] == "Message 9"
    store.close()


def test_state_store_replace_messages(tmp_path):
    store = StateStore(state_dir=tmp_path)
    store.upsert_session(session_id="s1", title="Chat")

    store.add_message("s1", "user", "Old message 1")
    store.add_message("s1", "assistant", "Old message 2")

    # Replace with compacted version
    store.replace_messages("s1", [
        {"role": "summary", "content": "Compacted summary", "timestamp": ""},
        {"role": "user", "content": "Latest message", "timestamp": ""},
    ])

    messages = store.get_messages("s1")
    assert len(messages) == 2
    assert messages[0]["role"] == "summary"
    assert messages[1]["content"] == "Latest message"

    # Session should be marked as compacted
    session = store.get_session("s1")
    assert session["compacted"] is True
    store.close()


def test_state_store_message_count(tmp_path):
    store = StateStore(state_dir=tmp_path)
    store.upsert_session(session_id="s1", title="Chat")

    assert store.message_count("s1") == 0
    store.add_message("s1", "user", "Hello")
    assert store.message_count("s1") == 1
    store.add_message("s1", "assistant", "Hi")
    assert store.message_count("s1") == 2
    store.close()


def test_state_store_delete_session(tmp_path):
    store = StateStore(state_dir=tmp_path)
    store.upsert_session(session_id="s1", title="To Delete")
    store.add_message("s1", "user", "Will be deleted")

    store.delete_session("s1")
    assert store.get_session("s1") is None
    assert store.get_messages("s1") == []
    store.close()


def test_state_store_search_sessions(tmp_path):
    store = StateStore(state_dir=tmp_path)
    store.upsert_session(session_id="s1", title="Python debugging")
    store.upsert_session(session_id="s2", title="JavaScript setup")
    store.upsert_session(session_id="s3", title="Python testing")

    results = store.search_sessions("Python")
    assert len(results) == 2
    titles = {r["title"] for r in results}
    assert "Python debugging" in titles
    assert "Python testing" in titles
    store.close()


def test_state_store_audit_events(tmp_path):
    store = StateStore(state_dir=tmp_path)

    store.log_audit_event(
        event_type="tool_call",
        payload={"tool": "read_file", "success": True},
        session_id="s1",
        turn_id="t1",
    )
    store.log_audit_event(
        event_type="turn_start",
        payload={"user_message": "hello"},
        session_id="s1",
        turn_id="t1",
    )

    events = store.recent_audit_events(count=10)
    assert len(events) == 2
    assert events[0]["event_type"] == "tool_call"
    assert events[1]["event_type"] == "turn_start"
    store.close()


def test_state_store_audit_events_filter_by_type(tmp_path):
    store = StateStore(state_dir=tmp_path)
    store.log_audit_event("tool_call", {"tool": "a"}, session_id="s1")
    store.log_audit_event("security", {"event": "blocked"}, session_id="s1")
    store.log_audit_event("tool_call", {"tool": "b"}, session_id="s1")

    events = store.recent_audit_events(count=10, event_type="tool_call")
    assert len(events) == 2
    assert all(e["event_type"] == "tool_call" for e in events)
    store.close()


def test_state_store_migrate_json_sessions(tmp_path):
    # Create a legacy JSON session file
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    session_data = {
        "id": "legacy_session",
        "title": "Legacy Chat",
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:01:00",
        "compacted": False,
        "messages": [
            {"role": "user", "content": "Hello", "timestamp": "2026-01-01T00:00:00", "metadata": {}},
            {"role": "assistant", "content": "Hi!", "timestamp": "2026-01-01T00:00:01", "metadata": {}},
        ],
    }
    (sessions_dir / "legacy_session.json").write_text(
        json.dumps(session_data), encoding="utf-8"
    )

    store = StateStore(state_dir=tmp_path)
    count = store.migrate_json_sessions(sessions_dir)
    assert count == 1

    # Verify migrated data
    session = store.get_session("legacy_session")
    assert session is not None
    assert session["title"] == "Legacy Chat"

    messages = store.get_messages("legacy_session")
    assert len(messages) == 2
    assert messages[0]["content"] == "Hello"
    store.close()


def test_state_store_migrate_skips_already_migrated(tmp_path):
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    (sessions_dir / "existing.json").write_text(
        json.dumps({"id": "existing", "title": "Already There", "messages": []}),
        encoding="utf-8",
    )

    store = StateStore(state_dir=tmp_path)
    store.upsert_session(session_id="existing", title="Already There")

    count = store.migrate_json_sessions(sessions_dir)
    assert count == 0  # Should skip
    store.close()


# ── SessionManager (SQLite-backed) tests ──────────────────────────────


def test_session_manager_creates_session_in_sqlite(tmp_path):
    mgr = SessionManager(
        sessions_dir=tmp_path / "sessions",
        state_store=StateStore(state_dir=tmp_path),
    )
    session = mgr.create_session("test_session")
    assert session.id == "test_session"

    # Verify it's in SQLite
    result = mgr.store.get_session("test_session")
    assert result is not None
    assert result["id"] == "test_session"


def test_session_manager_save_and_load(tmp_path):
    store = StateStore(state_dir=tmp_path)
    mgr = SessionManager(sessions_dir=tmp_path / "sessions", state_store=store)

    session = mgr.create_session("s1")
    session.add_message("user", "Hello")
    session.add_message("assistant", "Hi there!")
    mgr.save(session)

    # Create fresh manager to force reload from SQLite
    mgr2 = SessionManager(sessions_dir=tmp_path / "sessions", state_store=store)
    loaded = mgr2.load_session("s1")
    assert loaded is not None
    assert loaded.message_count == 2
    assert loaded.messages[0].content == "Hello"
    assert loaded.messages[1].content == "Hi there!"


def test_session_manager_list_sessions_from_sqlite(tmp_path):
    store = StateStore(state_dir=tmp_path)
    mgr = SessionManager(sessions_dir=tmp_path / "sessions", state_store=store)

    mgr.create_session("s1")
    mgr.create_session("s2")

    sessions = mgr.list_sessions()
    assert len(sessions) == 2


def test_session_manager_search_sessions(tmp_path):
    store = StateStore(state_dir=tmp_path)
    mgr = SessionManager(sessions_dir=tmp_path / "sessions", state_store=store)

    s1 = mgr.create_session("s1")
    s1.title = "Python debugging"
    mgr.save(s1)

    s2 = mgr.create_session("s2")
    s2.title = "JavaScript setup"
    mgr.save(s2)

    results = mgr.search_sessions("Python")
    assert len(results) == 1
    assert results[0]["title"] == "Python debugging"


def test_session_manager_load_or_create(tmp_path):
    store = StateStore(state_dir=tmp_path)
    mgr = SessionManager(sessions_dir=tmp_path / "sessions", state_store=store)

    # Should create a new session
    session = mgr.load_or_create("new_session")
    assert session.id == "new_session"

    # Should load the existing session
    loaded = mgr.load_or_create("new_session")
    assert loaded.id == "new_session"


def test_session_manager_auto_migrates_json(tmp_path):
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir(parents=True)

    # Write a legacy JSON session
    legacy = {
        "id": "old_session",
        "title": "Legacy",
        "created_at": "2026-01-01",
        "updated_at": "2026-01-01",
        "compacted": False,
        "messages": [
            {"role": "user", "content": "Old message", "timestamp": "", "metadata": {}},
        ],
    }
    (sessions_dir / "old_session.json").write_text(
        json.dumps(legacy), encoding="utf-8"
    )

    store = StateStore(state_dir=tmp_path)
    mgr = SessionManager(sessions_dir=sessions_dir, state_store=store)

    # list_sessions should trigger auto-migration
    sessions = mgr.list_sessions()
    assert len(sessions) >= 1

    # Load the migrated session
    loaded = mgr.load_session("old_session")
    assert loaded is not None
    assert loaded.title == "Legacy"
    assert loaded.message_count == 1
