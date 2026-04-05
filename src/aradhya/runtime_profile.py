"""Runtime profile for model and voice integrations."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_VOICE_EXTENSIONS = (
    ".aac",
    ".flac",
    ".m4a",
    ".mp3",
    ".ogg",
    ".wav",
)


@dataclass(frozen=True)
class ModelProfile:
    """Configuration for the local reasoning model."""

    provider: str
    model_name: str
    base_url: str
    request_timeout_seconds: int
    system_prompt: str
    ollama_home: Path
    ollama_models_path: Path


@dataclass(frozen=True)
class VoiceProfile:
    """Configuration for audio ingestion and transcription."""

    provider: str
    audio_inbox_dir: Path
    processed_audio_dir: Path
    transcripts_dir: Path
    manual_transcripts_dir: Path
    supported_extensions: tuple[str, ...]
    whisper_command_template: str | None
    poll_on_wake: bool


@dataclass(frozen=True)
class RuntimeProfile:
    """Combined runtime profile for Aradhya."""

    model: ModelProfile
    voice: VoiceProfile


def _project_root_from_here() -> Path:
    return Path(__file__).resolve().parents[2]


def _resolve_path(
    value: str | None,
    project_root: Path,
    fallback: Path,
) -> Path:
    if not value:
        return fallback

    path = Path(value)
    if not path.is_absolute():
        path = project_root / path
    return path


def build_default_runtime_profile(project_root: Path | None = None) -> RuntimeProfile:
    """Build the default runtime profile for this machine."""

    root = project_root or _project_root_from_here()
    ollama_home = Path.home() / ".ollama"
    audio_root = root / "audio"

    return RuntimeProfile(
        model=ModelProfile(
            provider="ollama",
            model_name="gemma4:e4b",
            base_url="http://127.0.0.1:11434",
            request_timeout_seconds=120,
            system_prompt=(
                "You are Aradhya, a local system assistant focused on safe planning, "
                "clear reasoning, and practical Windows workflow help."
            ),
            ollama_home=ollama_home,
            ollama_models_path=ollama_home / "models",
        ),
        voice=VoiceProfile(
            provider="manual_transcript",
            audio_inbox_dir=audio_root / "inbox",
            processed_audio_dir=audio_root / "processed",
            transcripts_dir=audio_root / "transcripts",
            manual_transcripts_dir=audio_root / "manual_transcripts",
            supported_extensions=DEFAULT_VOICE_EXTENSIONS,
            whisper_command_template=None,
            poll_on_wake=True,
        ),
    )


def load_runtime_profile(project_root: Path | None = None) -> RuntimeProfile:
    """Load the runtime profile from disk, merging over defaults."""

    root = project_root or _project_root_from_here()
    defaults = build_default_runtime_profile(root)
    profile_path = root / "core" / "memory" / "profile.json"

    if not profile_path.exists():
        return defaults

    raw_text = profile_path.read_text(encoding="utf-8").strip()
    if not raw_text:
        return defaults

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        return defaults

    raw_model = data.get("model", {})
    raw_voice = data.get("voice", {})

    return RuntimeProfile(
        model=ModelProfile(
            provider=raw_model.get("provider", defaults.model.provider),
            model_name=raw_model.get("model_name", defaults.model.model_name),
            base_url=raw_model.get("base_url", defaults.model.base_url),
            request_timeout_seconds=raw_model.get(
                "request_timeout_seconds",
                defaults.model.request_timeout_seconds,
            ),
            system_prompt=raw_model.get(
                "system_prompt",
                defaults.model.system_prompt,
            ),
            ollama_home=_resolve_path(
                raw_model.get("ollama_home"),
                root,
                defaults.model.ollama_home,
            ),
            ollama_models_path=_resolve_path(
                raw_model.get("ollama_models_path"),
                root,
                defaults.model.ollama_models_path,
            ),
        ),
        voice=VoiceProfile(
            provider=raw_voice.get("provider", defaults.voice.provider),
            audio_inbox_dir=_resolve_path(
                raw_voice.get("audio_inbox_dir"),
                root,
                defaults.voice.audio_inbox_dir,
            ),
            processed_audio_dir=_resolve_path(
                raw_voice.get("processed_audio_dir"),
                root,
                defaults.voice.processed_audio_dir,
            ),
            transcripts_dir=_resolve_path(
                raw_voice.get("transcripts_dir"),
                root,
                defaults.voice.transcripts_dir,
            ),
            manual_transcripts_dir=_resolve_path(
                raw_voice.get("manual_transcripts_dir"),
                root,
                defaults.voice.manual_transcripts_dir,
            ),
            supported_extensions=tuple(
                raw_voice.get(
                    "supported_extensions",
                    defaults.voice.supported_extensions,
                )
            ),
            whisper_command_template=raw_voice.get(
                "whisper_command_template",
                defaults.voice.whisper_command_template,
            ),
            poll_on_wake=raw_voice.get(
                "poll_on_wake",
                defaults.voice.poll_on_wake,
            ),
        ),
    )
