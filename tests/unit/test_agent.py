from __future__ import annotations

from datetime import datetime, timedelta

from src.aradhya.assistant_core import AradhyaAssistant
from src.aradhya.assistant_models import (
    AssistantPreferences,
    DirectoryIndexPolicy,
    PlanKind,
    WakeSource,
)
from src.aradhya.model_provider import ModelHealth, ModelResult


def build_test_preferences(tmp_path, *, refresh_interval_seconds: int = 60):
    return AssistantPreferences(
        user_roots=(tmp_path,),
        directory_index_path=tmp_path / "directory-index.txt",
        context_cache_dir=tmp_path / "context-cache",
        confirmation_phrases=("yes proceed",),
        security_blog_urls=("https://example.com/security",),
        project_markers=("pyproject.toml",),
        game_library_roots=tuple(),
        allow_live_execution=False,
        directory_index_policy=DirectoryIndexPolicy(
            max_nodes=1000,
            refresh_interval_seconds=refresh_interval_seconds,
        ),
    )


class SequenceModelProvider:
    def __init__(self, responses: list[str]):
        self.responses = responses
        self.prompts: list[str] = []

    def health_check(self) -> ModelHealth:
        return ModelHealth(
            reachable=True,
            ready=True,
            provider="fake",
            configured_model="fake",
            available_models=("fake",),
            message="ready",
        )

    def generate(self, prompt: str, *, system_prompt: str | None = None) -> ModelResult:
        self.prompts.append(prompt)
        index = min(len(self.prompts) - 1, len(self.responses) - 1)
        return ModelResult(
            text=self.responses[index],
            model="fake",
            provider="fake",
            raw={},
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
    assert response.index_snapshot.refreshed is False
    assert "docs" in response.spoken_response


def test_wake_reuses_fresh_directory_cache_within_refresh_window(tmp_path):
    assistant = AradhyaAssistant(
        build_test_preferences(tmp_path),
        now_provider=lambda: datetime(2026, 4, 5, 10, 0, 0),
    )

    first = assistant.handle_wake(WakeSource.FLOATING_ICON)
    second = assistant.handle_wake(WakeSource.FLOATING_ICON)

    assert first.index_snapshot is not None
    assert first.index_snapshot.refreshed is True
    assert second.index_snapshot is not None
    assert second.index_snapshot.refreshed is False
    assert "reused the fresh local directory cache" in second.spoken_response


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


def test_local_query_rebuilds_cache_after_refresh_window_expires(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "one.txt").write_text("one", encoding="utf-8")

    class MutableClock:
        def __init__(self, current: datetime):
            self.current = current

        def now(self) -> datetime:
            return self.current

        def advance(self, *, seconds: int) -> None:
            self.current += timedelta(seconds=seconds)

    clock = MutableClock(datetime(2026, 4, 5, 10, 0, 0))
    assistant = AradhyaAssistant(
        build_test_preferences(tmp_path, refresh_interval_seconds=60),
        now_provider=clock.now,
    )
    first_wake = assistant.handle_wake(WakeSource.FLOATING_ICON)
    clock.advance(seconds=61)

    response = assistant.handle_transcript(
        "find the folder with the highest concentration of .txt files"
    )

    assert first_wake.index_snapshot is not None
    assert first_wake.index_snapshot.refreshed is True
    assert response.index_snapshot is not None
    assert response.index_snapshot.refreshed is True


def test_complex_unknown_request_routes_to_confirmed_agent_task(tmp_path):
    model_provider = SequenceModelProvider(
        [
            "not valid classifier json",
            "I inspected what I could and here is the answer.",
        ]
    )
    assistant = AradhyaAssistant(
        build_test_preferences(tmp_path),
        model_provider=model_provider,
        now_provider=lambda: datetime(2026, 4, 5, 10, 0, 0),
        project_root=tmp_path,
    )
    assistant.handle_wake(WakeSource.FLOATING_ICON)

    response = assistant.handle_transcript("review this project and tell me the risks")

    assert response.awaiting_confirmation is True
    assert response.plan is not None
    assert response.plan.kind == PlanKind.AGENT_TASK
    assert assistant.state.pending_plan is not None

    confirmation = assistant.handle_transcript("yes proceed")

    assert confirmation.result is not None
    assert confirmation.result.success is True
    assert confirmation.spoken_response == "I inspected what I could and here is the answer."
    assert assistant.session_manager.active_session is not None
    assert assistant.session_manager.active_session.message_count >= 2
