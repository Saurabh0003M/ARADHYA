"""Safe-maintenance tools (class E) built on the trust-boundary engine.

The flow is the canonical analyze -> plan -> confirm -> execute -> summarize:

    analysis = scan_maintenance_candidates([root])        # read-only
    actions  = maintenance_actions(analysis)              # -> WorkflowAction[]
    wf = TrustBoundaryWorkflow("Reclaim disk space")
    wf.analyze(lambda: actions)
    wf.select_only(chosen_ids)
    executor = make_maintenance_executor(allowed_roots=[root])
    outcome = wf.execute(executor)   # blocks: every candidate is kind="delete"
    if outcome.needs_confirmation:
        wf.confirm(); wf.execute(executor)

``scan_maintenance_candidates`` is also exposed as the read-only, agent-callable
``analyze_disk_usage`` tool. Execution always goes through the engine, never the
tool, so deletes are confirmation-gated and path-confined.

This is deliberately domain-agnostic: "my disk is full" and "clean old caches in
this project" run through the exact same machinery — only the root differs.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Any

from loguru import logger

from src.aradhya.tools.tool_registry import tool_definition
from src.aradhya.workflows.trust_boundary import ActionRisk, WorkflowAction


# Directory names that are regenerable cleanup candidates, mapped to
# (kind label, risk). Caches are trivially regenerable; dependency and build
# dirs cost time/network to rebuild, so they carry more caution. Everything
# here still becomes a kind="delete" action, so the engine confirmation-gates
# it regardless of the risk label.
_CLEANUP_DIRS: dict[str, tuple[str, ActionRisk]] = {
    "__pycache__": ("python_cache", ActionRisk.SAFE),
    ".pytest_cache": ("test_cache", ActionRisk.SAFE),
    ".mypy_cache": ("type_cache", ActionRisk.SAFE),
    ".ruff_cache": ("lint_cache", ActionRisk.SAFE),
    ".tox": ("env_cache", ActionRisk.SAFE),
    ".cache": ("cache", ActionRisk.SAFE),
    "node_modules": ("dependency_cache", ActionRisk.CAUTION),
    "build": ("build_artifact", ActionRisk.CAUTION),
    "dist": ("build_artifact", ActionRisk.CAUTION),
    ".next": ("build_artifact", ActionRisk.CAUTION),
}

# Directories we never descend into while scanning (avoids huge walks and
# never proposes deleting version-control internals).
_SKIP_DESCEND = {".git", ".hg", ".svn"}


def _directory_size(path: Path) -> int:
    """Best-effort recursive byte size, skipping symlinks and unreadable files."""
    total = 0
    for child in path.rglob("*"):
        try:
            if child.is_symlink() or not child.is_file():
                continue
            total += child.stat().st_size
        except OSError:
            continue
    return total


def scan_maintenance_candidates(
    roots: Sequence[str | Path],
    *,
    depth: int = 4,
    max_candidates: int = 50,
) -> dict[str, Any]:
    """Scan ``roots`` for regenerable cleanup candidates (read-only).

    Returns a structured, serializable report. Walks at most ``depth`` levels
    below each root and never descends into a candidate once matched (so a
    nested ``__pycache__`` inside ``node_modules`` is counted once, via the
    parent).
    """
    candidates: list[dict[str, Any]] = []
    seen: set[Path] = set()

    for raw_root in roots:
        root = Path(raw_root).expanduser().resolve()
        if not root.is_dir():
            continue
        _walk_for_candidates(root, root, depth, candidates, seen)

    # Largest first — best reclaim per confirmation.
    candidates.sort(key=lambda c: c["bytes"], reverse=True)
    if len(candidates) > max_candidates:
        candidates = candidates[:max_candidates]

    reclaimable = sum(c["bytes"] for c in candidates)
    return {
        "roots": [str(Path(r).expanduser().resolve()) for r in roots],
        "depth": depth,
        "candidates": candidates,
        "candidate_count": len(candidates),
        "reclaimable_bytes": reclaimable,
        "reclaimable_mb": f"{reclaimable / (1024 * 1024):.1f}",
    }


def _walk_for_candidates(
    current: Path,
    root: Path,
    depth: int,
    candidates: list[dict[str, Any]],
    seen: set[Path],
) -> None:
    """Recursive helper that records cleanup candidates up to ``depth`` levels."""
    try:
        level = len(current.relative_to(root).parts)
    except ValueError:
        return
    if level > depth:
        return

    try:
        entries = sorted(current.iterdir())
    except OSError:
        return

    for entry in entries:
        try:
            if entry.is_symlink() or not entry.is_dir():
                continue
        except OSError:
            continue

        if entry.name in _SKIP_DESCEND:
            continue

        match = _CLEANUP_DIRS.get(entry.name)
        if match is not None and entry not in seen:
            kind, risk = match
            size = _directory_size(entry)
            seen.add(entry)
            candidates.append(
                {
                    "path": str(entry),
                    "kind": kind,
                    "reason": f"Regenerable {kind.replace('_', ' ')}",
                    "bytes": size,
                    "size_mb": f"{size / (1024 * 1024):.1f}",
                    "risk": risk.value,
                }
            )
            # Don't descend into a matched candidate.
            continue

        _walk_for_candidates(entry, root, depth, candidates, seen)


def maintenance_actions(analysis: dict[str, Any]) -> list[WorkflowAction]:
    """Convert a ``scan_maintenance_candidates`` report into WorkflowActions.

    Every candidate becomes a ``kind="delete"`` action so the trust-boundary
    engine confirmation-gates the whole batch behind a single checkpoint.
    """
    actions: list[WorkflowAction] = []
    for index, candidate in enumerate(analysis.get("candidates", [])):
        actions.append(
            WorkflowAction(
                id=f"m{index + 1}",
                description=(
                    f"Delete {candidate['kind']} at {candidate['path']} "
                    f"({candidate['size_mb']} MB)"
                ),
                risk=ActionRisk(candidate.get("risk", "caution")),
                kind="delete",
                target=candidate["path"],
                metadata={
                    "bytes": candidate.get("bytes", 0),
                    "reason": candidate.get("reason", ""),
                },
            )
        )
    return actions


def make_maintenance_executor(
    allowed_roots: Iterable[str | Path],
) -> Callable[[WorkflowAction], tuple[bool, str]]:
    """Build an executor that deletes a candidate, confined to ``allowed_roots``.

    The confinement is a hard safety boundary: even if an action's target was
    tampered with, the executor refuses to remove anything outside the roots
    that were scanned.
    """
    resolved_roots = [Path(r).expanduser().resolve() for r in allowed_roots]

    def _within_roots(target: Path) -> bool:
        for root in resolved_roots:
            try:
                target.relative_to(root)
                return True
            except ValueError:
                continue
        return False

    def _execute(action: WorkflowAction) -> tuple[bool, str]:
        target = Path(action.target).expanduser().resolve()
        if not _within_roots(target):
            return False, f"refused: {target} is outside the scanned roots"
        if not target.exists():
            return False, "skipped: path no longer exists"
        try:
            freed = action.metadata.get("bytes", 0)
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
            return True, f"removed ({freed} bytes)"
        except Exception as error:  # noqa: BLE001 - reported back, not raised
            logger.warning("Maintenance delete failed for {}: {}", target, error)
            return False, str(error)

    return _execute


@tool_definition(
    name="analyze_disk_usage",
    description=(
        "Scan one or more directories for regenerable cleanup candidates "
        "(caches, build artifacts, node_modules) and report how much space "
        "they use. Read-only — it never deletes anything; deletion happens "
        "through a confirmation-gated maintenance workflow."
    ),
    parameters={
        "type": "object",
        "properties": {
            "roots": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Directories to scan.",
            },
            "depth": {
                "type": "integer",
                "description": "Maximum levels to descend below each root. Default 4.",
            },
        },
        "required": ["roots"],
    },
)
def analyze_disk_usage(roots: list[str], depth: int = 4) -> str:
    """Agent-callable wrapper that returns a human-readable candidate report."""
    if not roots:
        return "No roots provided to scan."

    analysis = scan_maintenance_candidates(roots, depth=depth)
    candidates = analysis["candidates"]
    if not candidates:
        return (
            f"No regenerable cleanup candidates found under {', '.join(analysis['roots'])}."
        )

    lines = [
        f"Found {analysis['candidate_count']} cleanup candidate(s), "
        f"~{analysis['reclaimable_mb']} MB reclaimable:",
    ]
    for candidate in candidates[:20]:
        lines.append(
            f"  [{candidate['risk']}] {candidate['size_mb']:>8} MB  "
            f"{candidate['kind']}  {candidate['path']}"
        )
    lines.append(
        "\nTo remove any of these, run a maintenance workflow — deletion is "
        "confirmation-gated and confined to the scanned roots."
    )
    return "\n".join(lines)


ALL_MAINTENANCE_TOOLS = [analyze_disk_usage]
