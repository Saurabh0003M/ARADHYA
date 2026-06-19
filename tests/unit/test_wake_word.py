from __future__ import annotations

from pathlib import Path

from src.aradhya.assistant_models import WakeSource
from src.aradhya.runtime_profile import VoiceProfile
from src.aradhya.voice.pipeline import VoiceInboxManager
from src.aradhya.voice.transcriber import FileTranscription
from src.aradhya.voice.wake_word import WakeWordListener


def build_voice_profile(tmp_path) -> VoiceProfile:
    return VoiceProfile(
        provider="faster_whisper",
        audio_inbox_dir=tmp_path / "audio" / "inbox",
        processed_audio_dir=tmp_path / "audio" / "processed",
        transcripts_dir=tmp_path / "audio" / "transcripts",
        manual_transcripts_dir=tmp_path / "audio" / "manual_transcripts",
        supported_extensions=(".mp3", ".wav"),
        whisper_command_template=None,
        faster_whisper_model_size="base",
        faster_whisper_device="cpu",
        faster_whisper_compute_type="int8",
        language=None,
        poll_on_wake=True,
    )


class FakeTranscriber:
    """Records calls and mimics a provider that writes the transcript file."""

    def __init__(self, text: str = "arise now", status: str = "processed") -> None:
        self.text = text
        self.status = status
        self.calls: list[tuple[Path, Path]] = []

    def transcribe(self, audio_path, transcript_destination):
        self.calls.append((audio_path, transcript_destination))
        # Faster-whisper / shell providers write to the destination; mimic that
        # so cleanup behaviour is exercised end to end.
        Path(transcript_destination).write_text(self.text, encoding="utf-8")
        return FileTranscription(
            status=self.status,
            message="ok",
            transcript_text=self.text if self.status == "processed" else "",
        )


class BoomTranscriber:
    def transcribe(self, audio_path, transcript_destination):
        del audio_path, transcript_destination
        raise RuntimeError("model failed to load")


class _FakeWakeResponse:
    spoken_response = "I'm awake."


class _FakeState:
    is_awake = False


class FakeAssistant:
    def __init__(self) -> None:
        self.state = _FakeState()
        self.wake_calls: list[WakeSource] = []

    def handle_wake(self, source):
        self.wake_calls.append(source)
        return _FakeWakeResponse()


def build_listener(tmp_path, transcriber):
    profile = build_voice_profile(tmp_path)
    manager = VoiceInboxManager(profile, transcriber_factory=lambda _profile: transcriber)
    manager.ensure_directories()
    assistant = FakeAssistant()
    # Bypass __init__ so we do not open a real microphone in tests.
    listener = WakeWordListener.__new__(WakeWordListener)
    listener.assistant = assistant
    listener.voice_manager = manager
    return listener, assistant, profile


def test_transcribe_audio_returns_text_without_archiving(tmp_path):
    profile = build_voice_profile(tmp_path)
    transcriber = FakeTranscriber(text="hello there")
    manager = VoiceInboxManager(profile, transcriber_factory=lambda _profile: transcriber)
    manager.ensure_directories()

    audio_path = profile.audio_inbox_dir / "chunk.wav"
    audio_path.write_text("fake audio bytes", encoding="utf-8")

    result = manager.transcribe_audio(audio_path)

    assert result.transcript_text == "hello there"
    # transcribe_audio must NOT archive — the source audio stays put.
    assert audio_path.exists()
    assert not (profile.processed_audio_dir / "chunk.wav").exists()


def test_handle_audio_chunk_triggers_wake_on_match(tmp_path):
    transcriber = FakeTranscriber(text="please arise now")
    listener, assistant, profile = build_listener(tmp_path, transcriber)

    audio_path = profile.audio_inbox_dir / "temp_wakeword.wav"
    audio_path.write_text("fake audio bytes", encoding="utf-8")

    detected = listener._handle_audio_chunk(audio_path)

    assert detected is True
    assert assistant.wake_calls == [WakeSource.VOICE]
    # Temp audio and the throwaway transcript are both cleaned up.
    assert not audio_path.exists()
    assert not audio_path.with_suffix(".wake.txt").exists()


def test_handle_audio_chunk_ignores_non_wake_speech(tmp_path):
    transcriber = FakeTranscriber(text="what time is it")
    listener, assistant, profile = build_listener(tmp_path, transcriber)

    audio_path = profile.audio_inbox_dir / "temp_wakeword.wav"
    audio_path.write_text("fake audio bytes", encoding="utf-8")

    detected = listener._handle_audio_chunk(audio_path)

    assert detected is False
    assert assistant.wake_calls == []
    assert not audio_path.exists()


def test_handle_audio_chunk_swallows_transcription_errors(tmp_path):
    listener, assistant, profile = build_listener(tmp_path, BoomTranscriber())

    audio_path = profile.audio_inbox_dir / "temp_wakeword.wav"
    audio_path.write_text("fake audio bytes", encoding="utf-8")

    # A transcriber blowing up must not crash the listen loop.
    detected = listener._handle_audio_chunk(audio_path)

    assert detected is False
    assert assistant.wake_calls == []
    # Cleanup still runs despite the exception.
    assert not audio_path.exists()
