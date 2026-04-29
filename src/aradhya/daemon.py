"""Aradhya background daemon — keeps the assistant alive after the terminal closes.

Run with ``python -m src.aradhya.daemon`` to start the daemon.
The daemon creates:

1. A system-tray icon (via ``pystray``) with Wake / Sleep / Exit actions.
2. A background ``AradhyaAssistant`` instance.
3. A ``TaskScheduler`` wired to trigger agent thinking on heartbeat.
4. A localhost HTTP API (``daemon_api.py``) for programmatic control.

Design note
-----------
OpenClaw's daemon (``src/daemon/service.ts``) registers as a macOS LaunchAgent,
Linux systemd unit, or Windows Scheduled Task.  Aradhya intentionally uses a
lighter approach — a ``pystray`` tray icon running in the main thread — because
(a) it's pure Python, (b) it provides an immediate visual indicator, and (c) it
avoids ``schtasks`` / service-registration complexity for a local assistant.

To auto-start on Windows login, add a shortcut to
``shell:startup`` → ``pythonw -m src.aradhya.daemon``.
"""

from __future__ import annotations

import signal
import sys
import threading
import time
from pathlib import Path
from typing import Any

from loguru import logger

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------------------
# Optional dependency: pystray (tray icon).  If unavailable we fall back
# to a headless daemon that only exposes the HTTP API.
# ---------------------------------------------------------------------------
try:
    import pystray  # type: ignore[import-untyped]
    from PIL import Image, ImageDraw  # type: ignore[import-untyped]

    _HAS_TRAY = True
except ImportError:
    _HAS_TRAY = False


