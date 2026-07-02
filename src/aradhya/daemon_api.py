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

import hmac
import json
import os
import secrets
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Callable

from loguru import logger

from src.aradhya.confirmation_gates import HeadlessConfirmationGate
from src.aradhya.paths import aradhya_path

DEFAULT_PORT = 19842
DEFAULT_HOST = "127.0.0.1"


def get_or_create_daemon_token() -> str:
    """Return the daemon API bearer token, creating and persisting one if absent.

    The token lives in ``~/.aradhya/daemon_token`` (best-effort 0600 perms).
    Local clients must send it as ``Authorization: Bearer <token>`` — binding to
    loopback is not sufficient on its own, since any local process (or a browser
    via a crafted request) can reach a loopback port.
    """
    token_path = aradhya_path("daemon_token")
    try:
        if token_path.is_file():
            existing = token_path.read_text(encoding="utf-8").strip()
            if existing:
                return existing
    except OSError:
        pass

    token = secrets.token_urlsafe(32)
    try:
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(token, encoding="utf-8")
        try:
            os.chmod(token_path, 0o600)
        except OSError:
            pass
    except OSError as exc:
        logger.warning("Could not persist daemon API token: {}", exc)
    return token


class _DaemonRequestHandler(BaseHTTPRequestHandler):
    """HTTP handler wired to an ``AradhyaAssistant`` instance at server level."""

    # Silence the default stderr logging — we use loguru instead.
    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: ARG002
        logger.debug("daemon-api: {} {}", self.command, self.path)

    # ------------------------------------------------------------------
    # GET routes
    # ------------------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        if not self._is_authorized():
            self._unauthorized()
            return
        if self.path == "/status":
            self._handle_status()
        else:
            self._not_found()

    # ------------------------------------------------------------------
    # POST routes
    # ------------------------------------------------------------------

    def do_POST(self) -> None:  # noqa: N802
        if not self._is_authorized():
            self._unauthorized()
            return
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
        # Headless channel: deny dangerous tools rather than prompting a TTY
        # that does not exist in the daemon process.
        response = assistant.handle_transcript(
            text, confirmation_gate=HeadlessConfirmationGate()
        )
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

    def _is_authorized(self) -> bool:
        """Return True only if the request carries the correct bearer token."""
        token = getattr(self.server, "auth_token", None)  # type: ignore[attr-defined]
        if not token:
            # Fail closed: a server with no configured token denies all requests
            # rather than silently allowing them.
            return False
        provided = self.headers.get("Authorization", "")
        return hmac.compare_digest(provided, f"Bearer {token}")

    def _unauthorized(self) -> None:
        self._json_response(
            401, {"error": "Unauthorized: missing or invalid bearer token."}
        )

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
        auth_token: str | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.auth_token = auth_token or get_or_create_daemon_token()
        self._server = HTTPServer((host, port), _DaemonRequestHandler)
        self._server.assistant = assistant  # type: ignore[attr-defined]
        self._server.shutdown_callback = shutdown_callback  # type: ignore[attr-defined]
        self._server.auth_token = self.auth_token  # type: ignore[attr-defined]
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
        logger.info(
            "Daemon API requires a bearer token; clients read it from {}",
            aradhya_path("daemon_token"),
        )

    def stop(self) -> None:
        """Shut down the HTTP server."""
        self._server.shutdown()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        logger.info("Daemon API stopped")
