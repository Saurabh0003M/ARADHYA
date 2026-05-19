"""Shell execution tools for the agent loop.

These tools allow the model to execute shell commands on the user's
machine, with mandatory confirmation gates for safety.

Command results include structured metadata: exit code, wall time,
stdout, and stderr — matching the Codex tool output protocol.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

from src.aradhya.tools.tool_registry import tool_definition


@tool_definition(
    name="run_command",
    description="Execute a shell command and return its output. Requires user confirmation.",
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

        final_command = command
        # Sandboxing support (ZeroClaw feature)
        if getattr(prefs, "use_docker_sandbox", False):
            try:
                # Check if docker is available
                subprocess.run("docker --version", shell=True, capture_output=True, check=True)
                import shlex
                escaped_cmd = shlex.quote(command)
                # Mount the working directory to /workspace and run the command securely
                final_command = f'docker run --rm -v "{work_dir}:/workspace" -w /workspace python:3.10-slim bash -c {escaped_cmd}'
            except subprocess.CalledProcessError:
                # Docker not installed/running, gracefully fallback to local execution
                pass

        start_time = time.perf_counter()
        result = subprocess.run(
            final_command,
            shell=True,
            capture_output=True,
            text=True,
            cwd=str(work_dir) if final_command == command else None,
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

        return "\n".join(output_parts)

    except subprocess.TimeoutExpired:
        return f"Exit code: -1\nWall time: {timeout}s\nError: Command timed out after {timeout} seconds."
    except Exception as error:
        return f"Exit code: -1\nWall time: 0s\nError: {error}"


ALL_SHELL_TOOLS = [run_command]
