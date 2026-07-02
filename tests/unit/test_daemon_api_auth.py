"""Tests for the daemon HTTP API bearer-token auth (loopback is not enough)."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from types import SimpleNamespace

from src.aradhya.daemon_api import DaemonAPIServer


def _fake_assistant():
    state = SimpleNamespace(is_awake=True, pending_plan=None)
    return SimpleNamespace(state=state)


def test_status_requires_bearer_token():
    server = DaemonAPIServer(_fake_assistant(), port=0, auth_token="secret-token")
    server.start()
    try:
        port = server._server.server_address[1]
        base = f"http://127.0.0.1:{port}"

        # Missing token -> 401
        try:
            urllib.request.urlopen(f"{base}/status", timeout=5)
            raise AssertionError("expected HTTP 401 without a token")
        except urllib.error.HTTPError as exc:
            assert exc.code == 401

        # Wrong token -> 401
        bad = urllib.request.Request(
            f"{base}/status", headers={"Authorization": "Bearer nope"}
        )
        try:
            urllib.request.urlopen(bad, timeout=5)
            raise AssertionError("expected HTTP 401 with a wrong token")
        except urllib.error.HTTPError as exc:
            assert exc.code == 401

        # Correct token -> 200
        good = urllib.request.Request(
            f"{base}/status", headers={"Authorization": "Bearer secret-token"}
        )
        with urllib.request.urlopen(good, timeout=5) as resp:
            assert resp.status == 200
            body = json.loads(resp.read())
            assert body["is_awake"] is True
    finally:
        server.stop()
