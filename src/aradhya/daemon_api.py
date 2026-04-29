"""Minimal HTTP API for the Aradhya background daemon.

The server binds to ``localhost`` only and accepts JSON-encoded commands so
external tools (CLI, floating icon, scripts) can drive the assistant without
a terminal session.

Endpoints
---------
POST /wake          Wake the assistant.
POST /sleep         Send the assistant idle.
POST /transcript    Body: {"text": "..."}  — route text through planning.
GET  /status        Return current assistant state as JSON.
POST /shutdown      Gracefully shut down the daemon.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Callable

from loguru import logger

DEFAULT_PORT = 19842
DEFAULT_HOST = "127.0.0.1"


class _DaemonRequestHandler(BaseHTTPRequestHandler):
    """HTTP handler wired to an ``AradhyaAssistant`` instance at server level."""

    # Silence the default stderr logging — we use loguru instead.
    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: ARG002
        logger.debug("daemon-api: {} {}", self.command, self.path)

    # ------------------------------------------------------------------
    # GET routes
    # ------------------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/status":
            self._handle_status()
        else:
            self._not_found()

    # ------------------------------------------------------------------
    # POST routes
    # ------------------------------------------------------------------

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/wake":
            self._handle_wake()
        elif self.path == "/sleep":
            self._handle_sleep()
        elif self.path == "/transcript":
            self._handle_transcript()
        elif self.path == "/shutdown":
            self._handle_shutdown()
        else:
            self._not_found()

    # ------------------------------------------------------------------
    # Route implementations
    # ------------------------------------------------------------------

    def _handle_wake(self) -> None:
        from src.aradhya.assistant_models import WakeSource

        assistant = self.server.assistant  # type: ignore[attr-defined]
        response = assistant.handle_wake(WakeSource.FLOATING_ICON)
        self._json_response(200, {"spoken_response": response.spoken_response})

    def _handle_sleep(self) -> None:
        assistant = self.server.assistant  # type: ignore[attr-defined]
        response = assistant.go_idle()
        self._json_response(200, {"spoken_response": response.spoken_response})

    def _handle_transcript(self) -> None:
        body = self._read_json_body()
        if body is None:
            return
        text = body.get("text", "").strip()
        if not text:
            self._json_response(400, {"error": "Missing 'text' field."})
            return

        assistant = self.server.assistant  # type: ignore[attr-defined]
        response = assistant.handle_transcript(text)
        result_payload: dict[str, Any] = {
            "spoken_response": response.spoken_response,
            "awaiting_confirmation": response.awaiting_confirmation,
        }
        if response.plan is not None:
            result_payload["plan_kind"] = response.plan.kind.value
        if response.result is not None:
            result_payload["success"] = response.result.success
        self._json_response(200, result_payload)

    def _handle_status(self) -> None:
        assistant = self.server.assistant  # type: ignore[attr-defined]
        self._json_response(200, {
            "is_awake": assistant.state.is_awake,
            "has_pending_plan": assistant.state.pending_plan is not None,
        })

    def _handle_shutdown(self) -> None:
        self._json_response(200, {"message": "Daemon shutting down."})
        shutdown_callback = getattr(self.server, "shutdown_callback", None)
        if callable(shutdown_callback):
            # Fire the shutdown in a separate thread so the response is sent first.
            threading.Thread(
                target=shutdown_callback, daemon=True, name="daemon-shutdown"
            ).start()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _read_json_body(self) -> dict[str, Any] | None:
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            self._json_response(400, {"error": "Empty request body."})
            return None
        try:
            raw = self.rfile.read(content_length)
            return json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            self._json_response(400, {"error": f"Invalid JSON: {error}"})
            return None

    def _json_response(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _not_found(self) -> None:
        self._json_response(404, {"error": f"Unknown route: {self.path}"})


class DaemonAPIServer:
    """Wraps an ``HTTPServer`` that exposes the daemon API.

    Parameters
    ----------
    assistant
        A fully initialised ``AradhyaAssistant`` instance.
    host
        The hostname to bind to.  Defaults to ``127.0.0.1`` (loopback only).
    port
        The TCP port to listen on.  Defaults to ``19842``.
    shutdown_callback
        Optional callback invoked when ``POST /shutdown`` is received.
    """

    def __init__(
        self,
        assistant: Any,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        shutdown_callback: Callable[[], None] | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self._server = HTTPServer((host, port), _DaemonRequestHandler)
        self._server.assistant = assistant  # type: ignore[attr-defined]
        self._server.shutdown_callback = shutdown_callback  # type: ignore[attr-defined]
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start serving in a background daemon thread."""
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
            name="aradhya-daemon-api",
        )
        self._thread.start()
        logger.info("Daemon API listening on http://{}:{}", self.host, self.port)

    def stop(self) -> None:
        """Shut down the HTTP server."""
        self._server.shutdown()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        logger.info("Daemon API stopped")
