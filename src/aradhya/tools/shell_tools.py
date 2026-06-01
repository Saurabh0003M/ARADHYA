"""Shell execution tools for the agent loop.

These tools allow the model to execute shell commands on the user's
machine, with mandatory confirmation gates for safety.

Command results include structured metadata: exit code, wall time,
stdout, and stderr — matching the Codex tool output protocol.
"""

from __future__ import annotations

import collections
import subprocess
import time
from pathlib import Path

from src.aradhya.tools.tool_registry import tool_definition


# ── Gap H: rotating in-memory terminal history buffer ──────────────────
# Stores up to _MAX_TERMINAL_LINES lines from all run_command invocations
# this session. Lets the model call read_terminal_history() to review
# accumulated output without relying on message history alone.
# Inspired by Codex's read_thread_terminal dynamic tool.
_MAX_TERMINAL_LINES = 500
_terminal_buffer: collections.deque[str] = collections.deque(maxlen=_MAX_TERMINAL_LINES)

@tool_definition(
    name="run_command",
    description=(
        "Execute a shell command and return its output. Requires user confirmation. "
        "Note: Shell features like pipes (|) or redirection (>) will no longer work "
        "as commands are executed safely without a shell."
    ),
    parameters={
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to execute.",
            },
            "cwd": {
                "type": "string",
                "description": "Working directory for the command. Default is current directory.",
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds. Default 30.",
            },
        },
        "required": ["command"],
    },
    requires_confirmation=True,
)
def run_command(command: str, cwd: str = ".", timeout: int = 30) -> str:
    """Execute a shell command and return structured stdout/stderr."""
    work_dir = Path(cwd).resolve()
    if not work_dir.is_dir():
        return f"Error: Working directory does not exist: {work_dir}"

    try:
        from src.aradhya.assistant_models import load_preferences
        prefs = load_preferences()

        # Sandboxing support (ZeroClaw feature)
        import shlex
        final_command_args = shlex.split(command)
        is_sandboxed = False

        if getattr(prefs, "use_docker_sandbox", False):
            try:
                # Check if docker is available
                subprocess.run(
                    ["docker", "--version"],
                    shell=False,
                    capture_output=True,
                    check=True
                )
                quoted_command = shlex.quote(command)
                # Mount the working directory to /workspace and run the command securely
                final_command_args = [
                    "docker", "run", "--rm",
                    "-v", f"{work_dir}:/workspace",
                    "-w", "/workspace",
                    "python:3.10-slim",
                    "bash", "-c", quoted_command
                ]
                is_sandboxed = True
            except subprocess.CalledProcessError:
                # Docker not installed/running, gracefully fallback to local execution
                pass

        start_time = time.perf_counter()
        result = subprocess.run(
            final_command_args,
            shell=False,
            capture_output=True,
            text=True,
            cwd=None if is_sandboxed else str(work_dir),
            timeout=timeout,
        )
        wall_time = time.perf_counter() - start_time

        # Structured output matching Codex protocol
        output_parts: list[str] = [
            f"Exit code: {result.returncode}",
            f"Wall time: {wall_time:.1f}s",
        ]
        if result.stdout.strip():
            output_parts.append(f"STDOUT:\n{result.stdout.strip()}")
        if result.stderr.strip():
            output_parts.append(f"STDERR:\n{result.stderr.strip()}")

        full_output = "\n".join(output_parts)

        # ── Gap H: append to rotating terminal history buffer ──
        _terminal_buffer.append(f"$ {command}")
        for line in full_output.splitlines():
            _terminal_buffer.append(line)

        return full_output

    except subprocess.TimeoutExpired:
        _terminal_buffer.append(f"$ {command}")
        _terminal_buffer.append(f"[TIMEOUT after {timeout}s]")
        return f"Exit code: -1\nWall time: {timeout}s\nError: Command timed out after {timeout} seconds."
    except Exception as error:
        _terminal_buffer.append(f"$ {command}")
        _terminal_buffer.append(f"[ERROR: {error}]")
        return f"Exit code: -1\nWall time: 0s\nError: {error}"


@tool_definition(
    name="read_terminal_history",
    description=(
        "Read accumulated terminal output from all run_command calls this session. "
        "Use this to review previous command results without relying on message history. "
        "Inspired by Codex's read_thread_terminal dynamic tool."
    ),
    parameters={
        "type": "object",
        "properties": {
            "last_n_lines": {
                "type": "integer",
                "description": "Number of lines to return from the end of the buffer. Default 100.",
            },
        },
    },
)
def read_terminal_history(last_n_lines: int = 100) -> str:
    """Return the last N lines from the in-session terminal history buffer."""
    if not _terminal_buffer:
        return "Terminal history is empty. No commands have been run yet this session."
    lines = list(_terminal_buffer)
    selected = lines[-max(1, last_n_lines):]
    return (
        f"Terminal history (last {len(selected)} of {len(lines)} lines):\n"
        + "\n".join(selected)
    )


ALL_SHELL_TOOLS = [run_command, read_terminal_history]
