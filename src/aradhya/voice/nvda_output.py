"""NVDA screen-reader speech output for eyes-free operation.

For a blind/low-vision user the assistant should speak *through their screen
reader* rather than through a second, competing TTS voice. NVDA exposes a
controller client DLL (``nvdaControllerClient.dll``) that lets an external
process inject speech (and, on newer NVDA builds, SSML) directly into the
user's existing NVDA voice — so the agent's replies sound like part of the same
audio stream the user already navigates by.

This module is deliberately defensive: every NVDA call is wrapped so a missing
DLL, a stopped NVDA process, or a signature mismatch never crashes the agent —
it simply falls back to a provided synthesizer (typically ``pyttsx3``/SAPI).

DLL resolution order:
1. explicit ``dll_path`` argument,
2. the ``NVDA_CONTROLLER_CLIENT_DLL`` environment variable,
3. an architecture-matched name next to this module,
4. the name on the system search path.

The client DLL is distributed by NV Access (``controllerClient`` in the NVDA
source tree); it is intentionally *not* vendored here.
"""

from __future__ import annotations

import ctypes
import os
import struct
from pathlib import Path
from typing import Any, Callable

from loguru import logger

from src.aradhya.runtime_profile import VoiceOutputProfile
from src.aradhya.voice.synthesizer import SpeechSynthesizer

_ENV_DLL = "NVDA_CONTROLLER_CLIENT_DLL"


def _candidate_dll_names() -> list[str]:
    """Return likely DLL filenames, architecture-matched first."""
    is_64 = struct.calcsize("P") == 8
    primary = "nvdaControllerClient64.dll" if is_64 else "nvdaControllerClient32.dll"
    return [primary, "nvdaControllerClient.dll"]


def _load_nvda_client(dll_path: str | None) -> Any | None:
    """Load the NVDA controller client DLL, or return ``None`` if unavailable."""
    if os.name != "nt":
        return None

    search: list[str] = []
    if dll_path:
        search.append(dll_path)
    env_path = os.environ.get(_ENV_DLL)
    if env_path:
        search.append(env_path)
    here = Path(__file__).resolve().parent
    for name in _candidate_dll_names():
        search.append(str(here / name))
        search.append(name)  # let Windows resolve via PATH

    for candidate in search:
        try:
            client = ctypes.windll.LoadLibrary(candidate)  # type: ignore[attr-defined]
            logger.debug("Loaded NVDA controller client from {}", candidate)
            return client
        except OSError:
            continue
    logger.debug("NVDA controller client DLL not found (searched {} paths)", len(search))
    return None


class NvdaSpeechSynthesizer:
    """Speak assistant replies through a running NVDA instance.

    Conforms to the :class:`~src.aradhya.voice.synthesizer.SpeechSynthesizer`
    protocol. When NVDA is not present/running, delegates to ``fallback``.
    """

    def __init__(
        self,
        profile: VoiceOutputProfile,
        *,
        fallback: SpeechSynthesizer | None = None,
        dll_path: str | None = None,
        client_loader: Callable[[str | None], Any | None] | None = None,
    ) -> None:
        self.profile = profile
        self.fallback = fallback
        loader = client_loader or _load_nvda_client
        self._client = loader(dll_path)

    # ------------------------------------------------------------------
    def is_available(self) -> bool:
        """True when the DLL is loaded and NVDA is currently running."""
        if self._client is None:
            return False
        try:
            # nvdaController_testIfRunning() returns 0 (RPC_S_OK) when NVDA is up.
            return int(self._client.nvdaController_testIfRunning()) == 0
        except Exception as error:  # noqa: BLE001 - never let a probe crash the agent
            logger.debug("NVDA testIfRunning failed: {}", error)
            return False

    def speak(self, text: str) -> None:
        cleaned = text.strip()
        if not cleaned:
            return

        if self._speak_via_nvda(cleaned):
            return

        if self.fallback is not None:
            self.fallback.speak(cleaned)
        else:
            logger.debug("NVDA unavailable and no fallback synthesizer configured; reply not spoken")

    # ------------------------------------------------------------------
    def _speak_via_nvda(self, text: str) -> bool:
        """Attempt to speak through NVDA. Returns True on success."""
        if not self.is_available():
            return False
        try:
            self._client.nvdaController_cancelSpeech()
            # Prefer SSML (NVDA 2024.1+) so we can later modulate pitch/rate to
            # distinguish the agent's voice from the screen reader; fall back to
            # plain text on older builds that lack the export.
            use_ssml = getattr(self.profile, "use_ssml", True)
            if use_ssml and hasattr(self._client, "nvdaController_speakSsml"):
                ssml = self._wrap_ssml(text)
                status = self._client.nvdaController_speakSsml(
                    ctypes.c_wchar_p(ssml), 0, 0, True
                )
            else:
                status = self._client.nvdaController_speakText(ctypes.c_wchar_p(text))
            if int(status) != 0:
                logger.debug("NVDA speak returned non-zero status {}", status)
                return False
            return True
        except Exception as error:  # noqa: BLE001 - degrade to fallback, never crash
            logger.debug("NVDA speak failed, using fallback: {}", error)
            return False

    def _wrap_ssml(self, text: str) -> str:
        rate = getattr(self.profile, "ssml_rate", None)
        pitch = getattr(self.profile, "ssml_pitch", None)
        prosody_attrs = ""
        if rate:
            prosody_attrs += f' rate="{rate}"'
        if pitch:
            prosody_attrs += f' pitch="{pitch}"'
        escaped = (
            text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )
        if prosody_attrs:
            return f"<speak><prosody{prosody_attrs}>{escaped}</prosody></speak>"
        return f"<speak>{escaped}</speak>"
