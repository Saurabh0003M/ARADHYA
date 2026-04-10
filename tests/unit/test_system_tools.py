from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from src.aradhya.assistant_models import AssistantPreferences, DirectoryIndexPolicy
from src.aradhya.assistant_system_tools import SystemToolbox


def build_test_preferences(
    tmp_path: Path,
    *,
    user_roots: tuple[Path, ...],
    game_library_roots: tuple[Path, ...] = (),
    security_blog_urls: tuple[str, ...] = ("https://example.com/security",),
) -> AssistantPreferences:
    return AssistantPreferences(
        user_roots=user_roots,
        directory_index_path=tmp_path / "directory-index.txt",
        context_cache_dir=tmp_path / "context-cache",
        confirmation_phrases=("yes proceed",),
        security_blog_urls=security_blog_urls,
        project_markers=("pyproject.toml",),
        game_library_roots=game_library_roots,
        allow_live_execution=False,
        directory_index_policy=DirectoryIndexPolicy(max_nodes=1000),
    )


def test_score_path_prefers_configured_user_roots(tmp_path):
    preferred_root = tmp_path / "preferred"
    other_root = tmp_path / "other"
    preferred_path = preferred_root / "Notes"
    other_path = other_root / "Notes"
    preferred_path.mkdir(parents=True)
    other_path.mkdir(parents=True)

    toolbox = SystemToolbox(
        build_test_preferences(
            tmp_path,
            user_roots=(preferred_root,),
            game_library_roots=(other_root,),
        ),
        MagicMock(),
    )

    preferred_score = toolbox._score_path(preferred_path, "Notes")
    other_score = toolbox._score_path(other_path, "Notes")

    assert preferred_score > other_score


def test_plan_open_security_blogs_skips_invalid_urls(tmp_path):
    toolbox = SystemToolbox(
        build_test_preferences(
            tmp_path,
            user_roots=(tmp_path,),
            security_blog_urls=(
                "https://example.com/security",
                "ftp://example.com/feed",
                "javascript:alert(1)",
                "http://news.example.com/blog",
            ),
        ),
        MagicMock(),
    )

    plan = toolbox.plan_open_security_blogs()

    assert plan.ready is True
    assert plan.metadata["urls"] == [
        "https://example.com/security",
        "http://news.example.com/blog",
    ]
    assert plan.metadata["skipped_url_count"] == 2
    assert "skipped 2 invalid URL" in plan.summary


def test_plan_open_security_blogs_rejects_all_invalid_urls(tmp_path):
    toolbox = SystemToolbox(
        build_test_preferences(
            tmp_path,
            user_roots=(tmp_path,),
            security_blog_urls=("ftp://example.com/feed", "javascript:alert(1)"),
        ),
        MagicMock(),
    )

    plan = toolbox.plan_open_security_blogs()

    assert plan.ready is False
    assert plan.requires_confirmation is False
    assert "nothing safe to open" in plan.summary
