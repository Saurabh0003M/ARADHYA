"""P1-6: hardware detection, classification, and model recommendations.

Uses synthetic inputs (not live hardware) so the suite is deterministic.
"""

from __future__ import annotations

import pytest

from src.aradhya.model_setup import FEASIBLE_MODEL_CATALOG, recommend_for_profile
from src.aradhya.utils.hardware_profile import (
    GPUInfo,
    HardwareProfile,
    classify_gpu,
    parse_nvidia_smi,
    parse_wmi_video_csv,
)


# ── classify_gpu ───────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "name,expected",
    [
        ("NVIDIA GeForce RTX 3060", "discrete"),
        ("NVIDIA GeForce GTX 1650", "discrete"),
        ("AMD Radeon RX 6700 XT", "discrete"),
        ("Intel(R) Arc(TM) A770 Graphics", "discrete"),
        ("Intel(R) Arc(TM) Graphics", "integrated"),       # Meteor Lake iGPU
        ("Intel(R) UHD Graphics 620", "integrated"),
        ("Intel(R) Iris(R) Xe Graphics", "integrated"),
        ("AMD Radeon(TM) Graphics", "integrated"),          # APU
        ("Microsoft Basic Display Adapter", "virtual"),
        ("", "unknown"),
    ],
)
def test_classify_gpu(name, expected):
    assert classify_gpu(name) == expected


# ── parsers ────────────────────────────────────────────────────────────

def test_parse_nvidia_smi_multiple():
    out = "NVIDIA GeForce RTX 3060, 12288\nNVIDIA GeForce RTX 4090, 24564\n"
    gpus = parse_nvidia_smi(out)
    assert [g.name for g in gpus] == ["NVIDIA GeForce RTX 3060", "NVIDIA GeForce RTX 4090"]
    assert gpus[0].vram_mb == 12288
    assert all(g.kind == "discrete" for g in gpus)


def test_parse_nvidia_smi_handles_missing_vram():
    gpus = parse_nvidia_smi("NVIDIA GeForce RTX 3060, [N/A]\n")
    assert gpus[0].vram_mb is None


def test_parse_wmi_video_csv_classifies_and_converts_ram():
    out = '"Name","AdapterRAM"\n"Intel(R) Arc(TM) Graphics","2147483648"\n'
    gpus = parse_wmi_video_csv(out)
    assert len(gpus) == 1
    assert gpus[0].name == "Intel(R) Arc(TM) Graphics"
    assert gpus[0].kind == "integrated"
    assert gpus[0].vram_mb == 2048  # 2 GiB → MB


def test_parse_wmi_video_csv_handles_missing_ram_column():
    out = '"Name"\n"NVIDIA GeForce RTX 4090"\n'
    gpus = parse_wmi_video_csv(out)
    assert gpus[0].name == "NVIDIA GeForce RTX 4090"
    assert gpus[0].vram_mb is None
    assert gpus[0].kind == "discrete"


def test_parse_wmi_video_csv_empty():
    assert parse_wmi_video_csv("") == []


# ── HardwareProfile properties ─────────────────────────────────────────

def test_profile_discrete_and_vram():
    profile = HardwareProfile(
        cpu_model="Test CPU",
        logical_cores=8,
        ram_gb=16.0,
        gpus=(
            GPUInfo("Intel Arc Graphics", 2048, "integrated"),
            GPUInfo("NVIDIA RTX 3060", 12288, "discrete"),
        ),
    )
    assert profile.has_discrete_gpu is True
    assert profile.total_vram_mb == 12288  # only discrete counts
    assert "Test CPU" in profile.summary


def test_profile_integrated_only_has_no_discrete_vram():
    profile = HardwareProfile(
        cpu_model="Intel Ultra 5",
        logical_cores=18,
        ram_gb=15.5,
        gpus=(GPUInfo("Intel(R) Arc(TM) Graphics", 2047, "integrated"),),
    )
    assert profile.has_discrete_gpu is False
    assert profile.total_vram_mb is None


