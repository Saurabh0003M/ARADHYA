"""Tests for NVDA speech output and its graceful fallback."""

from __future__ import annotations

import pytest

from src.aradhya.runtime_profile import VoiceOutputProfile
from src.aradhya.voice.nvda_output import NvdaSpeechSynthesizer


def _profile(provider: str = "nvda") -> VoiceOutputProfile:
    return VoiceOutputProfile(
        enabled=True,
        provider=provider,
        voice_id="",
        rate=180,
        volume=1.0,
    )


class _RecordingFallback:
    def __init__(self) -> None:
        self.spoken: list[str] = []

    def speak(self, text: str) -> None:
        self.spoken.append(text)


class _FakeNvdaClient:
    """Stand-in for the ctypes-loaded NVDA controller client DLL."""

    def __init__(self, *, running: bool = True, speak_status: int = 0) -> None:
        self._running = running
        self._speak_status = speak_status
        self.spoke_text: list[str] = []
        self.cancels = 0

    def nvdaController_testIfRunning(self) -> int:
        return 0 if self._running else 1

    def nvdaController_cancelSpeech(self) -> int:
        self.cancels += 1
        return 0

    def nvdaController_speakText(self, text) -> int:  # noqa: ANN001 - ctypes wrapper
        self.spoke_text.append(getattr(text, "value", text))
        return self._speak_status


def test_falls_back_when_dll_missing() -> None:
    fallback = _RecordingFallback()
    synth = NvdaSpeechSynthesizer(
        _profile(),
        fallback=fallback,
        client_loader=lambda _dll: None,  # simulate DLL not found
    )
    assert synth.is_available() is False
    synth.speak("hello")
    assert fallback.spoken == ["hello"]


def test_speaks_through_nvda_when_running() -> None:
    client = _FakeNvdaClient(running=True)
    fallback = _RecordingFallback()
    synth = NvdaSpeechSynthesizer(
        _profile(),
        fallback=fallback,
        client_loader=lambda _dll: client,
    )
    assert synth.is_available() is True
    synth.speak("open the browser")
    assert client.spoke_text == ["open the browser"]
    assert client.cancels == 1
    assert fallback.spoken == []  # NVDA handled it; fallback untouched


def test_falls_back_when_nvda_not_running() -> None:
    client = _FakeNvdaClient(running=False)
    fallback = _RecordingFallback()
    synth = NvdaSpeechSynthesizer(
        _profile(),
        fallback=fallback,
        client_loader=lambda _dll: client,
    )
    synth.speak("read the page")
    assert client.spoke_text == []
    assert fallback.spoken == ["read the page"]


def test_falls_back_when_nvda_speak_errors() -> None:
    client = _FakeNvdaClient(running=True, speak_status=5)  # non-zero = failure
    fallback = _RecordingFallback()
    synth = NvdaSpeechSynthesizer(
        _profile(),
        fallback=fallback,
        client_loader=lambda _dll: client,
    )
    synth.speak("summarize this")
    assert fallback.spoken == ["summarize this"]


def test_blank_text_is_ignored() -> None:
    client = _FakeNvdaClient(running=True)
    fallback = _RecordingFallback()
    synth = NvdaSpeechSynthesizer(
        _profile(),
        fallback=fallback,
        client_loader=lambda _dll: client,
    )
    synth.speak("   ")
    assert client.spoke_text == []
    assert fallback.spoken == []
