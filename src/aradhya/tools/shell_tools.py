"""Shell execution tools for the agent loop.

These tools allow the model to execute shell commands on the user's
machine, with mandatory confirmation gates for safety.
"""

from __future__ import annotations

import subprocess
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
    """Execute a shell command and return stdout/stderr."""
    work_dir = Path(cwd).resolve()
    if not work_dir.is_dir():
        return f"Error: Working directory does not exist: {work_dir}"

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            cwd=str(work_dir),
            timeout=timeout,
        )

        output_parts: list[str] = []
        if result.stdout.strip():
            output_parts.append(f"STDOUT:\n{result.stdout.strip()}")
        if result.stderr.strip():
            output_parts.append(f"STDERR:\n{result.stderr.strip()}")
        output_parts.append(f"Exit code: {result.returncode}")

        return "\n\n".join(output_parts)

    except subprocess.TimeoutExpired:
        return f"Error: Command timed out after {timeout} seconds."
    except Exception as error:
        return f"Error executing command: {error}"


ALL_SHELL_TOOLS = [run_command]
