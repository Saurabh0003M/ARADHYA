"""System-level tools for the agent loop.

These tools provide access to Windows system operations like opening
apps, URLs, and managing the clipboard.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from src.aradhya.tools.tool_registry import tool_definition


@tool_definition(
    name="open_path",
    description="Open a file, folder, or application using the system default handler.",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "File path, folder path, or application name to open.",
            },
        },
        "required": ["path"],
    },
    requires_confirmation=True,
)
def open_path(path: str) -> str:
    """Open a path using the system's default handler."""
    target = Path(path)
    try:
        if os.name == "nt":
            os.startfile(str(target))  # type: ignore[attr-defined]
        else:
            subprocess.run(["xdg-open", str(target)], check=True)
        return f"Opened: {target}"
    except Exception as error:
        return f"Error opening path: {error}"


@tool_definition(
    name="open_url",
    description="Open a URL in the default web browser.",
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to open.",
            },
        },
        "required": ["url"],
    },
    requires_confirmation=True,
)
def open_url(url: str) -> str:
    """Open a URL in the default browser."""
    import webbrowser
    try:
        webbrowser.open(url)
        return f"Opened URL: {url}"
    except Exception as error:
        return f"Error opening URL: {error}"


@tool_definition(
    name="clipboard_read",
    description="Read the current content of the system clipboard.",
    parameters={"type": "object", "properties": {}},
)
def clipboard_read() -> str:
    """Read the system clipboard on Windows."""
    try:
        if os.name != "nt":
            return "Clipboard reading is only supported on Windows."
        result = subprocess.run(
            ["powershell", "-Command", "Get-Clipboard"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode == 0:
            content = result.stdout.strip()
            if not content:
                return "Clipboard is empty."
            return f"Clipboard content:\n{content[:2000]}"
        return "Failed to read clipboard."
    except Exception as error:
        return f"Error reading clipboard: {error}"


@tool_definition(
    name="clipboard_write",
    description="Write text to the system clipboard.",
    parameters={
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "The text to copy to the clipboard.",
            },
        },
        "required": ["text"],
    },
    requires_confirmation=True,
)
def clipboard_write(text: str) -> str:
    """Write text to the system clipboard on Windows."""
    try:
        if os.name != "nt":
            return "Clipboard writing is only supported on Windows."
        subprocess.run(
            ["powershell", "-Command", f"Set-Clipboard -Value '{text}'"],
            check=True,
            timeout=3,
        )
        return f"Copied {len(text)} characters to clipboard."
    except Exception as error:
        return f"Error writing to clipboard: {error}"


ALL_SYSTEM_TOOLS = [open_path, open_url, clipboard_read, clipboard_write]
