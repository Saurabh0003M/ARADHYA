from __future__ import annotations

from types import SimpleNamespace

from src.aradhya import main
from src.aradhya.runtime_profile import build_default_runtime_profile
from src.aradhya.parasite.checkpoint import (
    STAGES,
    Checkpoint,
    record_stage_complete,
    save_checkpoint,
)


def test_dispatch_model_workers_command(monkeypatch, tmp_path):
    captured = {}

    def fake_render(statuses):
        captured["count"] = len(statuses)

    monkeypatch.setattr(main, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(main, "render_model_workers", fake_render)

    handled = main._dispatch_command(
        "/model workers",
        runtime_profile=build_default_runtime_profile(tmp_path),
    )

    assert handled is True
    assert captured["count"] > 1


def test_dispatch_model_workers_assess_command(monkeypatch, tmp_path):
    captured = {}

    def fake_render(assessment):
        captured["allowed"] = assessment.allowed

    monkeypatch.setattr(main, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(main, "render_cloud_safety_assessment", fake_render)

    handled = main._dispatch_command(
        "/model workers assess summarize public API docs",
        runtime_profile=build_default_runtime_profile(tmp_path),
    )

    assert handled is True
    assert captured["allowed"] is True


def test_dispatch_apis_search_command(monkeypatch, tmp_path):
    captured = {}

    def fake_render(title, entries, risk_labels):
        captured["title"] = title
        captured["names"] = [entry.name for entry in entries]
        captured["risks"] = risk_labels

    monkeypatch.setattr(main, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(main, "render_api_entries", fake_render)

    handled = main._dispatch_command("/apis search weather")

    assert handled is True
    assert "Open-Meteo" in captured["names"]
    assert captured["risks"]["Open-Meteo"] == "low: no auth + HTTPS"


def test_dispatch_parasite_candidates_command(monkeypatch, tmp_path):
    hosts = tmp_path / "Hosts"
    target = hosts / "demo-agent"
    target.mkdir(parents=True)
    (target / ".parasite").mkdir()
    (target / ".parasite" / "DIGEST.md").write_text("# Digest: demo-agent\n", encoding="utf-8")

    cp = Checkpoint(target="demo-agent", trust_score="HIGH")
    record_stage_complete(
        cp,
        "SWALLOW",
        artifacts={
            "type": "node",
            "files_scanned": 12,
            "dependencies": ["demo"],
            "capabilities": [{"kind": "agent_framework", "detail": "agent"}],
        },
    )
    for stage in STAGES:
        if stage not in cp.completed_stages:
            artifacts = {}
            if stage == "EXTRACT":
                artifacts = {"passed": True}
            elif stage == "ABSORB":
                artifacts = {"absorbed": [], "count": 0}
            record_stage_complete(cp, stage, artifacts=artifacts)
    save_checkpoint(hosts, cp)

    monkeypatch.setattr(main, "PROJECT_ROOT", tmp_path)

    from unittest.mock import patch

    # Mock rich console print to avoid emoji rendering errors in Windows CI
    with patch("src.aradhya.ui.cli.console.print"):
        handled = main._dispatch_command("/parasite candidates")

    assert handled is True
    assert (tmp_path / "data" / "processed" / "context" / "host_integration_ledger.json").is_file()


def test_dispatch_parasite_gc_defaults_to_dry_run(monkeypatch, tmp_path):
    captured = {}

    class FakePipeline:
        def __init__(self, project_root):
            self.project_root = project_root

        def gc(self, **kwargs):
            captured.update(kwargs)
            return {
                "dry_run": kwargs["dry_run"],
                "results": [{"status": "planned", "action": "strip_git", "target": "demo"}],
                "errors": [],
                "actions_taken": 0,
                "actions_planned": 1,
                "freed_mb": "0.0",
            }

    monkeypatch.setattr(main, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("src.aradhya.parasite.pipeline.DigestionPipeline", FakePipeline)
    monkeypatch.setattr(main, "render_info", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main, "render_success", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main, "render_error", lambda *_args, **_kwargs: None)

    handled = main._dispatch_command("/parasite gc")

    assert handled is True
    assert captured["dry_run"] is True
    assert captured["strip_git"] is True


def test_dispatch_parasite_absorb_calls_reabsorb(monkeypatch, tmp_path):
    captured = {}

    class FakePipeline:
        def __init__(self, project_root):
            self.project_root = project_root

        def reabsorb(self, target):
            captured["target"] = target
            return SimpleNamespace(
                error="",
                stage_results={"ABSORB": {"artifacts": {"count": 2}}},
            )

    monkeypatch.setattr(main, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("src.aradhya.parasite.pipeline.DigestionPipeline", FakePipeline)
    monkeypatch.setattr(main, "render_info", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main, "render_success", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main, "render_error", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main, "render_warning", lambda *_args, **_kwargs: None)

    handled = main._dispatch_command("/parasite absorb demo")

    assert handled is True
    assert captured["target"] == "demo"


def test_dispatch_parasite_dedup_defaults_to_dry_run(monkeypatch, tmp_path):
    captured = {}

    class FakePipeline:
        def __init__(self, project_root):
            self.project_root = project_root

    class FakeDeduper:
        def __init__(self, project_root, confirmation_gate=None):
            captured["project_root"] = project_root
            captured["gate"] = confirmation_gate

        def run_deduplication(self, *, dry_run=True):
            captured["dry_run"] = dry_run
            return [{"status": "planned", "duplicate": "host-demo", "base": "native"}]

    monkeypatch.setattr(main, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("src.aradhya.parasite.pipeline.DigestionPipeline", FakePipeline)
    monkeypatch.setattr("src.aradhya.parasite.deduplicator.SkillDeduplicator", FakeDeduper)
    monkeypatch.setattr(main, "render_info", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main, "render_success", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main, "render_error", lambda *_args, **_kwargs: None)

    handled = main._dispatch_command("/parasite dedup")

    assert handled is True
    assert captured["dry_run"] is True
    assert captured["gate"] is None
