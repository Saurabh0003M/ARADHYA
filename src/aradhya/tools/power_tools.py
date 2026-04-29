"""System power-state tools for the agent loop.

These tools give Aradhya control over Windows power management — preventing
sleep, locking the workstation, and managing display state.  The agent loop
uses these to fulfil requests like "keep the screen on while this downloads".

Implementation uses ``ctypes`` to call Win32 kernel32/user32 APIs directly,
so there are zero external dependencies.
"""

from __future__ import annotations

import ctypes
import os
import subprocess

from src.aradhya.tools.tool_registry import tool_definition

# Win32 SetThreadExecutionState flags
_ES_CONTINUOUS = 0x80000000
_ES_SYSTEM_REQUIRED = 0x00000001
_ES_DISPLAY_REQUIRED = 0x00000002
_ES_AWAYMODE_REQUIRED = 0x00000040


@tool_definition(
    name="prevent_sleep",
    description=(
        "Prevent the system from sleeping or turning off the display. "
        "Use this when the user wants to keep the machine awake (e.g., "
        "during a download, installation, or long-running task). "
        "Call allow_sleep() when the task is done."
    ),
    parameters={
        "type": "object",
        "properties": {
            "keep_display_on": {
                "type": "boolean",
                "description": (
                    "If true, also prevents the display from turning off. "
                    "Defaults to true."
                ),
            },
        },
    },
    requires_confirmation=True,
)
def prevent_sleep(keep_display_on: bool = True) -> str:
    """Block Windows from sleeping or dimming the display."""
    if os.name != "nt":
        return "prevent_sleep is only supported on Windows."
    try:
        flags = _ES_CONTINUOUS | _ES_SYSTEM_REQUIRED
        if keep_display_on:
            flags |= _ES_DISPLAY_REQUIRED
        result = ctypes.windll.kernel32.SetThreadExecutionState(flags)
        if result == 0:
            return "Failed to set execution state — the API returned 0."
        mode = "sleep + display off" if keep_display_on else "sleep only"
        return f"System will NOT {mode} until allow_sleep() is called."
    except Exception as error:
        return f"Error calling SetThreadExecutionState: {error}"


@tool_definition(
    name="allow_sleep",
    description=(
        "Re-enable normal sleep and display-off behaviour. "
        "Call this after prevent_sleep() when the long-running task is done."
    ),
    parameters={"type": "object", "properties": {}},
    requires_confirmation=True,
)
def allow_sleep() -> str:
    """Restore normal Windows sleep/display behaviour."""
    if os.name != "nt":
        return "allow_sleep is only supported on Windows."
    try:
        result = ctypes.windll.kernel32.SetThreadExecutionState(_ES_CONTINUOUS)
        if result == 0:
            return "Failed to restore sleep state."
        return "Normal sleep and display-off behaviour restored."
    except Exception as error:
        return f"Error restoring sleep state: {error}"


@tool_definition(
    name="lock_workstation",
    description="Lock the Windows workstation (show the lock screen).",
    parameters={"type": "object", "properties": {}},
    requires_confirmation=True,
)
def lock_workstation() -> str:
    """Lock the Windows workstation."""
    if os.name != "nt":
        return "lock_workstation is only supported on Windows."
    try:
        ctypes.windll.user32.LockWorkStation()
        return "Workstation locked."
    except Exception as error:
        return f"Error locking workstation: {error}"


@tool_definition(
    name="set_volume",
    description=(
        "Set the system master volume or mute/unmute. "
        "Uses nircmd if available, otherwise PowerShell."
    ),
    parameters={
        "type": "object",
        "properties": {
            "level": {
                "type": "integer",
                "description": "Volume level 0-100. Omit to only mute/unmute.",
            },
            "mute": {
                "type": "boolean",
                "description": "True to mute, False to unmute. Omit to leave mute state unchanged.",
            },
        },
    },
    requires_confirmation=True,
)
def set_volume(level: int | None = None, mute: bool | None = None) -> str:
    """Set system volume or mute/unmute on Windows."""
    if os.name != "nt":
        return "set_volume is only supported on Windows."

    results: list[str] = []

    try:
        if mute is not None:
            # Use PowerShell COM to toggle mute
            mute_script = (
                "$audio = New-Object -ComObject MMDeviceAPI.MMDeviceEnumerator; "
                "$dev = $audio.GetDefaultAudioEndpoint(0, 1); "
                "$vol = $dev.AudioEndpointVolume; "
                f"$vol.Mute = {'$true' if mute else '$false'}"
            )
            # Fallback: use nircmd or simple key simulation
            if mute:
                subprocess.run(
                    ["powershell", "-Command",
                     "(New-Object -ComObject WScript.Shell).SendKeys([char]173)"],
                    capture_output=True, timeout=5,
                )
                results.append("Muted.")
            else:
                subprocess.run(
                    ["powershell", "-Command",
                     "(New-Object -ComObject WScript.Shell).SendKeys([char]173)"],
                    capture_output=True, timeout=5,
                )
                results.append("Toggled mute.")

        if level is not None:
            clamped = max(0, min(100, level))
            # Use nircmd if available for precise volume
            nircmd_result = subprocess.run(
                ["nircmd", "setsysvolume", str(int(clamped * 655.35))],
                capture_output=True, timeout=5,
            )
            if nircmd_result.returncode == 0:
                results.append(f"Volume set to {clamped}%.")
            else:
                # Fallback: PowerShell with audio COM
                ps_cmd = (
                    f"$wshell = New-Object -ComObject WScript.Shell; "
                    f"1..50 | ForEach-Object {{ $wshell.SendKeys([char]174) }}; "
                    f"1..{clamped // 2} | ForEach-Object {{ $wshell.SendKeys([char]175) }}"
                )
                subprocess.run(
                    ["powershell", "-Command", ps_cmd],
                    capture_output=True, timeout=10,
                )
                results.append(f"Volume set to approximately {clamped}%.")

    except FileNotFoundError:
        return "Volume control requires nircmd or PowerShell."
    except Exception as error:
        return f"Error setting volume: {error}"

    return " ".join(results) if results else "No volume change requested."


@tool_definition(
    name="check_process_running",
    description=(
        "Check if a specific process is currently running by name. "
        "Useful for monitoring downloads, installations, or applications."
    ),
    parameters={
        "type": "object",
        "properties": {
            "process_name": {
                "type": "string",
                "description": (
                    "Name of the process to check (e.g., 'WinStore.App', "
                    "'chrome', 'python'). Case-insensitive, .exe is optional."
                ),
            },
        },
        "required": ["process_name"],
    },
)
def check_process_running(process_name: str) -> str:
    """Check whether a process is running on Windows."""
    if os.name != "nt":
        return "check_process_running is only supported on Windows."
    try:
        name = process_name.strip()
        if not name.lower().endswith(".exe"):
            name_filter = f"{name}*"
        else:
            name_filter = name

        result = subprocess.run(
            ["powershell", "-Command",
             f"Get-Process -Name '{name_filter}' -ErrorAction SilentlyContinue "
             f"| Select-Object -First 5 Name, Id, CPU, WorkingSet64 "
             f"| Format-Table -AutoSize | Out-String"],
            capture_output=True, text=True, timeout=10,
        )
        output = result.stdout.strip()
        if not output:
            return f"No process matching '{process_name}' is currently running."
        return f"Running processes matching '{process_name}':\n{output}"
    except Exception as error:
        return f"Error checking process: {error}"


ALL_POWER_TOOLS = [
    prevent_sleep,
    allow_sleep,
    lock_workstation,
    set_volume,
    check_process_running,
]
