"""Runtime profile for model and voice integrations."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

DEFAULT_VOICE_EXTENSIONS = (
    ".aac",
    ".flac",
    ".m4a",
    ".mp3",
    ".ogg",
    ".opus",
    ".wav",
)
PROFILE_FILENAME = "profile.json"
PROFILE_LOCAL_FILENAME = "profile.local.json"


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
    faster_whisper_model_size: str
    faster_whisper_device: str
    faster_whisper_compute_type: str
    language: str | None
    poll_on_wake: bool


@dataclass(frozen=True)
class VoiceActivationProfile:
    """Configuration for optional live microphone activation."""

    enabled_on_startup: bool
    hotkey_modifiers: tuple[str, ...]
    hotkey_key: str
    preferred_backend: str
    sample_rate: int
    channels: int
    chunk_size: int
    silence_threshold: float
    silence_duration: float
    max_recording_duration: float


@dataclass(frozen=True)
class VoiceOutputProfile:
    """Configuration for optional spoken replies."""

    enabled: bool
    provider: str
    voice_id: str
    rate: int
    volume: float


@dataclass(frozen=True)
class RuntimeProfile:
    """Combined runtime profile for Aradhya."""

    model: ModelProfile
    voice: VoiceProfile
    voice_activation: VoiceActivationProfile
    voice_output: VoiceOutputProfile


def _project_root_from_here() -> Path:
    return Path(__file__).resolve().parents[2]


def _runtime_profile_paths(project_root: Path) -> tuple[Path, Path]:
    memory_dir = project_root / "core" / "memory"
    return memory_dir / PROFILE_FILENAME, memory_dir / PROFILE_LOCAL_FILENAME


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


def _load_profile_payload(profile_path: Path) -> dict[str, object]:
    if not profile_path.exists():
        return {}

    raw_text = profile_path.read_text(encoding="utf-8").strip()
    if not raw_text:
        return {}

    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError:
        return {}

    return payload if isinstance(payload, dict) else {}


def _deep_merge_payloads(
    base_payload: dict[str, object],
    override_payload: dict[str, object],
) -> dict[str, object]:
    merged = deepcopy(base_payload)
    for key, value in override_payload.items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged[key] = _deep_merge_payloads(existing, value)
            continue
        merged[key] = deepcopy(value)
    return merged


def build_default_runtime_profile(
    project_root: Path | None = None
) -> RuntimeProfile:
    """Build the default runtime profile for this machine."""

    root = project_root or _project_root_from_here()
    ollama_home = Path.home() / ".ollama"
    audio_root = root / "audio"

    return RuntimeProfile(
        model=ModelProfile(
            provider="ollama",
            # Change only this field to swap for another Ollama model later.
            model_name="gemma4:e4b",
            base_url="http://127.0.0.1:11434",
            request_timeout_seconds=120,
            system_prompt=(
                "You are Aradhya, an advanced, autonomous developer agent\n"
                "integrated directly into the user's local OS. Your\n"
                "primary function is to assist with software engineering\n"
                "tasks, system administration, codebase exploration, and\n"
                "workflow automation.\n"
                "\n"
                "CORE CAPABILITIES & TOOLS:\n"
                "1. Local File System: You can read, explore, and modify\n"
                "   local files.\n"
                "2. Shell Execution: You can draft and execute terminal\n"
                "   commands natively.\n"
                "3. Git Version Control: You can manage repositories,\n"
                "   check branches, stage files, and draft commits.\n"
                "\n"
                "RULES OF ENGAGEMENT:\n"
                "- CONTEXT FIRST: Never hallucinate code or file paths.\n"
                "  If you need to edit a file, always use your tools to\n"
                "  explore the directory structure and read it first.\n"
                "- FILE MODIFICATIONS: When proposing code changes, be\n"
                "  precise. Output unified diffs or surgically apply\n"
                "  changes. Do not dump the entire contents of a file\n"
                "  if you are only changing one line.\n"
                "- SANDBOX SAFETY: You operate in a secure sandbox\n"
                "  environment. When you draft a shell command or file\n"
                "  modification, you must wait for explicit user\n"
                "  approval via the UI before execution.\n"
                "- TONE: Be highly technical, concise, and direct.\n"
                "  Skip pleasantries. Prioritize functional code,\n"
                "  accurate terminal commands, and logical solutions.\n"
                "\n"
                "When asked to perform a complex task, break it down\n"
                "into a step-by-step plan before taking action."
            ),
            ollama_home=ollama_home,
            ollama_models_path=ollama_home / "models",
        ),
        voice=VoiceProfile(
            provider="manual_transcript",
            # This is the folder you can watch while testing
            # the file-based voice flow.
            audio_inbox_dir=audio_root / "inbox",
            processed_audio_dir=audio_root / "processed",
            transcripts_dir=audio_root / "transcripts",
            manual_transcripts_dir=audio_root / "manual_transcripts",
            supported_extensions=DEFAULT_VOICE_EXTENSIONS,
            whisper_command_template=None,
            # Faster-Whisper stays optional so a fresh clone can still run
            # without voice-specific dependencies installed.
            faster_whisper_model_size="base",
            faster_whisper_device="cpu",
            faster_whisper_compute_type="int8",
            language=None,
            poll_on_wake=True,
        ),
        voice_activation=VoiceActivationProfile(
            enabled_on_startup=False,
            hotkey_modifiers=("ctrl", "win"),
            hotkey_key="",
            preferred_backend="sounddevice",
            sample_rate=16000,
            channels=1,
            chunk_size=1024,
            silence_threshold=0.01,
            silence_duration=1.5,
            max_recording_duration=30.0,
        ),
        voice_output=VoiceOutputProfile(
            enabled=False,
            provider="pyttsx3",
            voice_id="",
            rate=185,
            volume=1.0,
        ),
    )


def load_runtime_profile(project_root: Path | None = None) -> RuntimeProfile:
    """Load the runtime profile from disk, merging over defaults."""

    root = project_root or _project_root_from_here()
    defaults = build_default_runtime_profile(root)
    profile_path, local_profile_path = _runtime_profile_paths(root)
    data = _deep_merge_payloads(
        _load_profile_payload(profile_path),
        _load_profile_payload(local_profile_path),
    )

    raw_model = data.get("model")
    if not isinstance(raw_model, dict):
        raw_model = {}

    raw_voice = data.get("voice")
    if not isinstance(raw_voice, dict):
        raw_voice = {}

    raw_voice_activation = data.get("voice_activation")
    if not isinstance(raw_voice_activation, dict):
        raw_voice_activation = {}

    raw_voice_output = data.get("voice_output")
    if not isinstance(raw_voice_output, dict):
        raw_voice_output = {}

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
            faster_whisper_model_size=raw_voice.get(
                "faster_whisper_model_size",
                defaults.voice.faster_whisper_model_size,
            ),
            faster_whisper_device=raw_voice.get(
                "faster_whisper_device",
                defaults.voice.faster_whisper_device,
            ),
            faster_whisper_compute_type=raw_voice.get(
                "faster_whisper_compute_type",
                defaults.voice.faster_whisper_compute_type,
            ),
            language=raw_voice.get(
                "language",
                defaults.voice.language,
            ),
            poll_on_wake=raw_voice.get(
                "poll_on_wake",
                defaults.voice.poll_on_wake,
            ),
        ),
        voice_activation=VoiceActivationProfile(
            enabled_on_startup=raw_voice_activation.get(
                "enabled_on_startup",
                defaults.voice_activation.enabled_on_startup,
            ),
            hotkey_modifiers=tuple(
                raw_voice_activation.get(
                    "hotkey_modifiers",
                    defaults.voice_activation.hotkey_modifiers,
                )
            ),
            hotkey_key=raw_voice_activation.get(
                "hotkey_key",
                defaults.voice_activation.hotkey_key,
            ),
            preferred_backend=raw_voice_activation.get(
                "preferred_backend",
                defaults.voice_activation.preferred_backend,
            ),
            sample_rate=raw_voice_activation.get(
                "sample_rate",
                defaults.voice_activation.sample_rate,
            ),
            channels=raw_voice_activation.get(
                "channels",
                defaults.voice_activation.channels,
            ),
            chunk_size=raw_voice_activation.get(
                "chunk_size",
                defaults.voice_activation.chunk_size,
            ),
            silence_threshold=raw_voice_activation.get(
                "silence_threshold",
                defaults.voice_activation.silence_threshold,
            ),
            silence_duration=raw_voice_activation.get(
                "silence_duration",
                defaults.voice_activation.silence_duration,
            ),
            max_recording_duration=raw_voice_activation.get(
                "max_recording_duration",
                defaults.voice_activation.max_recording_duration,
            ),
        ),
        voice_output=VoiceOutputProfile(
            enabled=raw_voice_output.get(
                "enabled",
                defaults.voice_output.enabled,
            ),
            provider=raw_voice_output.get(
                "provider",
                defaults.voice_output.provider,
            ),
            voice_id=raw_voice_output.get(
                "voice_id",
                defaults.voice_output.voice_id,
            ),
            rate=raw_voice_output.get(
                "rate",
                defaults.voice_output.rate,
            ),
            volume=raw_voice_output.get(
                "volume",
                defaults.voice_output.volume,
            ),
        ),
    )


def persist_model_name(
    project_root: Path | None, model_name: str
) -> Path:
    """Persist chosen Ollama model name into profile.local.json."""

    root = project_root or _project_root_from_here()
    _profile_path, local_profile_path = _runtime_profile_paths(root)
    payload = _load_profile_payload(local_profile_path)

    raw_model = payload.get("model")
    if not isinstance(raw_model, dict):
        raw_model = {}

    raw_model.setdefault("provider", "ollama")
    raw_model["model_name"] = model_name
    payload["model"] = raw_model

    local_profile_path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(payload, indent=2) + "\n"
    local_profile_path.write_text(content, encoding="utf-8")
    return local_profile_path
