"""Tests for the Parasite OS digestion pipeline."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.aradhya.parasite.checkpoint import (
    STAGES,
    Checkpoint,
    load_checkpoint,
    next_stage,
    record_stage_complete,
    record_stage_failure,
    record_stage_start,
    save_checkpoint,
)
from src.aradhya.parasite.analyzer import (
    analyze_target,
    analyze_public_apis_readme,
    generate_digest,
)
from src.aradhya.parasite.ledger import (
    build_integration_ledger,
    find_candidate,
    write_integration_ledger,
)


@pytest.fixture
def hosts_root(tmp_path: Path) -> Path:
    hosts = tmp_path / "Hosts"
    hosts.mkdir()
    return hosts


@pytest.fixture
def sample_target(hosts_root: Path) -> Path:
    target = hosts_root / "test-repo"
    target.mkdir()
    (target / "README.md").write_text(
        "# Test Repo\n\nA sample repo for testing the digestion pipeline.\n\n"
        "## Features\n- Feature 1\n- Feature 2\n",
        encoding="utf-8",
    )
    (target / "requirements.txt").write_text("requests>=2.0\nloguru\n", encoding="utf-8")
    (target / "setup.py").write_text("from setuptools import setup\n", encoding="utf-8")
    return target


@pytest.fixture
def public_apis_target(hosts_root: Path) -> Path:
    target = hosts_root / "public-apis"
    target.mkdir()
    (target / "README.md").write_text(
        "# Public APIs\n\nA collective list of free APIs.\n\n"
        "### Animals\n"
        "| API | Description | Auth | HTTPS | Cors |\n"
        "|:---|:---|:---|:---|:---|\n"
        "| [Cat Facts](https://catfact.ninja/) | Daily cat facts | No | Yes | No |\n"
        "| [Dog CEO](https://dog.ceo/dog-api/) | Random dog images | No | Yes | Yes |\n"
        "\n### Weather\n"
        "| API | Description | Auth | HTTPS | Cors |\n"
        "|:---|:---|:---|:---|:---|\n"
        "| [Open-Meteo](https://open-meteo.com/) | Weather forecasts | No | Yes | Yes |\n",
        encoding="utf-8",
    )
    (target / "LICENSE").write_text("MIT License\n", encoding="utf-8")
    return target


# ── Checkpoint tests ──────────────────────────────────────────────────


class TestCheckpoint:
    def test_save_and_load_checkpoint(self, hosts_root: Path):
        cp = Checkpoint(target="my-repo", source_url="https://github.com/test/repo")
        cp.started_at = "2026-05-19T00:00:00Z"

        path = save_checkpoint(hosts_root, cp)
        assert path.is_file()

        loaded = load_checkpoint(hosts_root, "my-repo")
        assert loaded is not None
        assert loaded.target == "my-repo"
        assert loaded.source_url == "https://github.com/test/repo"

    def test_load_missing_checkpoint(self, hosts_root: Path):
        assert load_checkpoint(hosts_root, "nonexistent") is None

    def test_stage_progression(self, hosts_root: Path):
        cp = Checkpoint(target="test")

        assert next_stage(cp) == "ENGULF"

        record_stage_start(cp, "ENGULF")
        assert cp.current_stage == "ENGULF"

        record_stage_complete(cp, "ENGULF", artifacts={"exists": True})
        assert "ENGULF" in cp.completed_stages
        assert next_stage(cp) == "ISOLATE"

    def test_stage_failure_and_resume(self, hosts_root: Path):
        cp = Checkpoint(target="test")
        record_stage_complete(cp, "ENGULF")
        record_stage_complete(cp, "ISOLATE")

        record_stage_start(cp, "CHEW")
        record_stage_failure(cp, "CHEW", "FileNotFoundError: target missing")

        assert cp.error == "FileNotFoundError: target missing"
        assert "CHEW" not in cp.completed_stages

        # Save and reload
        save_checkpoint(hosts_root, cp)
        loaded = load_checkpoint(hosts_root, "test")
        assert loaded is not None
        assert loaded.error == "FileNotFoundError: target missing"
        assert next_stage(loaded) == "CHEW"

    def test_all_stages_complete(self, hosts_root: Path):
        cp = Checkpoint(target="done")
        for stage in STAGES:
            record_stage_complete(cp, stage)
        assert next_stage(cp) is None


# ── Analyzer tests ────────────────────────────────────────────────────


class TestAnalyzer:
    def test_analyze_python_target(self, sample_target: Path):
        result = analyze_target(sample_target)

        assert result["name"] == "test-repo"
        assert result["type"] == "python"
        assert "requests" in result["dependencies"]
        assert "loguru" in result["dependencies"]
        assert result["files_scanned"] > 0
        assert "sample repo" in result["description"].lower()

    def test_analyze_missing_target(self, hosts_root: Path):
        result = analyze_target(hosts_root / "nonexistent")
        assert "error" in result

    def test_generate_digest(self, sample_target: Path):
        analysis = analyze_target(sample_target)
        digest_path = sample_target / ".parasite" / "DIGEST.md"
        result = generate_digest(analysis, digest_path)

        assert result.is_file()
        content = result.read_text(encoding="utf-8")
        assert "# Digest: test-repo" in content
        assert "python" in content.lower()
        assert "requests" in content

    def test_public_apis_parser_skips_separators(self, public_apis_target: Path):
        """The old parser included :--- separator rows as entries. This must not happen."""
        entries = analyze_public_apis_readme(public_apis_target)

        assert len(entries) == 3
        names = [e["API"] for e in entries]
        assert "Cat Facts" in names
        assert "Dog CEO" in names
        assert "Open-Meteo" in names

        # No garbage entries
        for entry in entries:
            assert not entry["API"].startswith(":")
            assert not entry["API"].startswith("-")
            assert len(entry["API"]) > 2

    def test_public_apis_parser_extracts_links(self, public_apis_target: Path):
        entries = analyze_public_apis_readme(public_apis_target)

        cat_facts = next(e for e in entries if e["API"] == "Cat Facts")
        assert cat_facts["Link"] == "https://catfact.ninja/"
        assert cat_facts["Category"] == "Animals"
        assert cat_facts["Auth"] == "No"

    def test_public_apis_parser_detects_https(self, public_apis_target: Path):
        entries = analyze_public_apis_readme(public_apis_target)
        for entry in entries:
            assert entry["HTTPS"] is True


# ── Pipeline integration test ─────────────────────────────────────────


class TestPipeline:
    def test_digest_full_pipeline(self, hosts_root: Path, sample_target: Path):
        from src.aradhya.parasite.pipeline import DigestionPipeline

        project_root = hosts_root.parent
        pipeline = DigestionPipeline(project_root)

        cp = pipeline.digest("test-repo")

        assert "ENGULF" in cp.completed_stages
        assert "ISOLATE" in cp.completed_stages
        assert "CHEW" in cp.completed_stages
        assert "SWALLOW" in cp.completed_stages

        # Check DIGEST.md was generated
        digest = sample_target / ".parasite" / "DIGEST.md"
        assert digest.is_file()

    def test_list_targets(self, hosts_root: Path, sample_target: Path):
        from src.aradhya.parasite.pipeline import DigestionPipeline

        project_root = hosts_root.parent
        pipeline = DigestionPipeline(project_root)

        targets = pipeline.list_targets()
        assert len(targets) >= 1
        names = [t["name"] for t in targets]
        assert "test-repo" in names

    def test_resume_from_checkpoint(self, hosts_root: Path, sample_target: Path):
        from src.aradhya.parasite.pipeline import DigestionPipeline

        project_root = hosts_root.parent
        pipeline = DigestionPipeline(project_root)

        # Simulate a partial run
        cp = Checkpoint(target="test-repo")
        record_stage_complete(cp, "ENGULF", artifacts={"exists": True})
        record_stage_complete(cp, "ISOLATE", artifacts={"trust_score": "HIGH"})
        save_checkpoint(hosts_root, cp)

        # Resume should pick up from CHEW
        resumed = pipeline.resume("test-repo")
        assert resumed is not None
        assert "CHEW" in resumed.completed_stages
        assert "SWALLOW" in resumed.completed_stages


class TestIntegrationLedger:
    def test_builds_candidate_from_completed_checkpoint(
        self,
        hosts_root: Path,
        sample_target: Path,
    ):
        from src.aradhya.parasite.pipeline import DigestionPipeline

        project_root = hosts_root.parent
        pipeline = DigestionPipeline(project_root)
        pipeline.digest("test-repo")

        candidates = build_integration_ledger(project_root)
        candidate = find_candidate(candidates, "test-repo")

        assert candidate is not None
        assert candidate.completed_stage_count == 7
        assert candidate.status == "ready"
        assert candidate.validate_passed is True
        assert candidate.absorb_completed is True
        assert candidate.digest_exists is True
        assert candidate.score > 0

    def test_writes_ledger_json(self, hosts_root: Path, sample_target: Path):
        from src.aradhya.parasite.pipeline import DigestionPipeline

        project_root = hosts_root.parent
        pipeline = DigestionPipeline(project_root)
        pipeline.digest("test-repo")

        path = write_integration_ledger(project_root)
        data = json.loads(path.read_text(encoding="utf-8"))

        assert path.is_file()
        assert data["version"] == 1
        assert data["candidate_count"] == 1
        assert data["candidates"][0]["repo"] == "test-repo"

    def test_includes_archived_completed_hosts(
        self,
        hosts_root: Path,
        public_apis_target: Path,
    ):
        from src.aradhya.parasite.pipeline import DigestionPipeline

        project_root = hosts_root.parent
        pipeline = DigestionPipeline(project_root)
        pipeline.digest("public-apis")

        archived_root = hosts_root / ".archived"
        archived_root.mkdir()
        archived = archived_root / "public-apis-archive"
        public_apis_target.rename(archived)

        candidates = build_integration_ledger(project_root)
        candidate = find_candidate(candidates, "public-apis")

        assert candidate is not None
        assert candidate.archived is True
        assert candidate.absorbed_count == 1
        assert candidate.priority == "live"
