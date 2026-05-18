"""Federation state and diagnostics.

This first slice intentionally avoids opening network listeners. It creates
the safe local state that later LAN transport will use: topology awareness,
local identity, peer registry, and user-facing diagnostics.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.aradhya.topology import ensure_topology, topology_path
from src.aradhya.runtime_profile import RuntimeProfile


@dataclass(frozen=True)
class FederationPaths:
    state_dir: Path
    identity_path: Path
    peers_path: Path


class FederationManager:
    """Manage local federation identity and peer state."""

    def __init__(self, project_root: Path, runtime_profile: RuntimeProfile) -> None:
        self.project_root = project_root
        self.runtime_profile = runtime_profile
        state_dir = project_root / "core" / "memory" / "federation"
        self.paths = FederationPaths(
            state_dir=state_dir,
            identity_path=state_dir / "identity.json",
            peers_path=state_dir / "peers.json",
        )

    def initialize(self) -> dict[str, Any]:
        """Create topology, local identity, and peer registry if missing."""

        topology = ensure_topology(self.project_root, self.runtime_profile)
        identity = self.ensure_identity(topology)
        self._ensure_peers_file()
        return {
            "topology": topology,
            "identity": self.public_identity(identity),
            "peers": self.load_peers(),
        }

    def ensure_identity(self, topology: dict[str, Any] | None = None) -> dict[str, Any]:
        """Create or load local identity.

        The current implementation uses a local secret and public fingerprint
        so no extra crypto dependency is needed for this foundation. Replace the
        signing backend with Ed25519 before enabling cross-device trust.
        """

        if self.paths.identity_path.is_file():
            return json.loads(self.paths.identity_path.read_text(encoding="utf-8"))

        topology = topology or ensure_topology(self.project_root, self.runtime_profile)
        node_id = str(topology.get("local_node_id") or "aradhya-node")
        secret = secrets.token_urlsafe(48)
        created_at = datetime.now(timezone.utc).isoformat()
        identity = {
            "version": 1,
            "node_id": node_id,
            "created_at": created_at,
            "signing_backend": "local-shared-secret-v0",
            "secret": secret,
            "fingerprint": _fingerprint(secret),
        }
        self.paths.state_dir.mkdir(parents=True, exist_ok=True)
        self.paths.identity_path.write_text(
            json.dumps(identity, indent=2) + "\n",
            encoding="utf-8",
        )
        return identity

    def public_identity(self, identity: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return identity fields that are safe to show or share."""

        identity = identity or self.ensure_identity()
        return {
            "version": identity.get("version", 1),
            "node_id": identity.get("node_id", "unknown"),
            "created_at": identity.get("created_at", ""),
            "signing_backend": identity.get("signing_backend", ""),
            "fingerprint": identity.get("fingerprint", ""),
        }

    def load_peers(self) -> list[dict[str, Any]]:
        if not self.paths.peers_path.is_file():
            return []
        payload = json.loads(self.paths.peers_path.read_text(encoding="utf-8"))
        peers = payload.get("peers", []) if isinstance(payload, dict) else []
        return peers if isinstance(peers, list) else []

    def status(self) -> dict[str, Any]:
        topology = ensure_topology(self.project_root, self.runtime_profile)
        identity = self.ensure_identity(topology)
        peers = self.load_peers()
        return {
            "enabled": True,
            "mode": topology.get("transport", {}).get("mode", "lan-only"),
            "transport_active": False,
            "identity": self.public_identity(identity),
            "peer_count": len(peers),
            "peers": peers,
            "state_dir": str(self.paths.state_dir),
        }

    def doctor(self) -> list[dict[str, Any]]:
        topology = ensure_topology(self.project_root, self.runtime_profile)
        identity = self.ensure_identity(topology)
        self._ensure_peers_file()
        return [
            {
                "name": "Topology",
                "ok": topology_path(self.project_root).is_file(),
                "detail": str(topology_path(self.project_root)),
            },
            {
                "name": "Identity",
                "ok": bool(identity.get("fingerprint")),
                "detail": f"{identity.get('node_id')} {identity.get('fingerprint')}",
            },
            {
                "name": "Peer registry",
                "ok": self.paths.peers_path.is_file(),
                "detail": str(self.paths.peers_path),
            },
            {
                "name": "Transport",
                "ok": True,
                "detail": "LAN transport not started yet; foundation mode only.",
            },
            {
                "name": "Secrets",
                "ok": self.paths.identity_path.is_file(),
                "detail": "Identity secret is stored under ignored local memory state.",
            },
        ]

    def _ensure_peers_file(self) -> None:
        if self.paths.peers_path.is_file():
            return
        self.paths.state_dir.mkdir(parents=True, exist_ok=True)
        self.paths.peers_path.write_text(
            json.dumps({"version": 1, "peers": []}, indent=2) + "\n",
            encoding="utf-8",
        )


def _fingerprint(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()[:16]
