"""Trust-boundary workflow engine.

Generalizes the Parasite GC ``analyze -> confirm -> execute`` pattern (see
``parasite/pipeline.py:gc``) and the assistant's plan-confirmation flow into a
single, domain-agnostic lifecycle that every gated task runs through:

    ANALYZE -> PLAN -> USER_SELECTS -> DRY_RUN -> CONFIRM -> EXECUTE -> SUMMARIZE

The engine owns one safety invariant: it refuses to EXECUTE any *destructive*
or *checkpoint* action until an explicit human confirmation has been recorded.
This is what makes "stop before submit" and "present a plan before delete" work
for arbitrary domains without any task-specific code.

Callers supply two domain-specific callables:

* an **analyzer** — ``() -> Iterable[WorkflowAction]`` — that inspects the world
  (read-only / dry-run) and proposes candidate actions;
* an **executor** — ``(WorkflowAction) -> tuple[bool, str]`` — that performs a
  single selected action and returns ``(success, detail)``.

Everything else (selection, the confirmation checkpoint, the standard handoff
message, audit, and the structured summary) is handled here.

Example::

    wf = TrustBoundaryWorkflow("Clean caches in this project")
    wf.analyze(scan_caches)              # -> PLAN, candidate actions
    wf.select_only(["a1", "a3"])         # -> USER_SELECTS
    outcome = wf.execute(delete_one)     # destructive -> needs confirmation
    if outcome.needs_confirmation:
        print(outcome.message)           # standard handoff text
        wf.confirm()
        outcome = wf.execute(delete_one) # now runs
    print(wf.summarize().format_for_user())
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from loguru import logger


# ── State / risk taxonomy ──────────────────────────────────────────────

class WorkflowState(str, Enum):
    """Lifecycle states, in canonical order."""

    ANALYZE = "analyze"
    PLAN = "plan"
    USER_SELECTS = "user_selects"
    DRY_RUN = "dry_run"
    CONFIRM = "confirm"
    EXECUTE = "execute"
    SUMMARIZE = "summarize"
    CANCELLED = "cancelled"


class ActionRisk(str, Enum):
    """How dangerous an action is, in increasing order of caution."""

    SAFE = "safe"              # read-only or trivially reversible
    CAUTION = "caution"        # reversible but notable (move, archive, rename)
    DESTRUCTIVE = "destructive"  # delete, submit, system mutation — irreversible


# Action kinds that ALWAYS require a confirmation checkpoint, regardless of the
# risk label a caller assigns. Mirrors the doc's "submit, delete, system
# mutation, security UI" mandatory checkpoints.
CHECKPOINT_KINDS: frozenset[str] = frozenset(
    {"submit", "delete", "system_mutation", "security"}
)


@dataclass
class WorkflowAction:
    """A single proposed action in a trust-boundary workflow."""

    id: str
    description: str
    risk: ActionRisk = ActionRisk.SAFE
    kind: str = ""                       # e.g. "delete", "move", "submit"
    target: str = ""                     # path / url / form identifier
    metadata: dict[str, Any] = field(default_factory=dict)
    selected: bool = True                # whether the user chose to run it
    status: str = "pending"              # pending|planned|done|failed|skipped
    result: str = ""
    error: str = ""

    @property
    def is_checkpoint(self) -> bool:
        """True when this action must be gated behind an explicit confirmation."""
        return self.risk == ActionRisk.DESTRUCTIVE or self.kind in CHECKPOINT_KINDS

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "risk": self.risk.value,
            "kind": self.kind,
            "target": self.target,
            "metadata": self.metadata,
            "selected": self.selected,
            "status": self.status,
            "result": self.result,
            "error": self.error,
        }


@dataclass
class ExecuteOutcome:
    """Result of an :meth:`TrustBoundaryWorkflow.execute` call."""

    executed: bool
    needs_confirmation: bool
    message: str
    summary: "WorkflowSummary | None" = None


@dataclass
class WorkflowSummary:
    """Structured, serializable summary of a workflow run."""

    goal: str
    state: WorkflowState
    actions: list[WorkflowAction]
    dry_run: bool = False
    needs_confirmation: bool = False
    message: str = ""

    @property
    def selected(self) -> list[WorkflowAction]:
        return [a for a in self.actions if a.selected]

    @property
    def executed(self) -> list[WorkflowAction]:
        return [a for a in self.actions if a.status == "done"]

    @property
    def failed(self) -> list[WorkflowAction]:
        return [a for a in self.actions if a.status == "failed"]

    @property
    def skipped(self) -> list[WorkflowAction]:
        return [a for a in self.actions if not a.selected]

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "state": self.state.value,
            "dry_run": self.dry_run,
            "needs_confirmation": self.needs_confirmation,
            "message": self.message,
            "counts": {
                "total": len(self.actions),
                "selected": len(self.selected),
                "executed": len(self.executed),
                "failed": len(self.failed),
                "skipped": len(self.skipped),
            },
            "actions": [a.to_dict() for a in self.actions],
        }

    def format_for_user(self) -> str:
        lines = [f"📋 **{self.goal}**", ""]
        risk_icon = {
            ActionRisk.SAFE: "🟢",
            ActionRisk.CAUTION: "🟡",
            ActionRisk.DESTRUCTIVE: "🔴",
        }
        status_icon = {
            "pending": "⬜",
            "planned": "📝",
            "done": "✅",
            "failed": "❌",
            "skipped": "⏭️",
        }
        for action in self.actions:
            mark = status_icon.get(action.status, "⬜")
            risk = risk_icon.get(action.risk, "")
            lines.append(f"{mark} {risk} `{action.id}` {action.description}")
            if action.error:
                lines.append(f"     ↳ error: {action.error}")
        lines.append("")
        lines.append(
            f"{len(self.executed)} done · {len(self.failed)} failed · "
            f"{len(self.skipped)} skipped · {len(self.selected)} selected"
        )
        if self.needs_confirmation and self.message:
            lines.append("")
            lines.append(self.message)
        return "\n".join(lines)


# ── Security checkpoint detection (CAPTCHA / login / 2FA) ───────────────

# Lightweight, domain-agnostic heuristics. The agent should never attempt to
# bypass these — it must hand off to the human. DOM/visible text is matched
# case-insensitively; an optional OCR caller can feed screen text through the
# same function.
_SECURITY_SIGNALS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("captcha", ("captcha", "recaptcha", "hcaptcha", "i'm not a robot",
                 "i am not a robot", "verify you are human", "are you a robot")),
    ("two_factor", ("two-factor", "two factor", "2fa", "one-time password",
                    "one time passcode", "verification code", "otp",
                    "enter the code we sent", "authenticator app")),
    ("login", ("sign in to continue", "please log in", "please sign in",
               "enter your password", "login required")),
    ("payment", ("card number", "cvv", "credit card", "payment details")),
)


def detect_security_checkpoint(text: str) -> str | None:
    """Return a security-checkpoint label if ``text`` looks like one, else None.

    Labels: ``"captcha"``, ``"two_factor"``, ``"login"``, ``"payment"``. Use
    this before automating a page/form: if it returns non-None, stop and hand
    off to the human rather than trying to proceed.
    """
    if not text:
        return None
    lowered = text.lower()
    for label, needles in _SECURITY_SIGNALS:
        if any(needle in lowered for needle in needles):
            return label
    return None


SECURITY_HANDOFF_MESSAGE = (
    "🔒 I hit a security checkpoint ({label}) that I won't bypass. "
    "Please complete it yourself, then tell me to continue."
)


# ── The engine ─────────────────────────────────────────────────────────

class TrustBoundaryWorkflow:
    """Drives a single gated task through the trust-boundary lifecycle."""

    def __init__(
        self,
        goal: str,
        *,
        audit: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        self.goal = goal
        self.state = WorkflowState.ANALYZE
        self.actions: list[WorkflowAction] = []
        self._confirmed = False
        # audit(event_type, payload) — defaults to a no-op so the engine stays
        # pure and trivially testable. Pass get_audit_logger().log_event to wire
        # it into the event-sourced audit trail.
        self._audit = audit or (lambda event_type, payload: None)

    # -- ANALYZE -> PLAN --------------------------------------------------

    def analyze(
        self, analyzer: Callable[[], Iterable[WorkflowAction]]
    ) -> list[WorkflowAction]:
        """Run the (read-only) analyzer and populate the candidate plan.

        The analyzer must not mutate anything — it only proposes actions. All
        proposed actions start *selected*; the user narrows from there.
        """
        proposed = list(analyzer())
        self._ensure_unique_ids(proposed)
        for action in proposed:
            action.selected = True
            action.status = "pending"
        self.actions = proposed
        self.state = WorkflowState.PLAN
        self._audit("workflow_analyzed", {"goal": self.goal, "count": len(proposed)})
        logger.debug("TrustBoundary '{}' analyzed: {} actions", self.goal, len(proposed))
        return self.actions

    # -- USER_SELECTS -----------------------------------------------------

    def select_all(self) -> None:
        for action in self.actions:
            action.selected = True
        self.state = WorkflowState.USER_SELECTS

    def select_none(self) -> None:
        for action in self.actions:
            action.selected = False
        self.state = WorkflowState.USER_SELECTS

    def select_only(self, ids: Iterable[str]) -> None:
        """Select exactly the given action ids, deselecting the rest."""
        wanted = set(ids)
        unknown = wanted - {a.id for a in self.actions}
        if unknown:
            raise KeyError(f"Unknown action id(s): {sorted(unknown)}")
        for action in self.actions:
            action.selected = action.id in wanted
        self.state = WorkflowState.USER_SELECTS

    def deselect(self, ids: Iterable[str]) -> None:
        drop = set(ids)
        for action in self.actions:
            if action.id in drop:
                action.selected = False
        self.state = WorkflowState.USER_SELECTS

    # -- DRY_RUN ----------------------------------------------------------

    def dry_run(self) -> WorkflowSummary:
        """Preview the selected actions without executing anything."""
        for action in self.actions:
            if action.selected:
                action.status = "planned"
        self.state = WorkflowState.DRY_RUN
        return self.summarize(dry_run=True)

    # -- CONFIRM ----------------------------------------------------------

    @property
    def requires_confirmation(self) -> bool:
        """True when any *selected* action is destructive / a checkpoint kind."""
        return any(a.selected and a.is_checkpoint for a in self.actions)

    @property
    def confirmed(self) -> bool:
        return self._confirmed

    def checkpoint_message(self) -> str:
        """Standard handoff text shown before destructive actions execute."""
        risky = [a for a in self.actions if a.selected and a.is_checkpoint]
        if not risky:
            return ""
        bullet = "\n".join(f"  • {a.description}" for a in risky)
        return (
            f"⚠️ This will run {len(risky)} irreversible action(s):\n{bullet}\n"
            "Confirm to proceed, or cancel. Nothing has changed yet."
        )

    def confirm(self) -> None:
        """Record explicit human confirmation for the destructive checkpoint."""
        self._confirmed = True
        self.state = WorkflowState.CONFIRM
        self._audit("workflow_confirmed", {"goal": self.goal})

    # -- EXECUTE -> SUMMARIZE ---------------------------------------------

    def execute(
        self, executor: Callable[[WorkflowAction], tuple[bool, str]]
    ) -> ExecuteOutcome:
        """Execute the selected actions, gated by the confirmation invariant.

        If any selected action requires confirmation and none has been
        recorded, NOTHING runs: the workflow moves to ``CONFIRM`` and returns an
        outcome with ``needs_confirmation=True`` and the standard handoff
        message. Call :meth:`confirm` then ``execute`` again to proceed.
        """
        if self.state == WorkflowState.CANCELLED:
            return ExecuteOutcome(False, False, "Workflow was cancelled.", self.summarize())

        if self.requires_confirmation and not self._confirmed:
            self.state = WorkflowState.CONFIRM
            message = self.checkpoint_message()
            self._audit("workflow_checkpoint", {"goal": self.goal})
            return ExecuteOutcome(
                executed=False,
                needs_confirmation=True,
                message=message,
                summary=self.summarize(needs_confirmation=True, message=message),
            )

        self.state = WorkflowState.EXECUTE
        for action in self.actions:
            if not action.selected:
                action.status = "skipped"
                continue
            try:
                success, detail = executor(action)
            except Exception as error:  # executor must not take down the engine
                action.status = "failed"
                action.error = str(error)
                logger.warning("Action '{}' raised: {}", action.id, error)
                self._audit("workflow_action", action.to_dict())
                continue
            action.status = "done" if success else "failed"
            if success:
                action.result = detail
            else:
                action.error = detail
            self._audit("workflow_action", action.to_dict())

        self.state = WorkflowState.SUMMARIZE
        summary = self.summarize()
        self._audit("workflow_summary", summary.to_dict())
        return ExecuteOutcome(executed=True, needs_confirmation=False, message="", summary=summary)

    # -- misc -------------------------------------------------------------

    def cancel(self) -> WorkflowSummary:
        self.state = WorkflowState.CANCELLED
        self._audit("workflow_cancelled", {"goal": self.goal})
        return self.summarize()

    def summarize(
        self,
        *,
        dry_run: bool = False,
        needs_confirmation: bool = False,
        message: str = "",
    ) -> WorkflowSummary:
        return WorkflowSummary(
            goal=self.goal,
            state=self.state,
            actions=self.actions,
            dry_run=dry_run,
            needs_confirmation=needs_confirmation,
            message=message,
        )

    @staticmethod
    def _ensure_unique_ids(actions: list[WorkflowAction]) -> None:
        seen: set[str] = set()
        for index, action in enumerate(actions):
            if not action.id or action.id in seen:
                action.id = f"a{index + 1}"
            seen.add(action.id)
