"""Audio inbox and transcription workflow for Aradhya."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
from typing import Callable

from loguru import logger

from src.aradhya.runtime_profile import VoiceProfile
from src.aradhya.voice_transcriber import FileTranscriber, build_file_transcriber


@dataclass(frozen=True)
class VoiceStatus:
    """Summary of the current audio inbox state."""

    provider: str
    inbox_dir: Path
    processed_dir: Path
    transcripts_dir: Path
    manual_transcripts_dir: Path
    supported_extensions: tuple[str, ...]
    pending_audio: tuple[Path, ...]
    whisper_command_configured: bool
    faster_whisper_model_size: str
    faster_whisper_device: str
    faster_whisper_compute_type: str
    language: str | None


@dataclass(frozen=True)
class VoiceJobResult:
    """Result of processing one audio file."""

    audio_path: Path
    status: str
    message: str
    transcript_text: str = ""
    transcript_path: Path | None = None
    archived_audio_path: Path | None = None


class VoiceInboxManager:
    """Manages audio drop folders and optional transcription hooks."""

    def __init__(
        self,
        profile: VoiceProfile,
        transcriber_factory: Callable[[VoiceProfile], FileTranscriber] = build_file_transcriber,
    ):
        self.profile = profile
        self._transcriber_factory = transcriber_factory
        self._transcriber: FileTranscriber | None = None

    def ensure_directories(self) -> None:
        """Create the runtime voice directories if they do not exist."""

        for path in (
            self.profile.audio_inbox_dir,
            self.profile.processed_audio_dir,
            self.profile.transcripts_dir,
            self.profile.manual_transcripts_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def status(self) -> VoiceStatus:
        """Return a snapshot of the current voice inbox configuration."""

        self.ensure_directories()
        pending_audio = tuple(self.list_pending_audio())
        return VoiceStatus(
            provider=self.profile.provider,
            inbox_dir=self.profile.audio_inbox_dir,
            processed_dir=self.profile.processed_audio_dir,
            transcripts_dir=self.profile.transcripts_dir,
            manual_transcripts_dir=self.profile.manual_transcripts_dir,
            supported_extensions=self.profile.supported_extensions,
            pending_audio=pending_audio,
            whisper_command_configured=bool(self.profile.whisper_command_template),
            faster_whisper_model_size=self.profile.faster_whisper_model_size,
            faster_whisper_device=self.profile.faster_whisper_device,
            faster_whisper_compute_type=self.profile.faster_whisper_compute_type,
            language=self.profile.language,
        )

    def list_pending_audio(self) -> list[Path]:
        """List audio files waiting in the inbox."""

        self.ensure_directories()
        supported_extensions = {
            extension.lower() for extension in self.profile.supported_extensions
        }

        return sorted(
            [
                path
                for path in self.profile.audio_inbox_dir.iterdir()
                if path.is_file() and path.suffix.lower() in supported_extensions
            ]
        )

    def process_pending_audio(self, limit: int | None = None) -> list[VoiceJobResult]:
        """Process pending audio files using the configured voice provider."""

        pending_audio = self.list_pending_audio()
        if limit is not None:
            pending_audio = pending_audio[:limit]

        return [self.process_audio_file(audio_path) for audio_path in pending_audio]

    def process_audio_file(self, audio_path: Path) -> VoiceJobResult:
        """Process one pending audio file."""

        self.ensure_directories()
        transcript_destination = self._unique_destination(
            self.profile.transcripts_dir / f"{audio_path.stem}.txt"
        )

        # Every provider feeds through the same transcript/archive pipeline so
        # manual transcripts, shell commands, and Faster-Whisper behave alike.
        try:
            transcription = self._get_transcriber().transcribe(
                audio_path,
                transcript_destination,
            )
        except ValueError as error:
            return VoiceJobResult(
                audio_path=audio_path,
                status="blocked",
                message=str(error),
            )

        if transcription.status != "processed":
            return VoiceJobResult(
                audio_path=audio_path,
                status=transcription.status,
                message=transcription.message,
                transcript_text=transcription.transcript_text,
                transcript_path=transcription.transcript_path,
            )

        transcript_path = transcription.transcript_path or self._write_transcript(
            audio_path.stem,
            transcription.transcript_text,
        )
        archived_audio_path = self._archive_audio(audio_path)
        self._cleanup_paths(transcription.cleanup_paths)
        logger.info(
            "Processed audio file {} via provider {}",
            audio_path.name,
            self.profile.provider,
        )
        return VoiceJobResult(
            audio_path=audio_path,
            status=transcription.status,
            message=transcription.message,
            transcript_text=transcription.transcript_text,
            transcript_path=transcript_path,
            archived_audio_path=archived_audio_path,
        )

    def _write_transcript(self, stem: str, transcript_text: str) -> Path:
        destination = self._unique_destination(
            self.profile.transcripts_dir / f"{stem}.txt"
        )
        destination.write_text(transcript_text + "\n", encoding="utf-8")
        return destination

    def _archive_audio(self, audio_path: Path) -> Path:
        destination = self._unique_destination(
            self.profile.processed_audio_dir / audio_path.name
        )
        # Moving the source file keeps the inbox clean so you can immediately
        # see which recordings are still unprocessed.
        shutil.move(str(audio_path), str(destination))
        return destination

    def _cleanup_paths(self, cleanup_paths: tuple[Path, ...]) -> None:
        for cleanup_path in cleanup_paths:
            if cleanup_path.exists():
                cleanup_path.unlink()

    def _get_transcriber(self) -> FileTranscriber:
        if self._transcriber is None:
            self._transcriber = self._transcriber_factory(self.profile)
        return self._transcriber

    def _unique_destination(self, candidate: Path) -> Path:
        if not candidate.exists():
            return candidate

        counter = 1
        while True:
            alternative = candidate.with_name(
                f"{candidate.stem}_{counter}{candidate.suffix}"
            )
            if not alternative.exists():
                return alternative
            counter += 1
