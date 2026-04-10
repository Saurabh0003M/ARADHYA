from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from src.aradhya.assistant_indexer import DirectoryIndexManager
from src.aradhya.assistant_models import AssistantPreferences, DirectoryIndexPolicy


class MutableClock:
    def __init__(self, current: datetime):
        self.current = current

    def now(self) -> datetime:
        return self.current

    def advance(self, *, seconds: int) -> None:
        self.current += timedelta(seconds=seconds)


def build_test_preferences(
    tmp_path: Path,
    *,
    user_roots: tuple[Path, ...],
    game_library_roots: tuple[Path, ...] = (),
    refresh_interval_seconds: int = 60,
    max_nodes: int = 200,
    max_name_candidates_per_key: int = 25,
    miss_cache_ttl_seconds: int = 300,
    miss_refresh_debounce_seconds: float = 2.0,
) -> AssistantPreferences:
    return AssistantPreferences(
        user_roots=user_roots,
        directory_index_path=tmp_path / "project_tree.txt",
        context_cache_dir=tmp_path / "context-cache",
        confirmation_phrases=("yes proceed",),
        security_blog_urls=("https://example.com/security",),
        project_markers=("pyproject.toml",),
        game_library_roots=game_library_roots,
        allow_live_execution=False,
        directory_index_policy=DirectoryIndexPolicy(
            max_nodes=max_nodes,
            refresh_interval_seconds=refresh_interval_seconds,
            max_name_candidates_per_key=max_name_candidates_per_key,
            miss_cache_ttl_seconds=miss_cache_ttl_seconds,
            miss_refresh_debounce_seconds=miss_refresh_debounce_seconds,
        ),
    )


def test_refresh_creates_manifest_shards_and_summary_artifact(tmp_path):
    user_root = tmp_path / "user"
    docs_dir = user_root / "docs"
    docs_dir.mkdir(parents=True)
    (docs_dir / "one.txt").write_text("one", encoding="utf-8")
    (docs_dir / "two.txt").write_text("two", encoding="utf-8")
    (docs_dir / "notes.md").write_text("md", encoding="utf-8")

    clock = MutableClock(datetime(2026, 4, 5, 10, 0, 0))
    preferences = build_test_preferences(tmp_path, user_roots=(user_root,))
    manager = DirectoryIndexManager(preferences, now_provider=clock.now)

    snapshot = manager.refresh("wake")

    manifest_path = preferences.context_cache_dir / "manifest.json"
    shard_files = list(preferences.context_cache_dir.glob("drive_*.json"))
    summary_text = preferences.directory_index_path.read_text(encoding="utf-8")
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert snapshot.refreshed is True
    assert manifest_path.exists()
    assert shard_files
    assert manifest_payload["refresh_interval_seconds"] == 60
    assert "# Aradhya directory index summary" in summary_text
    assert "[ROOT]" in summary_text
    assert "one.txt" not in summary_text


def test_refresh_if_stale_reuses_fresh_cache_without_rewriting_summary(tmp_path):
    user_root = tmp_path / "user"
    (user_root / "docs").mkdir(parents=True)

    clock = MutableClock(datetime(2026, 4, 5, 10, 0, 0))
    preferences = build_test_preferences(tmp_path, user_roots=(user_root,))
    manager = DirectoryIndexManager(preferences, now_provider=clock.now)

    first_snapshot = manager.refresh("wake")
    first_summary = preferences.directory_index_path.read_text(encoding="utf-8")
    clock.advance(seconds=30)
    second_snapshot = manager.refresh_if_stale("wake")

    assert first_snapshot.refreshed is True
    assert second_snapshot.refreshed is False
    assert second_snapshot.generated_at == first_snapshot.generated_at
    assert preferences.directory_index_path.read_text(encoding="utf-8") == first_summary


def test_invalid_manifest_triggers_rebuild(tmp_path):
    user_root = tmp_path / "user"
    user_root.mkdir()

    clock = MutableClock(datetime(2026, 4, 5, 10, 0, 0))
    preferences = build_test_preferences(tmp_path, user_roots=(user_root,))
    manager = DirectoryIndexManager(preferences, now_provider=clock.now)

    manager.refresh("wake")
    clock.advance(seconds=5)
    (preferences.context_cache_dir / "manifest.json").write_text("{not json", encoding="utf-8")

    snapshot = manager.refresh_if_stale("local_query")

    assert snapshot.refreshed is True
    repaired_manifest = json.loads(
        (preferences.context_cache_dir / "manifest.json").read_text(encoding="utf-8")
    )
    assert repaired_manifest["schema_version"] == 1


