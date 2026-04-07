"""Optional global hotkey listener for live voice activation."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from enum import Enum
from typing import Callable

from loguru import logger

try:
    from pynput import keyboard

    PYNPUT_AVAILABLE = True
except ImportError:  # pragma: no cover - depends on optional package
    keyboard = None
    PYNPUT_AVAILABLE = False


class ModifierKey(str, Enum):
    """Supported modifier keys for the wake hotkey."""

    CTRL = "ctrl"
    ALT = "alt"
    SHIFT = "shift"
    WIN = "win"


@dataclass(frozen=True)
class HotkeyConfig:
    """Configuration for a global hotkey combination."""

    modifiers: tuple[ModifierKey, ...]
    key: str = ""

    def describe(self) -> str:
        modifier_label = "+".join(modifier.value.capitalize() for modifier in self.modifiers)
        if self.key:
            return f"{modifier_label}+{self.key.upper()}"
        return modifier_label


def build_hotkey_config(modifiers: tuple[str, ...], key: str) -> HotkeyConfig:
    """Convert runtime profile strings into a validated hotkey config."""

    normalized_modifiers = tuple(ModifierKey(modifier.strip().lower()) for modifier in modifiers)
    return HotkeyConfig(modifiers=normalized_modifiers, key=key.strip().lower())


class HotkeyListener:
    """Listen for a global hotkey and trigger a callback once per press cycle."""

    def __init__(
        self,
        hotkey_config: HotkeyConfig,
        on_hotkey_pressed: Callable[[], None],
    ):
        if not PYNPUT_AVAILABLE:
            raise RuntimeError(
                "pynput is not available. Install requirements-voice-activation.txt."
            )

        self.config = hotkey_config
        self.on_hotkey_pressed = on_hotkey_pressed
        self._listener: keyboard.Listener | None = None
        self._current_keys: set[object] = set()
        self._lock = threading.Lock()
        self._running = False
        self._hotkey_active = False

    def start(self) -> None:
        """Begin listening for global hotkey events."""

        if self._running:
            return

        self._running = True
        self._current_keys.clear()
        self._hotkey_active = False
        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._listener.start()
        logger.info("Started global hotkey listener for {}", self.config.describe())

    def stop(self) -> None:
        """Stop listening for the wake hotkey."""

        self._running = False
        self._hotkey_active = False
        self._current_keys.clear()
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
        logger.info("Stopped global hotkey listener")

    def is_running(self) -> bool:
        """Return whether the listener is currently active."""

        return self._running

    def _on_press(self, key: object) -> None:
        with self._lock:
            self._current_keys.add(key)
            is_match = self._matches_hotkey()
            if is_match and not self._hotkey_active:
                self._hotkey_active = True
                logger.debug("Detected hotkey press for {}", self.config.describe())
                threading.Thread(target=self.on_hotkey_pressed, daemon=True).start()

    def _on_release(self, key: object) -> None:
        with self._lock:
            self._current_keys.discard(key)
            if self._hotkey_active and not self._matches_hotkey():
                self._hotkey_active = False

    def _matches_hotkey(self) -> bool:
        pressed_modifiers: set[ModifierKey] = set()
        pressed_regular_keys: set[str] = set()

        for key in self._current_keys:
            if keyboard is None:
                break

            if isinstance(key, keyboard.Key):
                if key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r, keyboard.Key.ctrl):
                    pressed_modifiers.add(ModifierKey.CTRL)
                elif key in (keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.alt):
                    pressed_modifiers.add(ModifierKey.ALT)
                elif key in (keyboard.Key.shift_l, keyboard.Key.shift_r, keyboard.Key.shift):
                    pressed_modifiers.add(ModifierKey.SHIFT)
                elif key in (keyboard.Key.cmd_l, keyboard.Key.cmd_r, keyboard.Key.cmd):
                    pressed_modifiers.add(ModifierKey.WIN)
            elif isinstance(key, keyboard.KeyCode) and key.char:
                pressed_regular_keys.add(key.char.lower())

        if set(self.config.modifiers) != pressed_modifiers:
            return False
        if self.config.key:
            return self.config.key in pressed_regular_keys
        return True
