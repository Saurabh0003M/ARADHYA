"""Audio inbox and transcription workflow for Aradhya."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess

from src.aradhya.runtime_profile import VoiceProfile


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

    def __init__(self, profile: VoiceProfile):
        self.profile = profile

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
        provider = self.profile.provider.lower()

        if provider == "manual_transcript":
            return self._process_manual_transcript(audio_path)

        if provider == "whisper_command":
            return self._process_whisper_command(audio_path)

        return VoiceJobResult(
            audio_path=audio_path,
            status="blocked",
            message=(
                f"Unsupported voice provider '{self.profile.provider}'. "
                "Update profile.json with a supported provider."
            ),
        )

    def _process_manual_transcript(self, audio_path: Path) -> VoiceJobResult:
        manual_transcript_path = self.profile.manual_transcripts_dir / f"{audio_path.stem}.txt"
        if not manual_transcript_path.exists():
            return VoiceJobResult(
                audio_path=audio_path,
                status="waiting",
                message=(
                    f"Waiting for a transcript file at {manual_transcript_path}. "
                    "Drop the audio in inbox and a matching .txt transcript in "
                    "manual_transcripts to continue."
                ),
            )

        transcript_text = manual_transcript_path.read_text(encoding="utf-8").strip()
        if not transcript_text:
            return VoiceJobResult(
                audio_path=audio_path,
                status="blocked",
                message=f"The manual transcript file {manual_transcript_path} is empty.",
            )

        transcript_path = self._write_transcript(audio_path.stem, transcript_text)
        archived_audio_path = self._archive_audio(audio_path)
        manual_transcript_path.unlink()

        return VoiceJobResult(
            audio_path=audio_path,
            status="processed",
            message=f"Processed {audio_path.name} using the manual transcript flow.",
            transcript_text=transcript_text,
            transcript_path=transcript_path,
            archived_audio_path=archived_audio_path,
        )

    def _process_whisper_command(self, audio_path: Path) -> VoiceJobResult:
        template = self.profile.whisper_command_template
        if not template:
            return VoiceJobResult(
                audio_path=audio_path,
                status="blocked",
                message=(
                    "Voice provider is set to whisper_command, but no "
                    "whisper_command_template is configured in profile.json."
                ),
            )

        transcript_path = self._unique_destination(
            self.profile.transcripts_dir / f"{audio_path.stem}.txt"
        )
        rendered_command = template.format(
            audio_path=str(audio_path),
            transcript_path=str(transcript_path),
        )
        completed = subprocess.run(
            rendered_command,
            shell=True,
            capture_output=True,
            text=True,
        )

        transcript_text = ""
        if transcript_path.exists():
            transcript_text = transcript_path.read_text(encoding="utf-8").strip()
        elif completed.stdout.strip():
            transcript_text = completed.stdout.strip()
            transcript_path.write_text(transcript_text + "\n", encoding="utf-8")

        if completed.returncode != 0:
            return VoiceJobResult(
                audio_path=audio_path,
                status="blocked",
                message=(
                    f"Whisper command failed for {audio_path.name}: "
                    f"{completed.stderr.strip() or completed.stdout.strip()}"
                ),
            )

        if not transcript_text:
            return VoiceJobResult(
                audio_path=audio_path,
                status="blocked",
                message=(
                    f"Whisper command finished for {audio_path.name}, but no transcript "
                    "text was produced."
                ),
            )

        archived_audio_path = self._archive_audio(audio_path)
        return VoiceJobResult(
            audio_path=audio_path,
            status="processed",
            message=f"Processed {audio_path.name} using the Whisper command flow.",
            transcript_text=transcript_text,
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
        shutil.move(str(audio_path), str(destination))
        return destination

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
