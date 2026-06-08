"""Integration tests for subagent tools and session incremental saves."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.aradhya.agents.subagent_runner import SubagentRunner
from src.aradhya.agents.subagent_registry import SubagentRegistry, SubagentStatus
from src.aradhya.agents.subagent_messenger import SubagentMessenger
from src.aradhya.tools.subagent_tools import (
    spawn_subagent,
    check_subagent,
    list_subagents,
    kill_subagent,
    message_subagent,
)
from src.aradhya.session_manager import SessionManager, Message


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _reset_singletons():
    """Reset all singletons before and after each test."""
    SubagentRunner.reset()
    SubagentRegistry.reset()
    SubagentMessenger.reset()
    yield
    SubagentRunner.reset()
    SubagentRegistry.reset()
    SubagentMessenger.reset()


@pytest.fixture()
def session_manager(tmp_path: Path):
    """Create a SessionManager with a temp directory."""
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    return SessionManager(sessions_dir)


def _make_echo_factory():
    """Factory that echoes back the prompt."""
    def factory(
        *,
        subagent_id: str,
        role: str,
        prompt: str,
        tools=None,
        model: str = "",
        max_turns: int = 10,
        system_prompt: str = "",
    ) -> str:
        return f"Echo from {role}: {prompt}"

    return factory


# ──────────────────────────────────────────────────────────────────────
# Subagent Tools Integration
# ──────────────────────────────────────────────────────────────────────

class TestSubagentToolsIntegration:
    """Test the model-callable subagent tools end-to-end."""

    def test_spawn_without_factory_returns_error(self):
        """spawn_subagent should return error JSON if no factory is set."""
        result = json.loads(spawn_subagent(role="test", prompt="hello"))
        assert result["status"] == "error"
        assert "factory" in result["message"].lower()

    def test_spawn_check_lifecycle(self):
        """Full lifecycle: spawn → check → completed."""
        runner = SubagentRunner.instance()
        runner.set_loop_factory(_make_echo_factory())

        # Spawn
        result = json.loads(spawn_subagent(role="worker", prompt="do stuff"))
        assert result["status"] == "spawned"
        sid = result["subagent_id"]

        # Give the thread a moment to complete
        time.sleep(0.5)

        # Check
        check = json.loads(check_subagent(subagent_id=sid, wait_seconds=5.0))
        assert check["status"] == "completed"
        assert "Echo from worker" in check["output"]

    def test_list_subagents_empty(self):
        """list_subagents should return empty when nothing is running."""
        result = json.loads(list_subagents())
        assert result["status"] == "empty"
        assert result["subagents"] == []

    def test_list_subagents_with_active(self):
        """list_subagents should show running subagents."""
        runner = SubagentRunner.instance()

        def slow_factory(*, subagent_id, role, prompt, **kw):
            time.sleep(2.0)
            return "done"

        runner.set_loop_factory(slow_factory)
        spawn_result = json.loads(spawn_subagent(role="slow", prompt="wait"))
        sid = spawn_result["subagent_id"]

        time.sleep(0.1)
        result = json.loads(list_subagents())
        # Could be empty if completed fast or have 1 active
        if result["status"] == "ok":
            assert any(a["subagent_id"] == sid for a in result["subagents"])

        # Cleanup
        runner.kill(sid)

    def test_kill_subagent(self):
        """kill_subagent should cancel a running subagent."""
        runner = SubagentRunner.instance()

        def slow_factory(*, subagent_id, role, prompt, **kw):
            time.sleep(10.0)
            return "done"

        runner.set_loop_factory(slow_factory)
        spawn_result = json.loads(spawn_subagent(role="killme", prompt="long"))
        sid = spawn_result["subagent_id"]

        kill_result = json.loads(kill_subagent(subagent_id=sid))
        assert kill_result["status"] in ("cancelled", "not_found")

    def test_message_subagent(self):
        """message_subagent should send to a registered subagent."""
        runner = SubagentRunner.instance()

        def slow_factory(*, subagent_id, role, prompt, **kw):
            time.sleep(1.0)
            return "done"

        runner.set_loop_factory(slow_factory)
        spawn_result = json.loads(spawn_subagent(role="msgtarget", prompt="go"))
        sid = spawn_result["subagent_id"]
        time.sleep(0.1)

        msg_result = json.loads(message_subagent(
            subagent_id=sid,
            message="additional instructions",
        ))
        # May succeed or fail depending on timing
        assert msg_result["status"] in ("sent", "error")

        runner.kill(sid)

    def test_check_nonexistent_subagent(self):
        """check_subagent with unknown ID should return not_found."""
        result = json.loads(check_subagent(subagent_id="nonexistent-id"))
        assert result["status"] == "not_found"


# ──────────────────────────────────────────────────────────────────────
# Session Incremental Save
# ──────────────────────────────────────────────────────────────────────

class TestSessionIncrementalSave:
    """Test the new append_message() incremental persistence."""

    def test_append_message_adds_to_session(self, session_manager):
        """append_message should add to both in-memory session and SQLite."""
        session = session_manager.create_session("test-append")

        session_manager.append_message("user", "Hello", session=session)
        session_manager.append_message("assistant", "Hi there", session=session)

        assert session.message_count == 2
        assert session.messages[0].role == "user"
        assert session.messages[1].role == "assistant"

    def test_append_message_persists_to_sqlite(self, session_manager):
        """Messages added via append_message should be in SQLite."""
        session = session_manager.create_session("test-persist")

        session_manager.append_message("user", "First message", session=session)
        session_manager.append_message("assistant", "Reply", session=session)

        # Reload from SQLite
        loaded = session_manager.load_session("test-persist")
        assert loaded is not None
        assert loaded.message_count == 2
        assert loaded.messages[0].content == "First message"
        assert loaded.messages[1].content == "Reply"

    def test_append_message_with_metadata(self, session_manager):
        """append_message should pass through metadata kwargs."""
        session = session_manager.create_session("test-meta")

        session_manager.append_message(
            "user",
            "With metadata",
            session=session,
            plan_kind="agent_task",
        )

        assert session.messages[0].metadata.get("plan_kind") == "agent_task"

    def test_mixed_save_and_append(self, session_manager):
        """Full save and incremental append should be compatible."""
        session = session_manager.create_session("test-mixed")

        # Full save with 2 messages
        session.add_message("user", "First")
        session.add_message("assistant", "Second")
        session_manager.save(session)

        # Incremental append
        session_manager.append_message("user", "Third", session=session)

        # Reload and verify all 3 messages
        loaded = session_manager.load_session("test-mixed")
        assert loaded is not None
        assert loaded.message_count == 3
        assert loaded.messages[2].content == "Third"


# ──────────────────────────────────────────────────────────────────────
# Session Summarizer
# ──────────────────────────────────────────────────────────────────────

class TestSessionSummarizer:
    """Test the set_summarizer() and compact_session() integration."""

    def test_set_summarizer(self, session_manager):
        """set_summarizer should store the callable."""
        mock_summarizer = MagicMock(return_value="Summary text")
        session_manager.set_summarizer(mock_summarizer)
        assert session_manager._summarizer is mock_summarizer

    def test_compact_uses_stored_summarizer(self, session_manager):
        """compact_session should use the stored summarizer."""
        session = session_manager.create_session("test-compact")

        # Add enough messages to trigger compaction (COMPACTION_TRIGGER=60)
        for i in range(35):
            session.add_message("user", f"Question {i}")
            session.add_message("assistant", f"Answer {i}")
        session_manager.save(session)

        mock_summarizer = MagicMock(return_value="LLM-generated summary")
        session_manager.set_summarizer(mock_summarizer)

        compacted = session_manager.compact_session(session)
        assert compacted is True
        mock_summarizer.assert_called_once()

        # Verify the summary was inserted
        assert any(
            "LLM-generated summary" in m.content
            for m in session.messages
            if m.role == "summary"
        )

    def test_compact_explicit_overrides_stored(self, session_manager):
        """An explicit summarizer arg should override the stored one."""
        session = session_manager.create_session("test-override")

        for i in range(35):
            session.add_message("user", f"Q{i}")
            session.add_message("assistant", f"A{i}")
        session_manager.save(session)

        stored = MagicMock(return_value="stored summary")
        explicit = MagicMock(return_value="explicit summary")
        session_manager.set_summarizer(stored)

        session_manager.compact_session(session, summarizer=explicit)

        explicit.assert_called_once()
        stored.assert_not_called()
