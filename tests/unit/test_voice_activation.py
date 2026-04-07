from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from src.aradhya.runtime_profile import build_default_runtime_profile
from src.aradhya.voice_activation import VoiceActivatedAradhya, describe_voice_activation_support
from src.aradhya.voice_pipeline import VoiceJobResult


class FakeAssistant:
    def __init__(self):
        self.state = type(
            "State",
            (),
            {"is_awake": False, "pending_plan": None},
        )()
        self.wake_count = 0
        self.last_transcript = None

    def handle_wake(self, source):
        del source
        self.state.is_awake = True
        self.wake_count += 1
        return type("Response", (), {"spoken_response": "Aradhya is awake."})()

    def handle_transcript(self, transcript: str):
        self.last_transcript = transcript
        return type(
            "Response",
            (),
            {
                "spoken_response": "I am ready to open that path. Say yes proceed when you want me to execute it.",
                "awaiting_confirmation": True,
            },
        )()


class FakeVoiceManager:
    def __init__(self, profile):
        self.profile = profile
        self.processed_paths: list[Path] = []
        self.ensure_called = False

    def ensure_directories(self):
        self.ensure_called = True

    def process_audio_file(self, audio_path: Path):
        self.processed_paths.append(audio_path)
        transcript_path = self.profile.transcripts_dir / "capture.txt"
        return VoiceJobResult(
            audio_path=audio_path,
            status="processed",
            message="Processed live capture.",
            transcript_text="open notes",
            transcript_path=transcript_path,
            archived_audio_path=self.profile.processed_audio_dir / audio_path.name,
        )


class FakeMicrophone:
    def __init__(self):
        self._recording = False
        self.recorded_paths: list[Path] = []
        self.cancel_count = 0

    def is_recording(self) -> bool:
        return self._recording

    def cancel_recording(self) -> None:
        self._recording = False
        self.cancel_count += 1

    def record_until_silence(self, output_path: Path, on_speaking_started=None):
        self._recording = True
        self.recorded_paths.append(output_path)
        if on_speaking_started is not None:
            on_speaking_started()
        self._recording = False
        return type(
            "RecordingResult",
            (),
            {
                "success": True,
                "audio_path": output_path,
                "duration_seconds": 1.0,
                "error_message": None,
            },
        )()


class FakeHotkeyListener:
    def __init__(self):
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def is_running(self) -> bool:
        return self.started and not self.stopped


def build_runtime_profile(tmp_path):
    profile = build_default_runtime_profile(tmp_path)
    return replace(
        profile,
        voice=replace(
            profile.voice,
            provider="faster_whisper",
            audio_inbox_dir=tmp_path / "audio" / "inbox",
            processed_audio_dir=tmp_path / "audio" / "processed",
            transcripts_dir=tmp_path / "audio" / "transcripts",
            manual_transcripts_dir=tmp_path / "audio" / "manual_transcripts",
        ),
    )


def test_voice_activation_routes_live_capture_into_assistant(tmp_path):
    runtime_profile = build_runtime_profile(tmp_path)
    outputs: list[str] = []
    assistant = FakeAssistant()
    voice_manager = FakeVoiceManager(runtime_profile.voice)
    microphone = FakeMicrophone()
    hotkey_listener = FakeHotkeyListener()

    runtime = VoiceActivatedAradhya(
        assistant=assistant,
        voice_manager=voice_manager,
        runtime_profile=runtime_profile,
        output_handler=outputs.append,
        microphone=microphone,
        hotkey_listener=hotkey_listener,
    )

    runtime.start()
    runtime._handle_hotkey_press()

    assert voice_manager.ensure_called is True
    assert assistant.wake_count == 1
    assert microphone.recorded_paths
    assert voice_manager.processed_paths == microphone.recorded_paths
    assert assistant.last_transcript == "open notes"
    assert any("Recording started" in line for line in outputs)
    assert any("Heard > open notes" in line for line in outputs)
    assert any("yes proceed" in line for line in outputs)


def test_voice_activation_does_not_rewake_when_assistant_is_already_awake(tmp_path):
    runtime_profile = build_runtime_profile(tmp_path)
    assistant = FakeAssistant()
    assistant.state.is_awake = True
    voice_manager = FakeVoiceManager(runtime_profile.voice)

    runtime = VoiceActivatedAradhya(
        assistant=assistant,
        voice_manager=voice_manager,
        runtime_profile=runtime_profile,
        output_handler=lambda _message: None,
        microphone=FakeMicrophone(),
        hotkey_listener=FakeHotkeyListener(),
    )

    runtime.start()
    runtime._handle_hotkey_press()

    assert assistant.wake_count == 0
    assert assistant.last_transcript == "open notes"


def test_voice_activation_support_rejects_manual_transcript_provider(tmp_path):
    runtime_profile = build_default_runtime_profile(tmp_path)
    support = describe_voice_activation_support(runtime_profile)

    assert support.available is False
    assert "requires a self-transcribing voice provider" in support.message