def _build_tray_icon_image() -> Any:
    """Create a simple 64×64 teal circle icon for the system tray."""
    size = 64
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse([4, 4, size - 4, size - 4], fill=(0, 180, 180, 255))
    # Draw an "A" in the center
    try:
        draw.text((size // 2 - 8, size // 2 - 12), "A", fill="white")
    except Exception:
        pass
    return image


class AradhyaDaemon:
    """Background daemon that keeps an ``AradhyaAssistant`` alive.

    The daemon is designed to run in a Windows system tray and expose
    an HTTP API for external control.  It wires the ``TaskScheduler``
    to trigger the ``AgentLoop`` on heartbeat tasks.
    """

    def __init__(self) -> None:
        self._shutdown_event = threading.Event()
        self._assistant: Any = None
        self._api_server: Any = None
        self._scheduler: Any = None
        self._tray_icon: Any = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Boot the daemon: assistant, scheduler, API, and tray icon."""
        logger.info("Aradhya daemon starting…")

        # Lazy imports so we only pull heavy modules when actually running.
        from src.aradhya.assistant_core import AradhyaAssistant
        from src.aradhya.assistant_models import WakeSource
        from src.aradhya.daemon_api import DaemonAPIServer
        from src.aradhya.logging_utils import configure_logging
        from src.aradhya.model_provider import build_text_model_provider
        from src.aradhya.model_setup import bootstrap_runtime_profile
        from src.aradhya.runtime_profile import load_runtime_profile
        from src.aradhya.scheduler import TaskScheduler
        from src.aradhya.skills import load_skills

        configure_logging(PROJECT_ROOT)
        runtime_profile = load_runtime_profile(PROJECT_ROOT)
        runtime_profile = bootstrap_runtime_profile(runtime_profile, PROJECT_ROOT)
        model_provider = build_text_model_provider(runtime_profile.model)
        skill_registry = load_skills(PROJECT_ROOT)

        self._assistant = AradhyaAssistant.from_project_root(
            PROJECT_ROOT,
            model_provider=model_provider,
            skill_registry=skill_registry,
        )

        # Wire the scheduler so "agent_think" tasks go through the assistant.
        self._scheduler = TaskScheduler(
            on_message=self._on_scheduler_message,
            on_agent_think=self._on_agent_think,
        )
        self._scheduler.start()

        # Start the HTTP API.
        self._api_server = DaemonAPIServer(
            self._assistant,
            shutdown_callback=self.stop,
        )
        self._api_server.start()

        # Auto-wake so the daemon is ready to process transcripts immediately.
        self._assistant.handle_wake(WakeSource.FLOATING_ICON)

        logger.info("Aradhya daemon is live (API on http://127.0.0.1:19842)")

        # Run the tray icon in the main thread (blocking).
        if _HAS_TRAY:
            self._run_tray()
        else:
            logger.warning(
                "pystray/Pillow not installed — running in headless mode. "
                "Install with: pip install pystray Pillow"
            )
            self._run_headless()

    def stop(self) -> None:
        """Gracefully shut everything down."""
        logger.info("Aradhya daemon shutting down…")
        self._shutdown_event.set()

        if self._scheduler is not None:
            self._scheduler.stop()
        if self._api_server is not None:
            self._api_server.stop()
        if self._tray_icon is not None:
            try:
                self._tray_icon.stop()
            except Exception:
                pass

        logger.info("Aradhya daemon stopped")

    # ------------------------------------------------------------------
    # Scheduler callbacks
    # ------------------------------------------------------------------

    def _on_scheduler_message(self, message: str) -> None:
        """Handle a ``message`` action from the scheduler."""
        logger.info("Scheduler message: {}", message)

    def _on_agent_think(self, payload: str) -> None:
        """Handle an ``agent_think`` action — route through full planning."""
        if self._assistant is None:
            return

        from src.aradhya.assistant_models import WakeSource

        logger.info("Heartbeat agent_think triggered: {}", payload[:120])

        # Ensure the assistant is awake.
        if not self._assistant.state.is_awake:
            self._assistant.handle_wake(WakeSource.FLOATING_ICON)

        response = self._assistant.handle_transcript(payload)
        logger.info(
            "Heartbeat result: awake={} spoken={}",
            self._assistant.state.is_awake,
            response.spoken_response[:200],
        )

        # Log heartbeat to a persistent file.
        self._log_heartbeat(payload, response.spoken_response)

    def _log_heartbeat(self, prompt: str, result: str) -> None:
        log_dir = PROJECT_ROOT / "core" / "memory" / "heartbeat_log"
        log_dir.mkdir(parents=True, exist_ok=True)
        from datetime import datetime

        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        log_file = log_dir / f"heartbeat_{stamp}.txt"
        try:
            log_file.write_text(
                f"Prompt: {prompt}\n\nResult: {result}\n",
                encoding="utf-8",
            )
        except OSError as error:
            logger.warning("Failed to write heartbeat log: {}", error)

    # ------------------------------------------------------------------
    # Tray icon
    # ------------------------------------------------------------------

    def _run_tray(self) -> None:
        """Run the pystray icon in the current (main) thread."""
        from src.aradhya.assistant_models import WakeSource

        def on_wake(_icon: Any, _item: Any) -> None:
            if self._assistant is not None:
                self._assistant.handle_wake(WakeSource.FLOATING_ICON)

        def on_sleep(_icon: Any, _item: Any) -> None:
            if self._assistant is not None:
                self._assistant.go_idle()

        def on_exit(_icon: Any, _item: Any) -> None:
            self.stop()

        menu = pystray.Menu(
            pystray.MenuItem("Wake", on_wake),
            pystray.MenuItem("Sleep", on_sleep),
            pystray.MenuItem("Exit", on_exit),
        )

        self._tray_icon = pystray.Icon(
            "Aradhya",
            icon=_build_tray_icon_image(),
            title="Aradhya — Running",
            menu=menu,
        )

        logger.info("System tray icon visible")
        self._tray_icon.run()  # blocks until icon.stop()

    def _run_headless(self) -> None:
        """Block until the shutdown event is set (no tray icon)."""
        try:
            signal.signal(signal.SIGINT, lambda *_: self.stop())
            signal.signal(signal.SIGTERM, lambda *_: self.stop())
        except (OSError, ValueError):
            pass

        print("Aradhya daemon running in headless mode. Press Ctrl+C to stop.")
        while not self._shutdown_event.is_set():
            time.sleep(1)


def main() -> None:
    daemon = AradhyaDaemon()
    daemon.start()


if __name__ == "__main__":
    main()
