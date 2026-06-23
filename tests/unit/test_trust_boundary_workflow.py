"""P1-1: the trust-boundary workflow engine.

Covers the core safety invariant (no destructive execution before an explicit
confirmation), batch selection, mandatory checkpoint kinds (submit/delete/...),
executor isolation, the dry-run preview, and security-checkpoint detection.
"""

from __future__ import annotations

import pytest

from src.aradhya.workflows.trust_boundary import (
    ActionRisk,
    TrustBoundaryWorkflow,
    WorkflowAction,
    WorkflowState,
    detect_security_checkpoint,
)


def _safe(id_: str) -> WorkflowAction:
    return WorkflowAction(id=id_, description=f"safe {id_}", risk=ActionRisk.SAFE)


def _delete(id_: str) -> WorkflowAction:
    return WorkflowAction(
        id=id_, description=f"delete {id_}", risk=ActionRisk.DESTRUCTIVE, kind="delete"
    )


class RecordingExecutor:
    """Records executed action ids; optionally fails or raises for some."""

    def __init__(self, fail: set[str] | None = None, raise_on: set[str] | None = None):
        self.ran: list[str] = []
        self.fail = fail or set()
        self.raise_on = raise_on or set()

    def __call__(self, action: WorkflowAction) -> tuple[bool, str]:
        self.ran.append(action.id)
        if action.id in self.raise_on:
            raise RuntimeError(f"boom {action.id}")
        if action.id in self.fail:
            return False, f"failed {action.id}"
        return True, f"did {action.id}"


# ── analyze / select ───────────────────────────────────────────────────

def test_analyze_populates_plan_all_selected():
    wf = TrustBoundaryWorkflow("goal")
    actions = wf.analyze(lambda: [_safe("a"), _safe("b")])

    assert wf.state == WorkflowState.PLAN
    assert [a.id for a in actions] == ["a", "b"]
    assert all(a.selected for a in actions)


def test_select_only_narrows_selection():
    wf = TrustBoundaryWorkflow("goal")
    wf.analyze(lambda: [_safe("a"), _safe("b"), _safe("c")])
    wf.select_only(["a", "c"])

    assert wf.state == WorkflowState.USER_SELECTS
    assert {a.id for a in wf.actions if a.selected} == {"a", "c"}


def test_select_only_rejects_unknown_id():
    wf = TrustBoundaryWorkflow("goal")
    wf.analyze(lambda: [_safe("a")])
    with pytest.raises(KeyError):
        wf.select_only(["nope"])


# ── safe path: no confirmation needed ──────────────────────────────────

def test_safe_actions_execute_without_confirmation():
    wf = TrustBoundaryWorkflow("goal")
    wf.analyze(lambda: [_safe("a"), _safe("b")])
    executor = RecordingExecutor()

    outcome = wf.execute(executor)

    assert outcome.executed is True
    assert outcome.needs_confirmation is False
    assert executor.ran == ["a", "b"]
    assert wf.state == WorkflowState.SUMMARIZE


# ── destructive path: confirmation gate ────────────────────────────────

def test_destructive_action_blocks_until_confirmed():
    wf = TrustBoundaryWorkflow("goal")
    wf.analyze(lambda: [_delete("x")])
    executor = RecordingExecutor()

    outcome = wf.execute(executor)

    # Nothing ran; we are parked at the confirmation checkpoint.
    assert outcome.executed is False
    assert outcome.needs_confirmation is True
    assert "irreversible" in outcome.message
    assert executor.ran == []
    assert wf.state == WorkflowState.CONFIRM
    assert wf.requires_confirmation is True

    wf.confirm()
    outcome2 = wf.execute(executor)

    assert outcome2.executed is True
    assert executor.ran == ["x"]
    assert wf.actions[0].status == "done"


def test_submit_kind_requires_confirmation_even_if_not_destructive():
    # A "submit" action labelled SAFE must still stop before running:
    # this is the "stop before submit" form-assist guarantee.
    submit = WorkflowAction(id="s", description="submit form", risk=ActionRisk.SAFE, kind="submit")
    wf = TrustBoundaryWorkflow("apply")
    wf.analyze(lambda: [submit])
    executor = RecordingExecutor()

    outcome = wf.execute(executor)

    assert outcome.needs_confirmation is True
    assert executor.ran == []


