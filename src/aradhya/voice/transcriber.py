"""File-based transcription providers for Aradhya's voice inbox."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
from typing import Any, Callable, Protocol

from loguru import logger

from src.aradhya.runtime_profile import VoiceProfile


@dataclass(frozen=True)
class FileTranscription:
    """Result returned by a file-transcription provider."""

    status: str
    message: str
    transcript_text: str = ""
    transcript_path: Path | None = None
    cleanup_paths: tuple[Path, ...] = ()


class FileTranscriber(Protocol):
    """Shared protocol for swappable file transcription providers."""

    def transcribe(
        self,
        audio_path: Path,
        transcript_destination: Path,
    ) -> FileTranscription:
        """Return transcript text or a provider-specific error message."""


class ManualTranscriptFileTranscriber:
    """Reads a matching ``.txt`` helper file from ``audio/manual_transcripts``."""

    def __init__(self, profile: VoiceProfile):
        self.profile = profile

    def transcribe(
        self,
        audio_path: Path,
        transcript_destination: Path,
    ) -> FileTranscription:
        del transcript_destination
        manual_transcript_path = self.profile.manual_transcripts_dir / f"{audio_path.stem}.txt"
        if not manual_transcript_path.exists():
            return FileTranscription(
                status="waiting",
                message=(
                    f"Waiting for a transcript file at {manual_transcript_path}. "
                    "Drop the audio in inbox and a matching .txt transcript in "
                    "manual_transcripts to continue."
                ),
            )

        transcript_text = manual_transcript_path.read_text(encoding="utf-8").strip()
        if not transcript_text:
            return FileTranscription(
                status="blocked",
                message=f"The manual transcript file {manual_transcript_path} is empty.",
            )

        return FileTranscription(
            status="processed",
            message=f"Processed {audio_path.name} using the manual transcript flow.",
            transcript_text=transcript_text,
            cleanup_paths=(manual_transcript_path,),
        )


class WhisperCommandFileTranscriber:
    """Runs an external command template against the pending audio file."""

    def __init__(self, profile: VoiceProfile):
        self.profile = profile

    def transcribe(
        self,
        audio_path: Path,
        transcript_destination: Path,
    ) -> FileTranscription:
        template = self.profile.whisper_command_template
        if not template:
            return FileTranscription(
                status="blocked",
                message=(
                    "Voice provider is set to whisper_command, but no "
                    "whisper_command_template is configured in profile.json."
                ),
            )

        rendered_command = template.format(
            audio_path=str(audio_path),
            transcript_path=str(transcript_destination),
        )
        logger.info("Running whisper_command provider for {}", audio_path.name)
        completed = subprocess.run(
            rendered_command,
            shell=True,
            capture_output=True,
            text=True,
        )

        transcript_text = ""
        if transcript_destination.exists():
            transcript_text = transcript_destination.read_text(encoding="utf-8").strip()
        elif completed.stdout.strip():
            transcript_text = completed.stdout.strip()

        if completed.returncode != 0:
            return FileTranscription(
                status="blocked",
                message=(
                    f"Whisper command failed for {audio_path.name}: "
                    f"{completed.stderr.strip() or completed.stdout.strip()}"
                ),
            )

        if not transcript_text:
            return FileTranscription(
                status="blocked",
                message=(
                    f"Whisper command finished for {audio_path.name}, but no transcript "
                    "text was produced."
                ),
            )

        return FileTranscription(
            status="processed",
            message=f"Processed {audio_path.name} using the Whisper command flow.",
            transcript_text=transcript_text,
            transcript_path=transcript_destination if transcript_destination.exists() else None,
        )


class FasterWhisperFileTranscriber:
    """Uses ``faster-whisper`` to transcribe audio files locally."""

    def __init__(
        self,
        profile: VoiceProfile,
        model_factory: Callable[..., Any] | None = None,
    ):
        self.profile = profile
        self._model_factory = model_factory
        self._model: Any | None = None

    def transcribe(
        self,
        audio_path: Path,
        transcript_destination: Path,
    ) -> FileTranscription:
        del transcript_destination

        try:
            model = self._load_model()
        except Exception as error:
            return FileTranscription(
                status="blocked",
                message=(
                    "Faster-Whisper is not available. Install requirements-voice.txt "
                    f"and verify the voice profile settings. Details: {error}"
                ),
            )

        try:
            logger.info(
                "Running faster_whisper provider for {} with model {}",
                audio_path.name,
                self.profile.faster_whisper_model_size,
            )
            segments, _info = model.transcribe(
                str(audio_path),
                language=self.profile.language,
            )
        except Exception as error:
            return FileTranscription(
                status="blocked",
                message=f"Faster-Whisper failed for {audio_path.name}: {error}",
            )

        transcript_text = " ".join(
            segment.text.strip() for segment in segments if segment.text.strip()
        ).strip()
        if not transcript_text:
            return FileTranscription(
                status="blocked",
                message=(
                    f"Faster-Whisper processed {audio_path.name}, but no transcript text "
                    "was produced."
                ),
            )

        return FileTranscription(
            status="processed",
            message=f"Processed {audio_path.name} using the Faster-Whisper flow.",
            transcript_text=transcript_text,
        )

    def _load_model(self) -> Any:
        if self._model is not None:
            return self._model

        model_factory = self._model_factory
        if model_factory is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as error:  # pragma: no cover - depends on optional package
                raise RuntimeError("Optional dependency 'faster-whisper' is not installed.") from error

            model_factory = WhisperModel

        # The voice profile owns these knobs so model swaps stay declarative and
        # inspectable in profile.json instead of becoming code changes.
        self._model = model_factory(
            self.profile.faster_whisper_model_size,
            device=self.profile.faster_whisper_device,
            compute_type=self.profile.faster_whisper_compute_type,
        )
        return self._model


def build_file_transcriber(profile: VoiceProfile) -> FileTranscriber:
    """Construct the configured transcription provider."""

    provider = profile.provider.lower()
    if provider == "manual_transcript":
        return ManualTranscriptFileTranscriber(profile)
    if provider == "whisper_command":
        return WhisperCommandFileTranscriber(profile)
    if provider == "faster_whisper":
        return FasterWhisperFileTranscriber(profile)

    raise ValueError(
        f"Unsupported voice provider '{profile.provider}'. "
        "Update profile.json with a supported provider."
    )