# ── recommend_for_profile ──────────────────────────────────────────────

def _profile(ram_gb=None, gpus=()):
    return HardwareProfile("CPU", 8, ram_gb, tuple(gpus))


def test_recommend_uses_vram_for_discrete_gpu():
    profile = _profile(ram_gb=64.0, gpus=[GPUInfo("RTX 3060", 12288, "discrete")])
    rec = recommend_for_profile(profile)
    assert rec.basis == "vram"
    assert rec.budget_gb == 12.0
    # Largest model fitting 12 GB should be offered first.
    assert rec.feasible[0].min_ram_gb <= 12.0


def test_recommend_uses_system_ram_for_igpu():
    # iGPU only → CPU inference off system RAM (× 0.6).
    profile = _profile(ram_gb=16.0, gpus=[GPUInfo("Intel Arc Graphics", 2048, "integrated")])
    rec = recommend_for_profile(profile)
    assert rec.basis == "system_ram"
    assert rec.budget_gb == 9.6  # 16.0 * 0.6
    assert rec.feasible  # something fits
    assert all(m.min_ram_gb <= rec.budget_gb for m in rec.feasible)


def test_recommend_low_memory_suggests_cloud():
    profile = _profile(ram_gb=2.0)  # 1.2 GB usable → below floor
    rec = recommend_for_profile(profile)
    assert rec.suggest_cloud is True
    assert rec.feasible == ()


def test_recommend_unknown_memory_suggests_cloud():
    rec = recommend_for_profile(_profile(ram_gb=None))
    assert rec.budget_gb is None
    assert rec.suggest_cloud is True


def test_recommend_high_ram_still_flags_cloud_for_biggest():
    profile = _profile(ram_gb=32.0)  # ~19.2 GB usable
    rec = recommend_for_profile(profile)
    # The 32B model (needs ~22 GB) shouldn't fit 19.2 GB, so cloud is suggested.
    biggest = max(FEASIBLE_MODEL_CATALOG, key=lambda m: m.min_ram_gb)
    assert biggest.min_ram_gb > rec.budget_gb
    assert rec.suggest_cloud is True


# ── analyze_hardware tool ──────────────────────────────────────────────

def test_analyze_hardware_tool(monkeypatch):
    from src.aradhya.tools import hardware_tools

    fixed = HardwareProfile(
        "Intel Ultra 5 125H", 18, 15.5,
        (GPUInfo("Intel(R) Arc(TM) Graphics", 2047, "integrated"),),
    )
    monkeypatch.setattr(hardware_tools, "detect_hardware_profile", lambda: fixed)

    out = hardware_tools.analyze_hardware()

    assert "Intel Ultra 5 125H" in out
    assert "run locally" in out
    assert "ollama pull" in out


# ── topology wiring ────────────────────────────────────────────────────

def test_topology_detect_hardware_formats_gpu(monkeypatch):
    from src.aradhya import topology

    fixed = HardwareProfile(
        "Intel Ultra 5", 18, 15.5,
        (GPUInfo("Intel(R) Arc(TM) Graphics", 2047, "integrated"),),
    )
    monkeypatch.setattr(
        "src.aradhya.utils.hardware_profile.detect_hardware_profile", lambda: fixed
    )

    hardware = topology._detect_hardware()

    assert hardware["cpu_model"] == "Intel Ultra 5"
    assert "Intel(R) Arc(TM) Graphics" in hardware["gpu"]
    assert "[integrated]" in hardware["gpu"]
    assert hardware["gpus"][0]["kind"] == "integrated"


def test_topology_detect_hardware_degrades_on_error(monkeypatch):
    from src.aradhya import topology

    def boom():
        raise RuntimeError("no WMI")

    monkeypatch.setattr(
        "src.aradhya.utils.hardware_profile.detect_hardware_profile", boom
    )

    hardware = topology._detect_hardware()
    assert hardware == {"cpu_model": "unknown", "gpu": "unknown", "gpus": []}