def test_checkpoint_message_lists_destructive_actions():
    wf = TrustBoundaryWorkflow("goal")
    wf.analyze(lambda: [_safe("a"), _delete("x"), _delete("y")])

    message = wf.checkpoint_message()

    assert "2 irreversible" in message
    assert "delete x" in message
    assert "delete y" in message
    assert "safe a" not in message


def test_deselecting_destructive_action_removes_checkpoint():
    wf = TrustBoundaryWorkflow("goal")
    wf.analyze(lambda: [_safe("a"), _delete("x")])
    wf.select_only(["a"])  # drop the destructive one

    assert wf.requires_confirmation is False
    executor = RecordingExecutor()
    outcome = wf.execute(executor)

    assert outcome.executed is True
    assert executor.ran == ["a"]
    assert wf.actions[1].status == "skipped"


# ── execution robustness ───────────────────────────────────────────────

def test_executor_exception_marks_failed_and_continues():
    wf = TrustBoundaryWorkflow("goal")
    wf.analyze(lambda: [_safe("a"), _safe("b"), _safe("c")])
    executor = RecordingExecutor(raise_on={"b"})

    outcome = wf.execute(executor)

    assert outcome.executed is True
    assert executor.ran == ["a", "b", "c"]  # one raising action didn't stop the rest
    statuses = {a.id: a.status for a in wf.actions}
    assert statuses == {"a": "done", "b": "failed", "c": "done"}
    assert wf.actions[1].error == "boom b"


def test_failed_executor_result_recorded():
    wf = TrustBoundaryWorkflow("goal")
    wf.analyze(lambda: [_safe("a")])
    outcome = wf.execute(RecordingExecutor(fail={"a"}))

    assert wf.actions[0].status == "failed"
    assert wf.actions[0].error == "failed a"
    assert len(outcome.summary.failed) == 1


# ── dry-run / summary / cancel ─────────────────────────────────────────

def test_dry_run_marks_planned_without_executing():
    wf = TrustBoundaryWorkflow("goal")
    wf.analyze(lambda: [_delete("x")])
    summary = wf.dry_run()

    assert wf.state == WorkflowState.DRY_RUN
    assert summary.dry_run is True
    assert wf.actions[0].status == "planned"  # not "done"


def test_summary_counts_and_serialization():
    wf = TrustBoundaryWorkflow("goal")
    wf.analyze(lambda: [_safe("a"), _safe("b"), _safe("c")])
    wf.select_only(["a", "b"])
    wf.execute(RecordingExecutor(fail={"b"}))

    summary = wf.summarize()
    data = summary.to_dict()

    assert data["counts"] == {
        "total": 3,
        "selected": 2,
        "executed": 1,
        "failed": 1,
        "skipped": 1,
    }
    assert data["goal"] == "goal"


def test_cancel_sets_state_and_blocks_execution():
    wf = TrustBoundaryWorkflow("goal")
    wf.analyze(lambda: [_safe("a")])
    wf.cancel()

    assert wf.state == WorkflowState.CANCELLED
    outcome = wf.execute(RecordingExecutor())
    assert outcome.executed is False


def test_audit_hook_receives_events():
    events: list[str] = []
    wf = TrustBoundaryWorkflow("goal", audit=lambda ev, payload: events.append(ev))
    wf.analyze(lambda: [_safe("a")])
    wf.execute(RecordingExecutor())

    assert "workflow_analyzed" in events
    assert "workflow_action" in events
    assert "workflow_summary" in events


def test_missing_or_duplicate_ids_are_made_unique():
    wf = TrustBoundaryWorkflow("goal")
    wf.analyze(
        lambda: [
            WorkflowAction(id="", description="one"),
            WorkflowAction(id="dup", description="two"),
            WorkflowAction(id="dup", description="three"),
        ]
    )
    ids = [a.id for a in wf.actions]
    assert len(set(ids)) == 3


# ── security checkpoint detection ──────────────────────────────────────

@pytest.mark.parametrize(
    "text,expected",
    [
        ("Please complete the reCAPTCHA to continue", "captcha"),
        ("I'm not a robot", "captcha"),
        ("Enter the verification code we sent via 2FA", "two_factor"),
        ("Please sign in to continue", "login"),
        ("Enter your card number and CVV", "payment"),
        ("Here is your search result summary", None),
        ("", None),
    ],
)
def test_detect_security_checkpoint(text, expected):
    assert detect_security_checkpoint(text) == expected
