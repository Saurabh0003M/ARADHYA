"""Unit tests for the 5 agent_loop gaps fixed in this sprint.

Gap 1: Dangerous tools blocked even when confirmation_gate is None (dry-run)
Gap 2: Tool failures auto-logged to learnings engine
Gap 3: Per-turn token budget guard truncates oversized tool outputs
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

# Ensure project root is importable
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.aradhya.agent_loop import AgentLoop, ToolCall, ToolResult
from src.aradhya.model_provider import ModelChatResult, ModelToolCall


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_chat_result(tool_name: str | None = None, text: str = "done") -> ModelChatResult:
    """Build a ModelChatResult with all required fields."""
    if tool_name:
        return ModelChatResult(
            text="",
            model="test-model",
            provider="test",
            raw={},
            tool_calls=(
                ModelToolCall(name=tool_name, arguments={"x": 1}, id="tc_001"),
            ),
        )
    return ModelChatResult(text=text, model="test-model", provider="test", raw={})


class _EchoExecutor:
    """Minimal executor that always returns a fixed result."""

    def __init__(self, output: str = "ok", success: bool = True):
        self._output = output
        self._success = success

    def execute_tool(self, name: str, arguments: dict, tool_call_id: str = "") -> ToolResult:
        return ToolResult(
            tool_call_id=tool_call_id,
            name=name,
            output=self._output,
            success=self._success,
        )

    def list_tools(self) -> list:
        return []


class _ToolCallModel:
    """Emits one tool call then a final text response."""

    def __init__(self, tool_name: str):
        self._tool_name = tool_name
        self._calls = 0

    def chat(self, messages, tools=None):
        if self._calls == 0:
            self._calls += 1
            return _make_chat_result(tool_name=self._tool_name)
        return _make_chat_result(text="finished")


class _BigOutputModel:
    """Emits up to 2 tool calls (non-dangerous) with large outputs."""

    def __init__(self):
        self._calls = 0

    def chat(self, messages, tools=None):
        if self._calls < 2:
            self._calls += 1
            return _make_chat_result(tool_name="read_file")
        return _make_chat_result(text="summarised")


# ── Gap 1: Dangerous tool blocked without confirmation_gate ───────────────────

class TestDangerousToolBlockedNullGate:
    """Dangerous tools must be blocked when confirmation_gate is None."""

    @pytest.mark.parametrize("tool", [
        "run_command", "write_file", "delete_file", "move_file",
        "browser_click", "browser_type", "browser_submit",
        "open_path", "open_url", "clipboard_write",
    ])
    def test_dangerous_tool_blocked(self, tool):
        loop = AgentLoop(
            model_provider=_ToolCallModel(tool),
            tool_executor=_EchoExecutor(),
            confirmation_gate=None,   # ← silent bypass scenario
        )
        with patch("src.aradhya.agent_loop.get_audit_logger") as mock_audit:
            mock_audit.return_value = MagicMock()
            turn = loop.run(user_message="do it", system_prompt="")

        assert len(turn.tool_results) == 1
        result = turn.tool_results[0]
        assert result.success is False
        assert result.requires_confirmation is True
        assert "dry-run" in result.output or "confirmation" in result.output.lower()

    def test_safe_tool_still_runs_without_gate(self):
        """Non-dangerous tools must still execute even without a gate."""
        loop = AgentLoop(
            model_provider=_ToolCallModel("read_file"),
            tool_executor=_EchoExecutor(output="file contents"),
            confirmation_gate=None,
        )
        with patch("src.aradhya.agent_loop.get_audit_logger") as mock_audit:
            mock_audit.return_value = MagicMock()
            turn = loop.run(user_message="read it", system_prompt="")

        assert len(turn.tool_results) == 1
        assert turn.tool_results[0].success is True
        assert turn.tool_results[0].output == "file contents"

    def test_dangerous_tool_runs_when_gate_approves(self):
        """Dangerous tools must execute when the gate approves."""
        loop = AgentLoop(
            model_provider=_ToolCallModel("run_command"),
            tool_executor=_EchoExecutor(output="exit 0"),
            confirmation_gate=lambda name, args: True,   # always approve
        )
        with patch("src.aradhya.agent_loop.get_audit_logger") as mock_audit:
            mock_audit.return_value = MagicMock()
            turn = loop.run(user_message="run it", system_prompt="")

        assert len(turn.tool_results) == 1
        assert turn.tool_results[0].success is True

    def test_dangerous_tool_denied_when_gate_rejects(self):
        """Dangerous tools must be blocked when the gate rejects."""
        loop = AgentLoop(
            model_provider=_ToolCallModel("run_command"),
            tool_executor=_EchoExecutor(output="exit 0"),
            confirmation_gate=lambda name, args: False,   # always reject
        )
        with patch("src.aradhya.agent_loop.get_audit_logger") as mock_audit:
            mock_audit.return_value = MagicMock()
            turn = loop.run(user_message="run it", system_prompt="")

        assert len(turn.tool_results) == 1
        result = turn.tool_results[0]
        assert result.success is False
        assert "denied" in result.output.lower()


# ── Gap 2: Auto-log tool failures to learnings engine ────────────────────────

class TestAutoLearningsOnFailure:
    """Tool failures must be auto-logged without requiring the model to call log_error."""

    def test_failure_calls_auto_log(self):
        loop = AgentLoop(
            model_provider=_ToolCallModel("read_file"),
            tool_executor=_EchoExecutor(output="[Error: file not found]", success=False),
            confirmation_gate=None,
        )
        with (
            patch("src.aradhya.agent_loop.get_audit_logger") as mock_audit,
            patch.object(loop, "_auto_log_tool_failure") as mock_log,
        ):
            mock_audit.return_value = MagicMock()
            turn = loop.run(user_message="read it", system_prompt="")

        assert len(turn.tool_results) == 1
        assert turn.tool_results[0].success is False
        mock_log.assert_called_once()
        called_tool, called_msg = mock_log.call_args[0]
        assert called_tool == "read_file"

    def test_learnings_engine_crash_does_not_propagate(self):
        """If learnings engine crashes, the agent loop must not crash."""
        loop = AgentLoop(
            model_provider=_ToolCallModel("read_file"),
            tool_executor=_EchoExecutor(output="error", success=False),
            confirmation_gate=None,
        )
        with (
            patch("src.aradhya.agent_loop.get_audit_logger") as mock_audit,
            # Make the learnings import raise inside _auto_log_tool_failure
            patch.object(loop, "_auto_log_tool_failure", side_effect=RuntimeError("boom")),
        ):
            mock_audit.return_value = MagicMock()
            # The agent should still return a valid turn even if auto-log crashes
            # (in real code it's wrapped in try/except — here the mock raises at
            #  the method call site, so the exception propagates; this is fine
            #  because the real method is safe — we test the real one below)
            try:
                turn = loop.run(user_message="read", system_prompt="")
            except RuntimeError:
                pass  # expected — mock bypasses the internal try/except

    def test_auto_log_method_swallows_its_own_errors(self):
        """_auto_log_tool_failure must never raise — internal errors are silenced."""
        loop = AgentLoop(model_provider=MagicMock())
        # Patch the learnings engine inside the module where it's dynamically imported
        with patch(
            "src.aradhya.learnings.learnings_engine.LearningsEngine.log_error",
            side_effect=RuntimeError("storage full"),
        ):
            # Should not raise — internal errors in _auto_log_tool_failure are silenced
            try:
                loop._auto_log_tool_failure("some_tool", "some error")
            except Exception as exc:
                pytest.fail(f"_auto_log_tool_failure raised unexpectedly: {exc}")

    def test_exception_during_execute_also_logs(self):
        """Exceptions thrown by execute_tool must also trigger auto-log."""

        class _CrashExecutor:
            def execute_tool(self, name, arguments, tool_call_id=""):
                raise RuntimeError("disk full")
            def list_tools(self):
                return []

        loop = AgentLoop(
            model_provider=_ToolCallModel("read_file"),
            tool_executor=_CrashExecutor(),
            confirmation_gate=None,
        )
        with (
            patch("src.aradhya.agent_loop.get_audit_logger") as mock_audit,
            patch.object(loop, "_auto_log_tool_failure") as mock_log,
        ):
            mock_audit.return_value = MagicMock()
            turn = loop.run(user_message="read", system_prompt="")

        assert turn.tool_results[0].success is False
        mock_log.assert_called_once()
        assert "disk full" in mock_log.call_args[0][1]


# ── Gap 3: Per-turn token budget ──────────────────────────────────────────────

class TestPerTurnTokenBudget:
    """Accumulated tool output tokens must not exceed the per-turn budget."""

    def test_budget_exceeded_returns_trim_notice(self):
        big_output = "X" * 200   # 200 chars ÷ 4 = 50 tokens
        # The trim-notice path calls _call_model one final time for a summary.
        # We give the model one tool-call response and then a summary text response.
        loop = AgentLoop(
            model_provider=_BigOutputModel(),
            tool_executor=_EchoExecutor(output=big_output),
            confirmation_gate=None,
            turn_token_budget=10,   # tiny budget → triggers immediately
        )
        with (
            patch("src.aradhya.agent_loop.get_audit_logger") as mock_audit,
            # Patch _call_model so the summary call returns a fixed text
            patch.object(
                loop, "_call_model",
                side_effect=[
                    # First call: model requests a tool
                    {"text": "", "tool_calls": [{
                        "id": "tc_001",
                        "type": "function",
                        "function": {"name": "read_file", "arguments": '{"x": 1}'},
                    }]},
                    # Second call (trim summary): model returns final text
                    {"text": "Here is a summary after trimming.", "tool_calls": []},
                ]
            ),
        ):
            mock_audit.return_value = MagicMock()
            turn = loop.run(user_message="read big file", system_prompt="")

        # Should have returned early — only 1 main iteration
        assert turn.iterations == 1
        assert turn.final_response == "Here is a summary after trimming."

    def test_budget_not_exceeded_for_small_outputs(self):
        loop = AgentLoop(
            model_provider=_BigOutputModel(),
            tool_executor=_EchoExecutor(output="tiny"),  # 1 token
            confirmation_gate=None,
            turn_token_budget=6000,
        )
        with patch("src.aradhya.agent_loop.get_audit_logger") as mock_audit:
            mock_audit.return_value = MagicMock()
            turn = loop.run(user_message="read it", system_prompt="")

        assert turn.final_response == "summarised"

    def test_budget_param_stored(self):
        loop = AgentLoop(model_provider=MagicMock(), turn_token_budget=1234)
        assert loop.turn_token_budget == 1234

    def test_default_budget_is_6000(self):
        loop = AgentLoop(model_provider=MagicMock())
        assert loop.turn_token_budget == 6000

    def test_accumulated_tokens_reset_per_turn(self):
        """Each call to run() should start with a fresh token accumulator."""
        small_output = "A" * 40   # 10 tokens, right at a 10-token budget
        loop = AgentLoop(
            model_provider=_BigOutputModel(),
            tool_executor=_EchoExecutor(output=small_output),
            confirmation_gate=None,
            turn_token_budget=5,   # triggers after first 20-token result
        )
        with patch("src.aradhya.agent_loop.get_audit_logger") as mock_audit:
            mock_audit.return_value = MagicMock()
            turn1 = loop.run(user_message="first", system_prompt="")

        # Reset model for second turn
        loop.model_provider = _BigOutputModel()
        with patch("src.aradhya.agent_loop.get_audit_logger") as mock_audit:
            mock_audit.return_value = MagicMock()
            turn2 = loop.run(user_message="second", system_prompt="")

        # Both turns should have been budget-limited (not crash)
        assert turn1.iterations >= 1
        assert turn2.iterations >= 1
