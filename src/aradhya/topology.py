"""Local topology detection for Aradhya federation.

The topology is capability-driven on purpose: Opus and future workers should
not hard-code this machine, the user's current phone, or any fixed device set.
Every node reports what it can safely do, and routing should depend on that
manifest instead of device names.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import platform
import re
import shutil
import socket
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from loguru import logger

from src.aradhya.runtime_profile import RuntimeProfile

TOPOLOGY_FILENAME = "topology.yaml"


def topology_path(project_root: Path) -> Path:
    """Return the shared topology config path."""

    return project_root / "core" / "config" / TOPOLOGY_FILENAME


def load_topology(project_root: Path) -> dict[str, Any] | None:
    """Load topology if it already exists."""

    path = topology_path(project_root)
    if not path.is_file():
        return None
    raw_text = path.read_text(encoding="utf-8")
    payload = _load_mapping(raw_text)
    return payload if isinstance(payload, dict) else None


def ensure_topology(
    project_root: Path,
    runtime_profile: RuntimeProfile,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Load topology, or generate it when missing or explicitly forced."""

    if not force:
        existing = load_topology(project_root)
        if existing is not None:
            return existing

    payload = build_topology(project_root, runtime_profile)
    path = topology_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        _dump_mapping(payload),
        encoding="utf-8",
    )
    return payload


def build_topology(project_root: Path, runtime_profile: RuntimeProfile) -> dict[str, Any]:
    """Detect the local node and build a portable topology payload."""

    local_node = detect_local_node(project_root, runtime_profile)
    now = datetime.now(timezone.utc).isoformat()
    return {
        "version": 1,
        "generated_at": now,
        "updated_at": now,
        "transport": {
            "mode": "lan-only",
            "hub_bind_host": "127.0.0.1",
            "hub_port": 19842,
            "internet_federation": False,
        },
        "local_node_id": local_node["node_id"],
        "nodes": [local_node],
    }


def detect_local_node(
    project_root: Path,
    runtime_profile: RuntimeProfile,
) -> dict[str, Any]:
    """Return a capability manifest for this machine."""

    hostname = socket.gethostname() or "aradhya-node"
    node_id = _stable_node_id(hostname)
    disk = _disk_summary(project_root)
    hardware = _detect_hardware()
    resources = {
        "cpu_count": os.cpu_count() or 1,
        "cpu_model": hardware["cpu_model"],
        "ram_gb": _total_ram_gb(),
        "disk_total_gb": disk["total_gb"],
        "disk_free_gb": disk["free_gb"],
        "gpu": hardware["gpu"],
        "gpus": hardware["gpus"],
    }
    capabilities = [
        {"name": "aradhya_core", "kind": "system", "enabled": True},
        {"name": "filesystem_index", "kind": "context", "enabled": True},
        {"name": "voice_inbox", "kind": "voice", "enabled": True},
        {"name": "federation_hub", "kind": "transport", "enabled": True},
    ]
    if runtime_profile.model.provider.lower() == "ollama":
        capabilities.append(
            {
                "name": "local_model",
                "kind": "model",
                "enabled": True,
                "model": runtime_profile.model.model_name,
            }
        )
    elif runtime_profile.model.provider.lower() != "ollama":
        capabilities.append(
            {
                "name": "cloud_model_optional",
                "kind": "model",
                "enabled": bool(runtime_profile.model.api_key),
                "model": runtime_profile.model.model_name,
                "provider": runtime_profile.model.provider,
            }
        )

    return {
        "node_id": node_id,
        "display_name": hostname,
        "role": "primary",
        "device_class": _device_class(resources),
        "os": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "python": sys.version.split()[0],
        },
        "resources": resources,
        "capabilities": capabilities,
        "paths": {
            "project_root": str(project_root),
            "topology": str(topology_path(project_root)),
        },
        "privacy_level": "local",
    }


