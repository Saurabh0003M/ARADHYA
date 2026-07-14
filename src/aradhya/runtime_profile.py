"""Runtime profile for model and voice integrations."""

from __future__ import annotations

import json
import os
from copy import deepcopy
from dataclasses import dataclass, fields, replace
from pathlib import Path
from typing import Any, TypeVar

from src.aradhya.paths import get_project_root

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
    api_key: str = ""
    api_key_env: str = ""
    api_key_fallback_envs: tuple[str, ...] = ()
    account_id: str = ""
    account_id_env: str = ""
    # Optional multimodal model used for screenshot/image description. When
    # empty, vision falls back to model_name (fine if that model is multimodal,
    # otherwise describe_image reports that no vision model is configured).
    vision_model: str = ""


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
    return get_project_root()


def _runtime_profile_paths(project_root: Path) -> tuple[Path, Path]:
    config_dir = project_root / "core" / "config"
    # Fallback to legacy path for existing installs
    if not config_dir.exists():
        config_dir = project_root / "core" / "memory"
    return config_dir / PROFILE_FILENAME, config_dir / PROFILE_LOCAL_FILENAME


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


T = TypeVar("T")


def _apply_overrides(default_obj: T, raw_data: dict[str, Any], **overrides: Any) -> T:
    """Merge a raw dictionary and explicit overrides into a dataclass instance."""
    updates = {}
    for f in fields(default_obj):  # type: ignore
        if f.name in raw_data:
            updates[f.name] = raw_data[f.name]
    updates.update(overrides)
    return replace(default_obj, **updates)  # type: ignore


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


def _default_api_key_env(provider: str) -> str:
    if provider.lower() == "openrouter":
        return "ARADHYA_OPENROUTER_API_KEY"
    if provider.lower() == "cloudflare":
        return "CLOUDFLARE_API_TOKEN"
    return ""


def _default_api_key_fallback_envs(provider: str) -> tuple[str, ...]:
    if provider.lower() == "cloudflare":
        return ("CLOUDFLARE_AUTH_TOKEN",)
    return ()


def _default_account_id_env(provider: str) -> str:
    if provider.lower() == "cloudflare":
        return "CLOUDFLARE_ACCOUNT_ID"
    return ""


def _default_model_name(provider: str, fallback: str) -> str:
    normalized = provider.lower()
    if normalized == "openrouter":
        return "google/gemma-4-31b-it:free"
    if normalized == "cloudflare":
        return "@cf/zai-org/glm-5.2"
    return fallback


def _default_base_url(provider: str, fallback: str) -> str:
    normalized = provider.lower()
    if normalized == "openrouter":
        return "https://openrouter.ai/api/v1"
    if normalized == "cloudflare":
        return "https://api.cloudflare.com/client/v4"
    return fallback


def _env_value(primary: str, fallback_envs: tuple[str, ...]) -> str:
    candidates = (primary,) + fallback_envs if primary else fallback_envs
    for env_name in candidates:
        value = os.environ.get(env_name, "")
        if value:
            return value
    return ""


def _string_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,) if value else ()
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value if str(item))
    return ()


def build_default_runtime_profile(project_root: Path | None = None) -> RuntimeProfile:
    """Build the default runtime profile for this machine."""

    root = project_root or _project_root_from_here()
    ollama_home = Path.home() / ".ollama"
    audio_root = root / "audio"

    return RuntimeProfile(
        model=ModelProfile(
            provider="ollama",
            # Change only this field to swap Gemma for another Ollama model later.
            model_name="gemma4:e4b",
            base_url="http://127.0.0.1:11434",
            request_timeout_seconds=300,
            system_prompt=(
                "You are Aradhya, a local system assistant focused on safe planning, "
                "clear reasoning, and practical Windows workflow help."
            ),
            ollama_home=ollama_home,
            ollama_models_path=ollama_home / "models",
        ),
        voice=VoiceProfile(
            provider="manual_transcript",
            # This is the folder you can watch while testing the file-based voice flow.
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


def _load_model_profile(
    raw_model: dict[str, object],
    defaults: RuntimeProfile,
    root: Path,
) -> ModelProfile:
    model_provider = str(raw_model.get("provider", defaults.model.provider))
    api_key_env = str(raw_model.get("api_key_env", "") or _default_api_key_env(model_provider))
    raw_fallback_envs = raw_model.get(
        "api_key_fallback_envs",
        _default_api_key_fallback_envs(model_provider),
    )
    api_key_fallback_envs = _string_tuple(raw_fallback_envs)
    env_api_key = _env_value(api_key_env, api_key_fallback_envs)
    file_api_key = str(raw_model.get("api_key", defaults.model.api_key) or "")
    api_key = env_api_key or file_api_key
    account_id_env = str(
        raw_model.get("account_id_env", "")
        or _default_account_id_env(model_provider)
    )
    env_account_id = os.environ.get(account_id_env, "") if account_id_env else ""
    file_account_id = str(raw_model.get("account_id", defaults.model.account_id) or "")
    account_id = env_account_id or file_account_id

    return ModelProfile(
        provider=model_provider,
        model_name=str(
            raw_model.get("model_name")
            or _default_model_name(model_provider, defaults.model.model_name)
        ),
        base_url=str(
            raw_model.get("base_url")
            or _default_base_url(model_provider, defaults.model.base_url)
        ),
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
        api_key=api_key,
        api_key_env=api_key_env,
        api_key_fallback_envs=api_key_fallback_envs,
        account_id=account_id,
        account_id_env=account_id_env,
        vision_model=str(raw_model.get("vision_model", defaults.model.vision_model) or ""),
    )


def _load_voice_profile(
    raw_voice: dict[str, object],
    defaults: RuntimeProfile,
    root: Path,
) -> VoiceProfile:
    return VoiceProfile(
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
    )


def _load_voice_activation_profile(
    raw_voice_activation: dict[str, object],
    defaults: RuntimeProfile,
) -> VoiceActivationProfile:
    return VoiceActivationProfile(
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
    )


def _load_voice_output_profile(
    raw_voice_output: dict[str, object],
    defaults: RuntimeProfile,
) -> VoiceOutputProfile:
    return VoiceOutputProfile(
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

    raw_model = data.get("model", {})
    raw_voice = data.get("voice", {})
    raw_voice_activation = data.get("voice_activation", {})
    raw_voice_output = data.get("voice_output", {})

    return RuntimeProfile(
        model=_load_model_profile(raw_model, defaults, root),
        voice=_load_voice_profile(raw_voice, defaults, root),
        voice_activation=_load_voice_activation_profile(raw_voice_activation, defaults),
        voice_output=_load_voice_output_profile(raw_voice_output, defaults),
    )


def persist_model_name(project_root: Path | None, model_name: str) -> Path:
    """Persist the chosen Ollama model name into ``core/config/profile.local.json``."""

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
    local_profile_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return local_profile_path
