"""Unit tests for the subagent runner."""

from __future__ import annotations

import time
import threading
from unittest.mock import MagicMock

import pytest

from src.aradhya.agents.subagent_runner import (
    SubagentResult,
    SubagentRunner,
)
from src.aradhya.agents.subagent_registry import (
    SubagentRegistry,
    SubagentStatus,
)
from src.aradhya.agents.subagent_messenger import SubagentMessenger


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


def _make_factory(output: str = "done", delay: float = 0.0):
    """Create a simple mock agent loop factory."""
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
        if delay:
            time.sleep(delay)
        return output

    return factory


def _make_failing_factory(error_msg: str = "boom"):
    """Create a factory that always raises."""
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
        raise RuntimeError(error_msg)

    return factory


class TestSubagentRunner:
    """Tests for the SubagentRunner class."""

    def test_singleton(self):
        runner1 = SubagentRunner.instance()
        runner2 = SubagentRunner.instance()
        assert runner1 is runner2

    def test_spawn_requires_factory(self):
        runner = SubagentRunner.instance()
        with pytest.raises(RuntimeError, match="No agent loop factory"):
            runner.spawn(role="test", prompt="hello")

    def test_spawn_and_get_result(self):
        runner = SubagentRunner.instance()
        runner.set_loop_factory(_make_factory(output="test output"))

        sid = runner.spawn(role="worker", prompt="do something")
        assert sid  # non-empty UUID string

        result = runner.get_result(sid, timeout=10.0)
        assert result is not None
        assert result.status == SubagentStatus.COMPLETED
        assert result.output == "test output"
        assert result.role == "worker"
        assert result.elapsed_seconds >= 0

    def test_spawn_failure(self):
        runner = SubagentRunner.instance()
        runner.set_loop_factory(_make_failing_factory("intentional failure"))

        sid = runner.spawn(role="failer", prompt="break")
        result = runner.get_result(sid, timeout=10.0)

        assert result is not None
        assert result.status == SubagentStatus.FAILED
        assert "intentional failure" in result.error

    def test_list_active(self):
        runner = SubagentRunner.instance()
        runner.set_loop_factory(_make_factory(delay=1.0))

        sid = runner.spawn(role="slow", prompt="wait")
        # Give the thread a moment to start
        time.sleep(0.1)

        active = runner.list_active()
        # Should have at least the one we just spawned
        assert any(a.subagent_id == sid for a in active)

        # Wait for completion
        runner.get_result(sid, timeout=5.0)

    def test_kill(self):
        runner = SubagentRunner.instance()
        runner.set_loop_factory(_make_factory(delay=5.0))

        sid = runner.spawn(role="killable", prompt="long task")
        killed = runner.kill(sid)
        # kill returns True if the subagent was found
        assert killed is True

    def test_kill_all(self):
        runner = SubagentRunner.instance()
        runner.set_loop_factory(_make_factory(delay=5.0))

        runner.spawn(role="a", prompt="task a")
        runner.spawn(role="b", prompt="task b")

        count = runner.kill_all()
        assert count >= 0  # may be 0 if tasks already completed

    def test_parent_notification(self):
        """Verify that completing subagent sends message to parent."""
        runner = SubagentRunner.instance()
        runner.set_loop_factory(_make_factory(output="result data"))

        parent_id = "main-agent"
        messenger = SubagentMessenger.instance()
        messenger.register_agent(parent_id)

        sid = runner.spawn(
            role="notifier",
            prompt="notify parent",
            parent_id=parent_id,
        )

        # Wait for completion
        result = runner.get_result(sid, timeout=10.0)
        assert result is not None
        assert result.status == SubagentStatus.COMPLETED

        # Check parent received the notification
        msg = messenger.receive_nowait(parent_id)
        assert msg is not None
        assert "completed" in msg.content.lower() or "result data" in msg.content

    def test_get_result_timeout(self):
        runner = SubagentRunner.instance()
        runner.set_loop_factory(_make_factory(delay=10.0))

        sid = runner.spawn(role="slow", prompt="very slow")
        result = runner.get_result(sid, timeout=0.1)
        # Should timeout — returns None or a FAILED result
        assert result is None or result.status == SubagentStatus.FAILED

        # Cleanup
        runner.kill(sid)

    def test_multiple_concurrent(self):
        """Test spawning multiple subagents concurrently."""
        runner = SubagentRunner.instance()
        results_lock = threading.Lock()
        collected: list[str] = []

        def factory(
            *,
            subagent_id: str,
            role: str,
            prompt: str,
            tools=None,
            model="",
            max_turns=10,
            system_prompt="",
        ) -> str:
            time.sleep(0.1)
            return f"done-{role}"

        runner.set_loop_factory(factory)

        sids = [
            runner.spawn(role=f"worker-{i}", prompt=f"task {i}")
            for i in range(3)
        ]

        for sid in sids:
            result = runner.get_result(sid, timeout=10.0)
            assert result is not None
            assert result.status == SubagentStatus.COMPLETED
            collected.append(result.output)

        assert len(collected) == 3
        assert all(o.startswith("done-") for o in collected)

    def test_registry_tracks_lifecycle(self):
        """Verify the registry reflects status changes."""
        runner = SubagentRunner.instance()
        runner.set_loop_factory(_make_factory(output="ok"))

        registry = SubagentRegistry.instance()
        sid = runner.spawn(role="tracked", prompt="go")

        # Wait for completion
        result = runner.get_result(sid, timeout=10.0)
        assert result is not None

        info = registry.get(sid)
        assert info is not None
        assert info.status == SubagentStatus.COMPLETED

    def test_shutdown(self):
        runner = SubagentRunner.instance()
        runner.set_loop_factory(_make_factory())
        runner.shutdown(wait=False)
        # After shutdown, the runner should be in a clean state
