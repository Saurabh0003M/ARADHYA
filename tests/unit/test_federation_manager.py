from __future__ import annotations

from src.aradhya.federation import FederationManager
from src.aradhya.runtime_profile import build_default_runtime_profile


def test_federation_initialize_creates_public_identity_without_leaking_secret(tmp_path):
    profile = build_default_runtime_profile(tmp_path)
    manager = FederationManager(tmp_path, profile)

    result = manager.initialize()

    assert result["identity"]["node_id"] == result["topology"]["local_node_id"]
    assert result["identity"]["fingerprint"]
    assert "secret" not in result["identity"]
    assert manager.paths.identity_path.is_file()
    assert manager.paths.peers_path.is_file()


def test_federation_doctor_reports_foundation_checks(tmp_path):
    profile = build_default_runtime_profile(tmp_path)
    manager = FederationManager(tmp_path, profile)

    checks = manager.doctor()

    names = {check["name"] for check in checks}
    assert {"Topology", "Identity", "Peer registry", "Transport", "Secrets"} <= names
    assert all("ok" in check for check in checks)
