"""Hardware detection for reality-grounded model recommendations (P1-6).

Replaces the hardcoded ``gpu: "unknown"`` in ``topology`` with a real CPU/GPU/
VRAM probe, and feeds ``model_setup`` so "what can I run on this machine?" is
answered from detected hardware rather than a static catalog.

Detection is best-effort and never raises: every probe is wrapped so a missing
tool (no ``nvidia-smi``), a denied WMI query, or a non-Windows OS degrades to a
partial profile instead of an error. The pure parse/classify helpers are kept
separate from the I/O so they can be unit-tested without real hardware.
"""

from __future__ import annotations

import os
import platform
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GPUInfo:
    """A single detected graphics adapter."""

    name: str
    vram_mb: int | None = None
    kind: str = "unknown"  # "discrete" | "integrated" | "virtual" | "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "vram_mb": self.vram_mb, "kind": self.kind}


@dataclass(frozen=True)
class HardwareProfile:
    """Detected hardware summary for this machine."""

    cpu_model: str
    logical_cores: int
    ram_gb: float | None
    gpus: tuple[GPUInfo, ...]

    @property
    def has_discrete_gpu(self) -> bool:
        return any(g.kind == "discrete" for g in self.gpus)

    @property
    def total_vram_mb(self) -> int | None:
        """Sum of discrete-GPU VRAM, or None if no discrete VRAM was detected."""
        values = [g.vram_mb for g in self.gpus if g.kind == "discrete" and g.vram_mb]
        return sum(values) if values else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "cpu_model": self.cpu_model,
            "logical_cores": self.logical_cores,
            "ram_gb": self.ram_gb,
            "has_discrete_gpu": self.has_discrete_gpu,
            "total_vram_mb": self.total_vram_mb,
            "gpus": [g.to_dict() for g in self.gpus],
        }

    @property
    def summary(self) -> str:
        ram = f"{self.ram_gb:g} GB RAM" if self.ram_gb else "RAM unknown"
        if self.gpus:
            gpu_bits = []
            for g in self.gpus:
                vram = f" {g.vram_mb} MB" if g.vram_mb else ""
                gpu_bits.append(f"{g.name}{vram} [{g.kind}]")
            gpu = "; ".join(gpu_bits)
        else:
            gpu = "no GPU detected"
        return f"{self.cpu_model} ({self.logical_cores} cores), {ram}, GPU: {gpu}"


# ── Classification (pure) ──────────────────────────────────────────────

_DISCRETE_SIGNALS = (
    "nvidia", "geforce", "rtx", "gtx", "quadro", "tesla",
    "radeon rx", "radeon pro",
)
_INTEGRATED_SIGNALS = ("uhd graphics", "iris", "intel(r) graphics", "vega")


def classify_gpu(name: str) -> str:
    """Heuristically classify a GPU as discrete / integrated / virtual / unknown."""
    lowered = name.lower()
    if not lowered.strip():
        return "unknown"
    if "microsoft basic" in lowered or "virtual" in lowered:
        return "virtual"
    if any(sig in lowered for sig in _DISCRETE_SIGNALS):
        return "discrete"
    # Intel Arc *A-series* (A770/A750/A580/A380) are discrete; the Meteor-Lake
    # "Arc Graphics" iGPU has no A-number.
    if "arc" in lowered and re.search(r"\ba\d{3}\b", lowered):
        return "discrete"
    if "intel" in lowered and ("graphics" in lowered or "iris" in lowered):
        return "integrated"
    if "radeon" in lowered and "graphics" in lowered:
        return "integrated"  # AMD APU integrated graphics
    if any(sig in lowered for sig in _INTEGRATED_SIGNALS):
        return "integrated"
    return "unknown"


def parse_nvidia_smi(output: str) -> list[GPUInfo]:
    """Parse ``nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits``."""
    gpus: list[GPUInfo] = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(",")]
        name = parts[0]
        vram_mb: int | None = None
        if len(parts) >= 2:
            try:
                vram_mb = int(float(parts[1]))
            except ValueError:
                vram_mb = None
        gpus.append(GPUInfo(name=name, vram_mb=vram_mb, kind="discrete"))
    return gpus


def parse_wmi_video_csv(output: str) -> list[GPUInfo]:
    """Parse ``Get-CimInstance Win32_VideoController | ... | ConvertTo-Csv``.

    Expected columns (in any order): ``Name`` and ``AdapterRAM`` (bytes). The
    AdapterRAM field is a 32-bit value so it caps around 4 GB and is unreliable
    for large VRAM — treat it as approximate. The adapter name is reliable.
    """
    lines = [ln for ln in output.splitlines() if ln.strip()]
    if not lines:
        return []

    header = [h.strip().strip('"').lower() for h in lines[0].split(",")]
    try:
        name_idx = header.index("name")
    except ValueError:
        return []
    ram_idx = header.index("adapterram") if "adapterram" in header else None

    gpus: list[GPUInfo] = []
    for row in lines[1:]:
        cells = [c.strip().strip('"') for c in row.split(",")]
        if name_idx >= len(cells):
            continue
        name = cells[name_idx]
        if not name:
            continue
        vram_mb: int | None = None
        if ram_idx is not None and ram_idx < len(cells):
            try:
                ram_bytes = int(cells[ram_idx])
                if ram_bytes > 0:
                    vram_mb = ram_bytes // (1024 * 1024)
            except ValueError:
                vram_mb = None
        gpus.append(GPUInfo(name=name, vram_mb=vram_mb, kind=classify_gpu(name)))
    return gpus


# ── Detection (I/O, best-effort) ───────────────────────────────────────

def detect_cpu_model() -> str:
    """Return a human CPU model string, falling back to platform info."""
    if sys.platform == "win32":
        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
            )
            try:
                value, _ = winreg.QueryValueEx(key, "ProcessorNameString")
                if value:
                    return str(value).strip()
            finally:
                winreg.CloseKey(key)
        except Exception:
            pass
    else:
        try:
            with open("/proc/cpuinfo", encoding="utf-8", errors="ignore") as handle:
                for line in handle:
                    if line.lower().startswith("model name"):
                        return line.split(":", 1)[1].strip()
        except OSError:
            pass
    return platform.processor() or platform.machine() or "Unknown CPU"


def _run(cmd: list[str], timeout: float = 8.0) -> str | None:
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def detect_gpus() -> list[GPUInfo]:
    """Detect GPUs via nvidia-smi, then Windows WMI. Best-effort."""
    nvidia = _run(
        ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"]
    )
    if nvidia:
        gpus = parse_nvidia_smi(nvidia)
        if gpus:
            return gpus

    if sys.platform == "win32":
        wmi = _run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_VideoController | "
                "Select-Object Name, AdapterRAM | ConvertTo-Csv -NoTypeInformation",
            ]
        )
        if wmi:
            return parse_wmi_video_csv(wmi)

    return []


def _total_ram_gb() -> float | None:
    if sys.platform == "win32":
        import ctypes

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
        return None

    try:
        with open("/proc/meminfo", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                if line.startswith("MemTotal:"):
                    parts = line.split()
                    if len(parts) >= 2 and parts[1].isdigit():
                        return round(int(parts[1]) / (1024**2), 2)
    except OSError:
        pass
    return None


def detect_hardware_profile() -> HardwareProfile:
    """Probe this machine and return a best-effort HardwareProfile."""
    return HardwareProfile(
        cpu_model=detect_cpu_model(),
        logical_cores=os.cpu_count() or 1,
        ram_gb=_total_ram_gb(),
        gpus=tuple(detect_gpus()),
    )
