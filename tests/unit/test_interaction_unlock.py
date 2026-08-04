"""Tests for the session-level interaction unlock (the floating icon's "I").

The point of these tests is the safety boundary, not the feature. Unlocking
grants live execution for one session; it must NOT weaken the confirmed-task
grant, the path confinement, or persist anything to preferences.
"""

from __future__ import annotations

from pathlib import Path

from src.aradhya.assistant_models import AssistantState
from src.aradhya.tools.runtime_policy import ToolRuntimePolicy


class TestDefaults:
    def test_unlock_is_off_by_default(self) -> None:
        """A fresh session must never inherit permission to act."""
        assert AssistantState().interaction_unlocked is False


class TestPolicyEffect:
    """`live_execution_enabled` should be (preference OR session unlock)."""

    def _policy(self, *, pref: bool, unlocked: bool, granted: bool = True) -> ToolRuntimePolicy:
        return ToolRuntimePolicy(
            allowed_roots=(Path.cwd(),),
            live_execution_enabled=pref or unlocked,
            mutation_granted=granted,
        )

    def test_locked_blocks_mutating_tool(self) -> None:
        decision = self._policy(pref=False, unlocked=False).check(
            "write_file", {"path": str(Path.cwd() / "x.txt")}, requires_confirmation=True,
        )
        assert decision.allowed is False
        assert "allow_live_execution" in decision.message

    def test_unlock_permits_mutating_tool(self) -> None:
        decision = self._policy(pref=False, unlocked=True).check(
            "write_file", {"path": str(Path.cwd() / "x.txt")}, requires_confirmation=True,
        )
        assert decision.allowed is True

    def test_preference_still_works_without_unlock(self) -> None:
        decision = self._policy(pref=True, unlocked=False).check(
            "write_file", {"path": str(Path.cwd() / "x.txt")}, requires_confirmation=True,
        )
        assert decision.allowed is True


class TestSafetyBoundary:
    """Unlocking must not bypass anything else."""

    def test_unlock_does_not_bypass_task_grant(self) -> None:
        """Without a confirmed task grant, unlocking alone is not enough."""
        policy = ToolRuntimePolicy(
            allowed_roots=(Path.cwd(),),
            live_execution_enabled=True,   # unlocked
            mutation_granted=False,        # but no confirmed grant
        )
        decision = policy.check(
            "write_file", {"path": str(Path.cwd() / "x.txt")}, requires_confirmation=True,
        )
        assert decision.allowed is False
        assert decision.requires_confirmation is True
        assert "confirmed task grant" in decision.message

    def test_unlock_does_not_widen_path_confinement(self) -> None:
        """An unlocked session still cannot write outside its allowed roots."""
        policy = ToolRuntimePolicy(
            allowed_roots=(Path.cwd(),),
            live_execution_enabled=True,
            mutation_granted=True,
        )
        decision = policy.check("write_file", {"path": "C:/Windows/System32/evil.txt"})
        assert decision.allowed is False
        assert "outside configured" in decision.message

    def test_unlock_does_not_widen_traversal(self) -> None:
        policy = ToolRuntimePolicy(
            allowed_roots=(Path.cwd(),),
            live_execution_enabled=True,
            mutation_granted=True,
        )
        decision = policy.check("read_file", {"path": str(Path.cwd() / ".." / ".." / "secret.txt")})
        assert decision.allowed is False

    def test_read_only_tools_unaffected_when_locked(self) -> None:
        """Locking must not break reading — otherwise the assistant is useless."""
        policy = ToolRuntimePolicy(
            allowed_roots=(Path.cwd(),),
            live_execution_enabled=False,
            mutation_granted=False,
        )
        decision = policy.check("read_file", {"path": str(Path.cwd() / "README.md")})
        assert decision.allowed is True


class TestPersistence:
    def test_unlock_does_not_leak_between_sessions(self) -> None:
        """Setting it on one state must not affect a freshly constructed one."""
        state = AssistantState()
        state.interaction_unlocked = True
        assert AssistantState().interaction_unlocked is False

    def test_unlock_is_not_a_persisted_preference(self) -> None:
        """It must live on AssistantState only — never on the saved preferences.

        If it were a preference field it would be written to disk and survive a
        restart, which defeats the point of a session-scoped grant.
        """
        import dataclasses
        from src.aradhya import assistant_models

        prefs_cls = getattr(assistant_models, "AssistantPreferences", None)
        if prefs_cls is None or not dataclasses.is_dataclass(prefs_cls):
            import pytest
            pytest.skip("AssistantPreferences dataclass not found")

        pref_fields = {f.name for f in dataclasses.fields(prefs_cls)}
        assert "interaction_unlocked" not in pref_fields

        state_fields = {f.name for f in dataclasses.fields(AssistantState)}
        assert "interaction_unlocked" in state_fields
