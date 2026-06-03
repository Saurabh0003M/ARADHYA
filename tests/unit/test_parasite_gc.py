from __future__ import annotations

from pathlib import Path

from src.aradhya.parasite.checkpoint import (
    STAGES,
    Checkpoint,
    record_stage_complete,
    save_checkpoint,
)
from src.aradhya.parasite.pipeline import DigestionPipeline


def _completed_checkpoint(hosts_root: Path, target: str) -> None:
    cp = Checkpoint(target=target)
    for stage in STAGES:
        artifacts = {"passed": True} if stage == "EXTRACT" else {}
        record_stage_complete(cp, stage, artifacts=artifacts)
    save_checkpoint(hosts_root, cp)


def test_gc_dry_run_default_does_not_delete_git(tmp_path: Path):
    hosts = tmp_path / "Hosts"
    target = hosts / "demo"
    git_objects = target / ".git" / "objects"
    git_objects.mkdir(parents=True)
    (git_objects / "obj").write_bytes(b"abc")

    result = DigestionPipeline(tmp_path).gc()

    assert result["dry_run"] is True
    assert result["actions_planned"] == 1
    assert result["actions_taken"] == 0
    assert result["results"][0]["action"] == "strip_git"
    assert (target / ".git").is_dir()


def test_gc_live_strip_git_removes_git_dir(tmp_path: Path, monkeypatch):
    hosts = tmp_path / "Hosts"
    target = hosts / "demo"
    git_objects = target / ".git" / "objects"
    git_objects.mkdir(parents=True)
    (git_objects / "obj").write_bytes(b"abc")
    monkeypatch.setattr(
        DigestionPipeline,
        "_audit_gc_action",
        staticmethod(lambda _result: None),
    )

    result = DigestionPipeline(tmp_path).gc(dry_run=False)

    assert result["actions_taken"] == 1
    assert not (target / ".git").exists()


def test_gc_delete_preserves_checkpoint_archive(tmp_path: Path, monkeypatch):
    hosts = tmp_path / "Hosts"
    target = hosts / "demo"
    target.mkdir(parents=True)
    _completed_checkpoint(hosts, "demo")
    monkeypatch.setattr(
        DigestionPipeline,
        "_audit_gc_action",
        staticmethod(lambda _result: None),
    )

    result = DigestionPipeline(tmp_path).gc(
        strip_git=False,
        delete_completed=True,
        dry_run=False,
    )

    assert result["actions_taken"] == 1
    assert not target.exists()
    archived = list((hosts / ".archived").glob("demo-*/.parasite/checkpoint.json"))
    assert len(archived) == 1


def test_reabsorb_maps_old_stage_names(tmp_path: Path, monkeypatch):
    hosts = tmp_path / "Hosts"
    target = hosts / "demo"
    target.mkdir(parents=True)
    cp = Checkpoint(target="demo")
    cp.completed_stages = ["ANALYZE", "VALIDATE"]
    cp.stage_results = {
        "ANALYZE": {"artifacts": {"capabilities": []}},
        "VALIDATE": {"artifacts": {"passed": True}},
    }
    save_checkpoint(hosts, cp)

    pipeline = DigestionPipeline(tmp_path)
    reabsorbed = pipeline.reabsorb("demo")

    assert reabsorbed is not None
    assert reabsorbed.error == ""
    assert "ABSORB" in reabsorbed.completed_stages
    assert "SWALLOW" in reabsorbed.stage_results
    assert "EXTRACT" in reabsorbed.stage_results
