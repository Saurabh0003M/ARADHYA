"""Reusable workflow machinery for gated, multi-step tasks.

The flagship piece is the trust-boundary engine (``trust_boundary.py``), which
generalizes the Parasite GC ``analyze -> confirm -> execute`` pattern into a
single domain-agnostic lifecycle used by maintenance, form-fill, and batch file
operations.
"""

from src.aradhya.workflows.trust_boundary import (
    ActionRisk,
    TrustBoundaryWorkflow,
    WorkflowAction,
    WorkflowState,
    WorkflowSummary,
    detect_security_checkpoint,
)

__all__ = [
    "ActionRisk",
    "TrustBoundaryWorkflow",
    "WorkflowAction",
    "WorkflowState",
    "WorkflowSummary",
    "detect_security_checkpoint",
]
