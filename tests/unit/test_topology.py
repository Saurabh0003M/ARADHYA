from __future__ import annotations

from src.aradhya.runtime_profile import build_default_runtime_profile
from src.aradhya.topology import ensure_topology, load_topology, topology_summary_lines


def test_ensure_topology_generates_capability_driven_local_node(tmp_path):
    profile = build_default_runtime_profile(tmp_path)

    topology = ensure_topology(tmp_path, profile)

    assert topology["version"] == 1
    assert topology["transport"]["mode"] == "lan-only"
    assert topology["local_node_id"]
    assert topology["nodes"][0]["role"] == "primary"
    capability_names = {cap["name"] for cap in topology["nodes"][0]["capabilities"]}
    assert "aradhya_core" in capability_names
    assert "filesystem_index" in capability_names
    assert load_topology(tmp_path)["local_node_id"] == topology["local_node_id"]


def test_topology_summary_lines_are_user_readable(tmp_path):
    profile = build_default_runtime_profile(tmp_path)
    topology = ensure_topology(tmp_path, profile)

    lines = topology_summary_lines(topology)

    assert any("Mode: lan-only" in line for line in lines)
    assert any("Local node:" in line for line in lines)
    assert any("capabilities" in line for line in lines)