def test_named_path_lookup_triggers_targeted_rescan_on_cache_miss(tmp_path):
    user_root = tmp_path / "user"
    user_root.mkdir()

    clock = MutableClock(datetime(2026, 4, 5, 10, 0, 0))
    preferences = build_test_preferences(tmp_path, user_roots=(user_root,))
    manager = DirectoryIndexManager(preferences, now_provider=clock.now)

    manager.refresh("wake")
    clock.advance(seconds=5)
    target_dir = user_root / "Notes"
    target_dir.mkdir()

    matches = manager.find_named_paths("Notes")

    assert target_dir in matches
    assert manager.last_snapshot is not None
    assert manager.last_snapshot.refreshed is True


def test_cached_lookup_results_match_feature_expectations(tmp_path):
    user_root = tmp_path / "user"
    docs_dir = user_root / "docs"
    project_dir = user_root / "passport-project"
    game_root = tmp_path / "games"
    game_dir = game_root / "Minecraft"
    docs_dir.mkdir(parents=True)
    project_dir.mkdir(parents=True)
    game_dir.mkdir(parents=True)

    (docs_dir / "one.txt").write_text("one", encoding="utf-8")
    (docs_dir / "two.txt").write_text("two", encoding="utf-8")
    (docs_dir / "notes.md").write_text("md", encoding="utf-8")

    marker_path = project_dir / "pyproject.toml"
    marker_path.write_text("[project]\nname='passport'\n", encoding="utf-8")
    project_timestamp = datetime(2026, 4, 4, 18, 0, 0).timestamp()
    os.utime(marker_path, (project_timestamp, project_timestamp))
    os.utime(project_dir, (project_timestamp, project_timestamp))

    game_path = game_dir / "minecraft.exe"
    game_path.write_text("binary", encoding="utf-8")
    game_timestamp = datetime(2026, 4, 5, 9, 30, 0).timestamp()
    os.utime(game_path, (game_timestamp, game_timestamp))

    clock = MutableClock(datetime(2026, 4, 5, 10, 0, 0))
    preferences = build_test_preferences(
        tmp_path,
        user_roots=(user_root,),
        game_library_roots=(game_root,),
    )
    manager = DirectoryIndexManager(preferences, now_provider=clock.now)

    manager.refresh("wake")

    txt_folder = manager.find_txt_dense_folder()
    project = manager.find_yesterdays_project(clock.now())
    recent_game = manager.find_recent_game()

    assert txt_folder is not None
    assert txt_folder[0] == docs_dir
    assert project is not None
    assert project[0] == project_dir
    assert recent_game is not None
    assert recent_game[0] == game_path


def test_candidate_lists_are_capped_and_summary_stays_compact(tmp_path):
    user_root = tmp_path / "user"
    user_root.mkdir()

    for index in range(40):
        folder = user_root / f"folder-{index}"
        folder.mkdir()
        (folder / "notes.txt").write_text(str(index), encoding="utf-8")

    clock = MutableClock(datetime(2026, 4, 5, 10, 0, 0))
    preferences = build_test_preferences(
        tmp_path,
        user_roots=(user_root,),
        max_nodes=80,
        max_name_candidates_per_key=25,
    )
    manager = DirectoryIndexManager(preferences, now_provider=clock.now)

    manager.refresh("wake")
    _manifest, shards = manager._load_cache()
    summary_text = preferences.directory_index_path.read_text(encoding="utf-8")

    candidates = []
    for shard in shards.values():
        candidates.extend(shard.name_candidates.get("notes txt", ()))

    assert len(candidates) == 25
    assert "notes.txt" not in summary_text


def test_named_path_lookup_negative_cache_skips_repeat_refreshes(tmp_path, monkeypatch):
    user_root = tmp_path / "user"
    user_root.mkdir()

    clock = MutableClock(datetime(2026, 4, 5, 10, 0, 0))
    preferences = build_test_preferences(
        tmp_path,
        user_roots=(user_root,),
        miss_cache_ttl_seconds=10,
        miss_refresh_debounce_seconds=2.0,
    )
    manager = DirectoryIndexManager(preferences, now_provider=clock.now)
    manager.refresh("wake")

    refresh_calls = 0
    original_refresh = manager._refresh_relevant_roots

    def tracked_refresh(reason: str, **kwargs):
        nonlocal refresh_calls
        refresh_calls += 1
        return original_refresh(reason, **kwargs)

    monkeypatch.setattr(manager, "_refresh_relevant_roots", tracked_refresh)

    assert manager.find_named_paths("missing target") == []
    assert refresh_calls == 1

    clock.advance(seconds=1)
    assert manager.find_named_paths("missing target") == []
    assert refresh_calls == 1

    clock.advance(seconds=11)
    assert manager.find_named_paths("missing target") == []
    assert refresh_calls == 2
