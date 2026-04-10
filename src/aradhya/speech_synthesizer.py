"""Optional speech-output providers for Aradhya's live voice runtime."""

from __future__ import annotations

import threading
from typing import Any, Callable, Protocol

from loguru import logger

from src.aradhya.runtime_profile import VoiceOutputProfile


class SpeechSynthesizer(Protocol):
    """Minimal interface for optional spoken assistant replies."""

    def speak(self, text: str) -> None:
        """Speak the given text aloud."""


class Pyttsx3SpeechSynthesizer:
    """Windows-friendly speech output built on ``pyttsx3`` and SAPI."""

    def __init__(
        self,
        profile: VoiceOutputProfile,
        engine_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.profile = profile
        self._engine_factory = engine_factory
        self._engine: Any | None = None
        self._lock = threading.Lock()

    def speak(self, text: str) -> None:
        cleaned_text = text.strip()
        if not cleaned_text:
            return

        with self._lock:
            engine = self._get_engine()
            logger.debug("Speaking assistant reply with provider {}", self.profile.provider)
            engine.say(cleaned_text)
            engine.runAndWait()

    def _get_engine(self) -> Any:
        if self._engine is not None:
            return self._engine

        if self._engine_factory is not None:
            engine = self._engine_factory()
        else:
            try:
                import pyttsx3
            except ImportError as error:  # pragma: no cover - optional dependency
                raise RuntimeError(
                    "Optional dependency 'pyttsx3' is not installed. "
                    "Install requirements-voice-activation.txt to enable spoken replies."
                ) from error

            engine = pyttsx3.init()

        if self.profile.voice_id:
            engine.setProperty("voice", self.profile.voice_id)
        engine.setProperty("rate", self.profile.rate)
        engine.setProperty("volume", self.profile.volume)
        self._engine = engine
        return engine


def build_speech_synthesizer(
    profile: VoiceOutputProfile,
    *,
    engine_factory: Callable[[], Any] | None = None,
) -> SpeechSynthesizer | None:
    """Construct the configured speech-output provider."""

    if not profile.enabled:
        return None

    provider = profile.provider.lower()
    if provider == "pyttsx3":
        return Pyttsx3SpeechSynthesizer(
            profile,
            engine_factory=engine_factory,
        )

    raise ValueError(
        f"Unsupported voice output provider '{profile.provider}'. "
        "Add a provider implementation instead of hard-coding a new backend."
    )
