from __future__ import annotations

from src.aradhya.assistant_models import AssistantPreferences, DirectoryIndexPolicy
from src.aradhya.cache_diagnostics import (
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
