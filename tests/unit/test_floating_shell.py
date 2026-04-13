from __future__ import annotations

from datetime import datetime

import src.aradhya.floating_shell as floating_shell_module
from src.aradhya.assistant_core import AradhyaAssistant
from src.aradhya.assistant_models import AssistantPreferences, DirectoryIndexPolicy
from src.aradhya.floating_shell import FloatingShellController
from src.aradhya.runtime_profile import build_default_runtime_profile
from src.aradhya.voice_activation import VoiceActivationSupport


def build_test_preferences(tmp_path):
    return AssistantPreferences(
        user_roots=(tmp_path,),
        directory_index_path=tmp_path / "directory-index.txt",
        context_cache_dir=tmp_path / "context-cache",
        confirmation_phrases=("yes proceed",),
        security_blog_urls=("https://example.com/security",),
        project_markers=("pyproject.toml",),
        game_library_roots=tuple(),
        allow_live_execution=False,
        directory_index_policy=DirectoryIndexPolicy(max_nodes=1000),
    )


class FakeVoiceManager:
    def __init__(self):
        self.ensure_called = False

    def ensure_directories(self):
        self.ensure_called = True


def build_controller(tmp_path, *, voice_runtime_factory=None) -> FloatingShellController:
    assistant = AradhyaAssistant(
        build_test_preferences(tmp_path),
        now_provider=lambda: datetime(2026, 4, 5, 10, 0, 0),
    )
    return FloatingShellController(
        assistant=assistant,
        runtime_profile=build_default_runtime_profile(tmp_path),
        voice_manager=FakeVoiceManager(),
        voice_runtime_factory=voice_runtime_factory,
    )


def test_floating_shell_controller_exposes_v1_controls_and_local_status(tmp_path):
    controller = build_controller(tmp_path)

    specs = controller.control_specs()

    assert tuple(spec.control_id for spec in specs) == (
        "mic",
        "screen",
        "advanced",
        "interaction",
    )
    assert tuple(spec.label for spec in specs) == ("Mic", "Screen", "A", "I")
    assert all(spec.control_id != "camera" for spec in specs)
    assert controller.shell_state_snapshot().cloud_features_enabled is False
    assert "Local only" in controller.status_line()
    assert "Cloud off" in controller.status_line()


def test_floating_shell_controller_toggles_session_state_and_screen_attachment(tmp_path):
    screenshot_path = tmp_path / "screen.png"
    screenshot_path.write_text("fake image", encoding="utf-8")
    controller = build_controller(tmp_path)

    interaction_message = controller.toggle_interaction()
    advanced_message = controller.arm_advanced_request()
    screen_message = controller.toggle_screen_context(screenshot_path)

    snapshot = controller.shell_state_snapshot()
    assert "Interaction unlocked" in interaction_message
    assert "Advanced mode is armed" in advanced_message
    assert "screen.png" in screen_message
    assert snapshot.interaction_enabled is True
    assert snapshot.advanced_next_request is True
    assert snapshot.screen_context_active is True
    assert controller.screen_attachment_path() == screenshot_path

    screen_off_message = controller.toggle_screen_context()

    assert "Screen guidance mode is off" in screen_off_message
    assert controller.shell_state_snapshot().screen_context_active is False
    assert controller.screen_attachment_path() is None


def test_floating_shell_controller_submit_text_auto_wakes_and_routes_request(tmp_path):
    controller = build_controller(tmp_path)

    lines = controller.submit_text("enable debate mode")

    assert any("awake" in line.lower() for line in lines)
    assert any("Debate AI mode is now enabled" in line for line in lines)
    assert controller.assistant.state.is_awake is True


def test_floating_shell_controller_mic_returns_help_when_capture_is_unavailable(tmp_path):
    controller = build_controller(tmp_path)

    lines = controller.capture_once()

    assert len(lines) == 1
    assert lines[0].startswith("Voice >")
    assert "Mic capture requires a self-transcribing voice provider" in lines[0]


def test_floating_shell_controller_mic_uses_voice_runtime_when_capture_is_available(
    monkeypatch,
    tmp_path,
):
    def fake_support(_profile):
        return VoiceActivationSupport(True, "ready")

    def fake_runtime_factory(output_handler):
        class FakeRuntime:
            def capture_once(self):
                output_handler("Voice > Simulated capture.")
                output_handler("Aradhya > Simulated voice request routed.")

        return FakeRuntime()

    monkeypatch.setattr(
        floating_shell_module,
        "describe_voice_capture_support",
        fake_support,
    )
    controller = build_controller(tmp_path, voice_runtime_factory=fake_runtime_factory)

    lines = controller.capture_once()

    assert lines == (
        "Voice > Simulated capture.",
        "Aradhya > Simulated voice request routed.",
    )
