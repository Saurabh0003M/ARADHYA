from __future__ import annotations

from datetime import datetime

from src.aradhya.assistant_core import AradhyaAssistant
from src.aradhya.assistant_models import (
    AssistantPreferences,
    DirectoryIndexPolicy,
    PlanKind,
    WakeSource,
)


def build_test_preferences(tmp_path):
    return AssistantPreferences(
        user_roots=(tmp_path,),
        directory_index_path=tmp_path / "directory-index.txt",
        confirmation_phrases=("yes proceed",),
        security_blog_urls=("https://example.com/security",),
        project_markers=("pyproject.toml",),
        game_library_roots=tuple(),
        allow_live_execution=False,
        directory_index_policy=DirectoryIndexPolicy(max_nodes=1000),
    )


def test_open_request_waits_for_explicit_confirmation(tmp_path):
    target_dir = tmp_path / "Notes"
    target_dir.mkdir()

    assistant = AradhyaAssistant(
        build_test_preferences(tmp_path),
        now_provider=lambda: datetime(2026, 4, 5, 10, 0, 0),
    )
    assistant.handle_wake(WakeSource.FLOATING_ICON)

    response = assistant.handle_transcript("open Notes")

    assert response.awaiting_confirmation is True
    assert response.plan is not None
    assert response.plan.kind == PlanKind.OPEN_PATH
    assert assistant.state.pending_plan is not None

    confirmation = assistant.handle_transcript("yes proceed")

    assert confirmation.result is not None
    assert confirmation.result.success is True
    assert "Dry run" in confirmation.spoken_response
    assert assistant.state.pending_plan is None


def test_local_query_refreshes_directory_index(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "one.txt").write_text("one", encoding="utf-8")
    (docs_dir / "two.txt").write_text("two", encoding="utf-8")
    (docs_dir / "notes.md").write_text("md", encoding="utf-8")

    assistant = AradhyaAssistant(
        build_test_preferences(tmp_path),
        now_provider=lambda: datetime(2026, 4, 5, 10, 0, 0),
    )
    assistant.handle_wake(WakeSource.FLOATING_ICON)

    response = assistant.handle_transcript(
        "find the folder with the highest concentration of .txt files"
    )

    assert response.plan is not None
    assert response.plan.kind == PlanKind.LOCATE_TXT_DENSE_FOLDER
    assert response.index_snapshot is not None
    assert response.index_snapshot.path.exists()
    assert response.index_snapshot.reason == "local_query"
    assert "docs" in response.spoken_response


def test_toggle_debate_executes_immediately_without_confirmation(tmp_path):
    assistant = AradhyaAssistant(
        build_test_preferences(tmp_path),
        now_provider=lambda: datetime(2026, 4, 5, 10, 0, 0),
    )
    assistant.handle_wake(WakeSource.FLOATING_ICON)

    response = assistant.handle_transcript("enable debate mode")

    assert response.awaiting_confirmation is False
    assert response.result is not None
    assert response.result.success is True
    assert assistant.state.debate_mode_enabled is True
    assert assistant.state.pending_plan is None


def test_research_request_routes_to_debate_when_enabled(tmp_path):
    assistant = AradhyaAssistant(
        build_test_preferences(tmp_path),
        now_provider=lambda: datetime(2026, 4, 5, 10, 0, 0),
    )
    assistant.handle_wake(WakeSource.FLOATING_ICON)
    assistant.state.debate_mode_enabled = True

    response = assistant.handle_transcript("research the safest rollout for this change")

    assert response.plan is not None
    assert response.plan.kind == PlanKind.DEBATE_RESEARCH
    assert response.awaiting_confirmation is False
    assert "multi-model debate workflow" in response.spoken_response
