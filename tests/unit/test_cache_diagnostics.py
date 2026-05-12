from __future__ import annotations

from datetime import datetime
from pathlib import Path

from src.aradhya.assistant_models import (
    AssistantPreferences,
    DirectoryIndexPolicy,
    DirectoryIndexSnapshot,
)
from src.aradhya.utils.cache_diagnostics import (
    CacheValidationReport,
    format_cache_validation_report,
    run_cache_validation,
)


def build_test_preferences(tmp_path):
    return AssistantPreferences(
        user_roots=(tmp_path,),
        directory_index_path=tmp_path / "project_tree.txt",
        context_cache_dir=tmp_path / "data" / "processed" / "context",
        confirmation_phrases=("yes proceed",),
        security_blog_urls=("https://example.com/security",),
        project_markers=("pyproject.toml",),
        game_library_roots=tuple(),
        allow_live_execution=False,
        directory_index_policy=DirectoryIndexPolicy(max_nodes=200),
    )


def test_cache_validation_exercises_cold_warm_and_targeted_paths(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "notes.txt").write_text("note", encoding="utf-8")

    report = run_cache_validation(build_test_preferences(tmp_path))

    assert report.cold_snapshot.refreshed is True
    assert report.warm_snapshot.refreshed is False
    assert report.manifest_path.exists()
    assert report.shard_paths
    assert report.exact_query is not None
    assert report.exact_lookup_found is True
    assert report.repeat_miss_negative_cached is True
    assert report.targeted_skip_reason is None
    assert report.targeted_probe_path is not None
    assert report.targeted_lookup_found is True
    assert report.targeted_snapshot_refreshed is True
    assert report.cleanup_performed is True
    assert not report.targeted_probe_path.exists()

    rendered = format_cache_validation_report(report)
    assert any("Cold refresh" in line for line in rendered)
    assert any("Warm reuse" in line for line in rendered)
    assert any("Exact lookup" in line for line in rendered)
    assert any("negative_cache=yes" in line for line in rendered)
    assert any("Targeted lookup found probe: yes" in line for line in rendered)


def test_format_cache_validation_report_full():
    report = CacheValidationReport(
        cold_snapshot=DirectoryIndexSnapshot(
            path=Path("/cold/path.txt"),
            generated_at=datetime(2023, 1, 1),
            reason="test",
            scanned_roots=(),
            node_count=10,
            truncated=False,
            refreshed=True,
        ),
        cold_refresh_seconds=1.5,
        warm_snapshot=DirectoryIndexSnapshot(
            path=Path("/warm/path.txt"),
            generated_at=datetime(2023, 1, 1),
            reason="test",
            scanned_roots=(),
            node_count=10,
            truncated=False,
            refreshed=False,
        ),
        warm_refresh_seconds=0.5,
        manifest_path=Path("/manifest.json"),
        shard_paths=(Path("/shard1.json"), Path("/shard2.json")),
        exact_query="exact_test",
        exact_query_seconds=0.1,
        exact_lookup_found=True,
        miss_query="miss_test",
        first_miss_query_seconds=0.2,
        repeat_miss_query_seconds=0.05,
        repeat_miss_negative_cached=True,
        targeted_query="targeted_test",
        targeted_query_seconds=0.3,
        targeted_lookup_found=True,
        targeted_snapshot_refreshed=True,
        targeted_probe_path=Path("/probe/path.txt"),
        cleanup_performed=True,
        targeted_skip_reason=None,
    )

    formatted = format_cache_validation_report(report)

    assert any(str(Path("/cold/path.txt")) in line for line in formatted)
    assert any(str(Path("/manifest.json")) in line for line in formatted)
    assert "Cache > Drive shards: 2" in formatted
    assert "Cache > Cold refresh: 1.500s (10 summary nodes, refreshed=yes)" in formatted
    assert "Cache > Warm reuse: 0.500s (refreshed=no)" in formatted
    assert "Cache > Exact lookup: exact_test (0.100s, found=yes)" in formatted
    assert "Cache > Miss lookup: miss_test (first=0.200s, repeat=0.050s, negative_cache=yes)" in formatted
    assert "Cache > Targeted query: targeted_test (0.300s)" in formatted
    assert "Cache > Targeted rescan refreshed: yes" in formatted
    assert "Cache > Targeted lookup found probe: yes" in formatted
    assert "Cache > Probe cleanup: yes" in formatted


def test_format_cache_validation_report_skipped():
    report = CacheValidationReport(
        cold_snapshot=DirectoryIndexSnapshot(
            path=Path("/cold/path.txt"),
            generated_at=datetime(2023, 1, 1),
            reason="test",
            scanned_roots=(),
            node_count=10,
            truncated=False,
            refreshed=True,
        ),
        cold_refresh_seconds=1.5,
        warm_snapshot=DirectoryIndexSnapshot(
            path=Path("/warm/path.txt"),
            generated_at=datetime(2023, 1, 1),
            reason="test",
            scanned_roots=(),
            node_count=10,
            truncated=False,
            refreshed=False,
        ),
        warm_refresh_seconds=0.5,
        manifest_path=Path("/manifest.json"),
        shard_paths=(Path("/shard1.json"), Path("/shard2.json")),
        exact_query=None,
        exact_query_seconds=0.0,
        exact_lookup_found=False,
        miss_query="miss_test",
        first_miss_query_seconds=0.2,
        repeat_miss_query_seconds=0.05,
        repeat_miss_negative_cached=False,
        targeted_query="targeted_test",
        targeted_query_seconds=0.3,
        targeted_lookup_found=False,
        targeted_snapshot_refreshed=False,
        targeted_probe_path=None,
        cleanup_performed=False,
        targeted_skip_reason="Skipped for testing",
    )

    formatted = format_cache_validation_report(report)

    assert "Cache > Exact lookup: no cached query available" in formatted
    assert "Cache > Targeted rescan skipped: Skipped for testing" in formatted
    assert not any("Targeted query" in line for line in formatted)
