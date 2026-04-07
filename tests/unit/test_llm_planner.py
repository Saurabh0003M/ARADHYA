from __future__ import annotations

from datetime import datetime

from src.aradhya.assistant_core import AradhyaAssistant
from src.aradhya.assistant_models import (
    AssistantPreferences,
    DirectoryIndexPolicy,
    PlanKind,
    WakeSource,
)
from src.aradhya.model_provider import ModelHealth, ModelResult


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


class FakeModelProvider:
    def __init__(self, response_text: str | None = None, error: Exception | None = None):
        self.response_text = response_text or ""
        self.error = error
        self.last_prompt = None
        self.last_system_prompt = None

    def health_check(self) -> ModelHealth:
        return ModelHealth(
            reachable=True,
            ready=True,
            provider="fake",
            configured_model="fake-model",
            available_models=("fake-model",),
            message="ready",
        )

    def generate(self, prompt: str, *, system_prompt: str | None = None) -> ModelResult:
        self.last_prompt = prompt
        self.last_system_prompt = system_prompt
        if self.error is not None:
            raise self.error
        return ModelResult(
            text=self.response_text,
            model="fake-model",
            provider="fake",
            raw={},
        )


def test_llm_fallback_routes_to_open_path_and_keeps_confirmation_gate(tmp_path):
    target_dir = tmp_path / "Launchpad"
    target_dir.mkdir()
    model_provider = FakeModelProvider(
        """
        {"intent": "OPEN_PATH", "confidence": 0.91, "reasoning": "User wants a local folder opened", "target": "Launchpad", "enabled": null}
        """
    )
    assistant = AradhyaAssistant(
        build_test_preferences(tmp_path),
        model_provider=model_provider,
        now_provider=lambda: datetime(2026, 4, 5, 10, 0, 0),
    )
    assistant.handle_wake(WakeSource.FLOATING_ICON)

    response = assistant.handle_transcript("please launch the launchpad folder for me")

    assert response.awaiting_confirmation is True
    assert response.plan is not None
    assert response.plan.kind == PlanKind.OPEN_PATH
    assert response.plan.metadata["llm_intent"] == "OPEN_PATH"
    assert assistant.state.pending_plan is not None

    confirmation = assistant.handle_transcript("yes proceed")

    assert confirmation.result is not None
    assert confirmation.result.success is True
    assert "Dry run" in confirmation.spoken_response
    assert "Launchpad" in confirmation.spoken_response


def test_llm_fallback_rejects_low_confidence_results(tmp_path):
    model_provider = FakeModelProvider(
        """
        {"intent": "OPEN_PATH", "confidence": 0.33, "reasoning": "Weak guess", "target": "Notes", "enabled": null}
        """
    )
    assistant = AradhyaAssistant(
        build_test_preferences(tmp_path),
        model_provider=model_provider,
        now_provider=lambda: datetime(2026, 4, 5, 10, 0, 0),
    )
    assistant.handle_wake(WakeSource.FLOATING_ICON)

    response = assistant.handle_transcript("launch something maybe called notes")

    assert response.awaiting_confirmation is False
    assert response.plan is not None
    assert response.plan.kind == PlanKind.UNKNOWN
    assert assistant.state.pending_plan is None
    assert "not confident enough" in response.spoken_response


def test_llm_fallback_handles_invalid_json_without_execution(tmp_path):
    model_provider = FakeModelProvider("not valid json")
    assistant = AradhyaAssistant(
        build_test_preferences(tmp_path),
        model_provider=model_provider,
        now_provider=lambda: datetime(2026, 4, 5, 10, 0, 0),
    )
    assistant.handle_wake(WakeSource.FLOATING_ICON)

    response = assistant.handle_transcript("do something ambiguous")

    assert response.plan is not None
    assert response.plan.kind == PlanKind.UNKNOWN
    assert assistant.state.pending_plan is None
    assert "could not safely classify" in response.spoken_response


def test_llm_fallback_handles_provider_errors(tmp_path):
    model_provider = FakeModelProvider(error=RuntimeError("provider offline"))
    assistant = AradhyaAssistant(
        build_test_preferences(tmp_path),
        model_provider=model_provider,
        now_provider=lambda: datetime(2026, 4, 5, 10, 0, 0),
    )
    assistant.handle_wake(WakeSource.FLOATING_ICON)

    response = assistant.handle_transcript("please figure this out for me")

    assert response.plan is not None
    assert response.plan.kind == PlanKind.UNKNOWN
    assert "provider offline" in response.spoken_response


def test_llm_fallback_accepts_markdown_wrapped_json(tmp_path):
    target_dir = tmp_path / "Notes"
    target_dir.mkdir()
    model_provider = FakeModelProvider(
        """
        ```json
        {"intent": "OPEN_PATH", "confidence": 0.88, "reasoning": "The user wants a folder", "target": "Notes", "enabled": null}
        ```
        """
    )
    assistant = AradhyaAssistant(
        build_test_preferences(tmp_path),
        model_provider=model_provider,
        now_provider=lambda: datetime(2026, 4, 5, 10, 0, 0),
    )
    assistant.handle_wake(WakeSource.FLOATING_ICON)

    response = assistant.handle_transcript("launch the notes folder")

    assert response.plan is not None
    assert response.plan.kind == PlanKind.OPEN_PATH
    assert response.awaiting_confirmation is True
