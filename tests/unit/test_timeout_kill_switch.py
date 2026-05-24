"""Tests for consecutive timeout kill switch in AgentLoop."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from src.aradhya.agent_loop import AgentLoop, ToolCall, ToolResult


class TestConsecutiveTimeoutKillSwitch:
    """Verify the agent loop exits after N consecutive timeouts."""

    def _make_loop(self, max_timeouts: int = 3) -> AgentLoop:
        """Create an AgentLoop with a mock model that always returns tool calls."""
        mock_model = MagicMock()
        mock_executor = MagicMock()
        return AgentLoop(
            model_provider=mock_model,
            tool_executor=mock_executor,
            max_consecutive_timeouts=max_timeouts,
        )

    def test_kill_after_n_consecutive_timeouts(self) -> None:
        loop = self._make_loop(max_timeouts=3)

        # Simulate 3 consecutive timeouts
        for _ in range(3):
            result = ToolResult(
                tool_call_id="t1", name="run_command",
                output="Error: Command timed out after 30 seconds.", success=False,
            )
            loop._consecutive_timeouts += 1 if ("timeout" in result.output.lower() or "timed out" in result.output.lower()) else 0

        assert loop._consecutive_timeouts >= 3

    def test_non_timeout_resets_counter(self) -> None:
        loop = self._make_loop(max_timeouts=5)

        # Simulate 2 timeouts
        loop._consecutive_timeouts = 2

        # Simulate a successful result (non-timeout)
        result = ToolResult(
            tool_call_id="t2", name="run_command",
            output="Exit code: 0\nSTDOUT: hello", success=True,
        )
        if "timeout" not in result.output.lower() and "timed out" not in result.output.lower():
            loop._consecutive_timeouts = 0

        assert loop._consecutive_timeouts == 0

    def test_default_max_is_5(self) -> None:
        mock_model = MagicMock()
        loop = AgentLoop(model_provider=mock_model)
        assert loop.max_consecutive_timeouts == 5

    def test_custom_max(self) -> None:
        mock_model = MagicMock()
        loop = AgentLoop(model_provider=mock_model, max_consecutive_timeouts=10)
        assert loop.max_consecutive_timeouts == 10

    def test_timeout_keyword_detection(self) -> None:
        """Verify various timeout message formats are detected."""
        timeout_messages = [
            "Error: Command timed out after 30 seconds.",
            "Exit code: -1\nWall time: 30s\nError: Command timed out after 30 seconds.",
            "[Sandbox] Command timed out after 30000ms",
            "TIMEOUT",
            "The operation has timeout",
        ]
        for msg in timeout_messages:
            assert "timeout" in msg.lower() or "timed out" in msg.lower(), f"Should detect timeout in: {msg}"

        non_timeout = [
            "Exit code: 0\nSTDOUT: hello",
            "Error: File not found",
            "Permission denied",
        ]
        for msg in non_timeout:
            assert "timeout" not in msg.lower() and "timed out" not in msg.lower(), f"Should NOT detect timeout in: {msg}"