def topology_summary_lines(topology: dict[str, Any]) -> list[str]:
    """Format topology as user-readable lines."""

    nodes = topology.get("nodes") or []
    lines = [
        f"Version: {topology.get('version', '?')}",
        f"Mode: {topology.get('transport', {}).get('mode', 'unknown')}",
        f"Local node: {topology.get('local_node_id', 'unknown')}",
        f"Nodes: {len(nodes)}",
    ]
    for node in nodes:
        resources = node.get("resources", {})
        caps = node.get("capabilities", [])
        lines.append(
            " - {node_id} ({role}, {device_class}): CPU {cpu}, RAM {ram}, "
            "free disk {disk}, capabilities {cap_count}".format(
                node_id=node.get("node_id", "unknown"),
                role=node.get("role", "unknown"),
                device_class=node.get("device_class", "unknown"),
                cpu=resources.get("cpu_count", "?"),
                ram=_format_gb(resources.get("ram_gb")),
                disk=_format_gb(resources.get("disk_free_gb")),
                cap_count=len(caps),
            )
        )
    return lines


def _stable_node_id(hostname: str) -> str:
    raw = f"{hostname}-{uuid.getnode()}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]
    cleaned = re.sub(r"[^a-z0-9-]+", "-", hostname.lower()).strip("-")
    return f"{cleaned or 'aradhya'}-{digest}"


def _detect_hardware() -> dict[str, Any]:
    """Detect CPU/GPU details, degrading to safe defaults on any failure."""
    try:
        from src.aradhya.utils.hardware_profile import detect_hardware_profile

        profile = detect_hardware_profile()
        if profile.gpus:
            primary = profile.gpus[0]
            vram = f" {primary.vram_mb} MB" if primary.vram_mb else ""
            gpu_label = f"{primary.name}{vram} [{primary.kind}]"
        else:
            gpu_label = "none detected"
        return {
            "cpu_model": profile.cpu_model,
            "gpu": gpu_label,
            "gpus": [g.to_dict() for g in profile.gpus],
        }
    except Exception as error:  # detection must never break topology
        logger.debug("Hardware detection failed: {}", error)
        return {"cpu_model": "unknown", "gpu": "unknown", "gpus": []}


def _device_class(resources: dict[str, Any]) -> str:
    ram = resources.get("ram_gb") or 0
    cpu = resources.get("cpu_count") or 1
    if ram >= 12 and cpu >= 8:
        return "workstation"
    if ram >= 6:
        return "companion"
    return "lightweight"


def _disk_summary(project_root: Path) -> dict[str, float | None]:
    try:
        usage = shutil.disk_usage(project_root.anchor or project_root)
    except OSError:
        return {"total_gb": None, "free_gb": None}
    return {
        "total_gb": round(usage.total / (1024**3), 2),
        "free_gb": round(usage.free / (1024**3), 2),
    }


def _total_ram_gb() -> float | None:
    if sys.platform == "win32":
        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.dwLength = ctypes.sizeof(status)
        try:
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return round(status.ullTotalPhys / (1024**3), 2)
        except Exception:
            return None

    meminfo = Path("/proc/meminfo")
    if meminfo.is_file():
        for line in meminfo.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("MemTotal:"):
                parts = line.split()
                if len(parts) >= 2 and parts[1].isdigit():
                    return round(int(parts[1]) / (1024**2), 2)
    return None


def _format_gb(value: Any) -> str:
    if value is None:
        return "unknown"
    return f"{value} GB"


def _dump_mapping(payload: dict[str, Any]) -> str:
    try:
        dumped = yaml.safe_dump(payload, sort_keys=False, allow_unicode=False)
        if isinstance(dumped, str):
            return dumped
    except Exception:
        pass
    return json.dumps(payload, indent=2) + "\n"


def _load_mapping(raw_text: str) -> dict[str, Any]:
    try:
        loaded = yaml.safe_load(raw_text) or {}
        if isinstance(loaded, dict):
            return loaded
    except Exception:
        pass
    try:
        loaded = json.loads(raw_text)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}
