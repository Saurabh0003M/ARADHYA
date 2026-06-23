"""P1-2: safe-maintenance tools running through the trust-boundary engine.

Proves the class-E loop end to end on a temp tree: scan (read-only) -> build
actions -> the engine blocks on the delete checkpoint -> confirm -> execute
actually removes the candidates, while non-candidates and out-of-root paths are
never touched.
"""

from __future__ import annotations

from pathlib import Path

from src.aradhya.tools.maintenance_tools import (
    analyze_disk_usage,
    maintenance_actions,
    make_maintenance_executor,
    scan_maintenance_candidates,
)
from src.aradhya.workflows.trust_boundary import TrustBoundaryWorkflow, WorkflowAction


def _write(path: Path, content: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _build_tree(root: Path) -> None:
    # Candidates
    _write(root / "src" / "__pycache__" / "mod.pyc", "abcdef")       # python_cache
    _write(root / "node_modules" / "left-pad" / "index.js", "xxxx")  # dependency_cache
    _write(root / "build" / "out.bin", "yyyyyyyy")                    # build_artifact
    # Non-candidates that must be preserved
    _write(root / "src" / "app.py", "print('hi')")
    _write(root / ".git" / "config", "[core]")                       # never a candidate
    _write(root / "keep.txt", "important")


def test_scan_finds_cleanup_candidates(tmp_path):
    _build_tree(tmp_path)

    analysis = scan_maintenance_candidates([tmp_path])
    names = {Path(c["path"]).name for c in analysis["candidates"]}

    assert names == {"__pycache__", "node_modules", "build"}
    assert analysis["candidate_count"] == 3
    assert analysis["reclaimable_bytes"] > 0


def test_scan_excludes_git_and_source(tmp_path):
    _build_tree(tmp_path)

    analysis = scan_maintenance_candidates([tmp_path])
    paths = {c["path"] for c in analysis["candidates"]}

    assert not any(".git" in p for p in paths)
    assert not any(p.endswith("app.py") for p in paths)


def test_scan_sorted_largest_first(tmp_path):
    _build_tree(tmp_path)
    analysis = scan_maintenance_candidates([tmp_path])
    sizes = [c["bytes"] for c in analysis["candidates"]]
    assert sizes == sorted(sizes, reverse=True)


def test_scan_respects_depth(tmp_path):
    # Candidate buried 3 levels deep is missed at depth=1, found at depth=4.
    _write(tmp_path / "a" / "b" / "__pycache__" / "x.pyc", "data")

    shallow = scan_maintenance_candidates([tmp_path], depth=1)
    deep = scan_maintenance_candidates([tmp_path], depth=4)

    assert shallow["candidate_count"] == 0
    assert deep["candidate_count"] == 1


def test_does_not_descend_into_matched_candidate(tmp_path):
    # A nested cache inside node_modules is counted once (via node_modules).
    _write(tmp_path / "node_modules" / "pkg" / "__pycache__" / "a.pyc", "z")
    analysis = scan_maintenance_candidates([tmp_path])
    names = [Path(c["path"]).name for c in analysis["candidates"]]
    assert names == ["node_modules"]


def test_maintenance_actions_are_delete_kind(tmp_path):
    _build_tree(tmp_path)
    analysis = scan_maintenance_candidates([tmp_path])
    actions = maintenance_actions(analysis)

    assert all(a.kind == "delete" for a in actions)
    # delete kind always forces a checkpoint regardless of risk label
    assert all(a.is_checkpoint for a in actions)


def test_end_to_end_requires_confirmation_then_deletes(tmp_path):
    _build_tree(tmp_path)
    analysis = scan_maintenance_candidates([tmp_path])
    actions = maintenance_actions(analysis)

    wf = TrustBoundaryWorkflow("Reclaim disk space")
    wf.analyze(lambda: actions)
    executor = make_maintenance_executor(allowed_roots=[tmp_path])

    # First execute: blocked at the delete checkpoint, nothing removed yet.
    outcome = wf.execute(executor)
    assert outcome.needs_confirmation is True
    assert (tmp_path / "build").exists()

    # Confirm and execute for real.
    wf.confirm()
    outcome2 = wf.execute(executor)

    assert outcome2.executed is True
    assert not (tmp_path / "src" / "__pycache__").exists()
    assert not (tmp_path / "node_modules").exists()
    assert not (tmp_path / "build").exists()
    # Non-candidates survive.
    assert (tmp_path / "src" / "app.py").exists()
    assert (tmp_path / ".git").exists()
    assert (tmp_path / "keep.txt").exists()


def test_partial_selection_only_deletes_chosen(tmp_path):
    _build_tree(tmp_path)
    analysis = scan_maintenance_candidates([tmp_path])
    actions = maintenance_actions(analysis)
    build_action = next(a for a in actions if Path(a.target).name == "build")

    wf = TrustBoundaryWorkflow("Reclaim disk space")
    wf.analyze(lambda: actions)
    wf.select_only([build_action.id])
    wf.confirm()
    wf.execute(make_maintenance_executor(allowed_roots=[tmp_path]))

    assert not (tmp_path / "build").exists()
    assert (tmp_path / "node_modules").exists()  # not selected → untouched


def test_executor_refuses_paths_outside_roots(tmp_path):
    outside = tmp_path.parent / "outside_target"
    outside.mkdir()
    (outside / "file.txt").write_text("precious", encoding="utf-8")

    executor = make_maintenance_executor(allowed_roots=[tmp_path])
    action = WorkflowAction(id="x", description="delete outside", kind="delete", target=str(outside))

    success, detail = executor(action)

    assert success is False
    assert "outside" in detail
    assert outside.exists()
    # cleanup
    (outside / "file.txt").unlink()
    outside.rmdir()


def test_analyze_disk_usage_tool_reports(tmp_path):
    _build_tree(tmp_path)
    report = analyze_disk_usage([str(tmp_path)])

    assert "cleanup candidate" in report
    assert "MB reclaimable" in report
    assert "node_modules" in report


def test_analyze_disk_usage_tool_handles_empty(tmp_path):
    report = analyze_disk_usage([str(tmp_path)])
    assert "No regenerable cleanup candidates" in report
