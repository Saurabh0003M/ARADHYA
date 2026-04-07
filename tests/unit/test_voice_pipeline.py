from __future__ import annotations

from src.aradhya.runtime_profile import VoiceProfile
from src.aradhya.voice_pipeline import VoiceInboxManager
from src.aradhya.voice_transcriber import FileTranscription


class FakeProcessedTranscriber:
    def transcribe(self, audio_path, transcript_destination):
        del audio_path, transcript_destination
        return FileTranscription(
            status="processed",
            message="Processed via fake faster-whisper.",
            transcript_text="open the notes project",
        )


class FakeBlockedTranscriber:
    def transcribe(self, audio_path, transcript_destination):
        del audio_path, transcript_destination
        return FileTranscription(
            status="blocked",
            message="Transcriber failed cleanly.",
        )


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


def test_voice_inbox_uses_shared_pipeline_for_faster_whisper_results(tmp_path):
    profile = build_voice_profile(tmp_path)
    manager = VoiceInboxManager(
        profile,
        transcriber_factory=lambda _profile: FakeProcessedTranscriber(),
    )
    manager.ensure_directories()

    audio_path = profile.audio_inbox_dir / "meeting.mp3"
    audio_path.write_text("fake audio bytes", encoding="utf-8")
    # Existing files force the manager to exercise its collision-safe naming.
    (profile.transcripts_dir / "meeting.txt").write_text("older transcript", encoding="utf-8")
    (profile.processed_audio_dir / "meeting.mp3").write_text("older audio", encoding="utf-8")

    results = manager.process_pending_audio()

    assert len(results) == 1
    result = results[0]
    assert result.status == "processed"
    assert result.transcript_text == "open the notes project"
    assert result.transcript_path is not None
    assert result.transcript_path.name == "meeting_1.txt"
    assert result.transcript_path.read_text(encoding="utf-8").strip() == "open the notes project"
    assert result.archived_audio_path is not None
    assert result.archived_audio_path.name == "meeting_1.mp3"
    assert result.archived_audio_path.exists()
    assert not audio_path.exists()


def test_voice_inbox_surfaces_transcriber_errors_without_archiving_audio(tmp_path):
    profile = build_voice_profile(tmp_path)
    manager = VoiceInboxManager(
        profile,
        transcriber_factory=lambda _profile: FakeBlockedTranscriber(),
    )
    manager.ensure_directories()

    audio_path = profile.audio_inbox_dir / "meeting.mp3"
    audio_path.write_text("fake audio bytes", encoding="utf-8")

    results = manager.process_pending_audio()

    assert len(results) == 1
    result = results[0]
    assert result.status == "blocked"
    assert result.message == "Transcriber failed cleanly."
    assert result.archived_audio_path is None
    assert audio_path.exists()
