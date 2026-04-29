"""File system tools for the agent loop.

These tools allow the model to read, list, and search the file system
during multi-step reasoning.
"""

from __future__ import annotations

import os
from pathlib import Path

from src.aradhya.tools.tool_registry import tool_definition


@tool_definition(
    name="read_file",
    description="Read the contents of a file at the given path. Returns the text content.",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Absolute or relative path to the file to read.",
            },
            "max_lines": {
                "type": "integer",
                "description": "Maximum number of lines to return. Default 200.",
            },
        },
        "required": ["path"],
    },
)
def read_file(path: str, max_lines: int = 200) -> str:
    """Read a file and return its contents."""
    target = Path(path).resolve()
    if not target.is_file():
        return f"Error: File not found: {target}"
    try:
        text = target.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        if len(lines) > max_lines:
            return "\n".join(lines[:max_lines]) + f"\n\n[... truncated, {len(lines)} total lines]"
        return text
    except Exception as error:
        return f"Error reading file: {error}"


@tool_definition(
    name="list_directory",
    description="List the contents of a directory. Returns file and folder names with sizes.",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the directory to list.",
            },
            "max_entries": {
                "type": "integer",
                "description": "Maximum number of entries to return. Default 50.",
            },
        },
        "required": ["path"],
    },
)
def list_directory(path: str, max_entries: int = 50) -> str:
    """List the contents of a directory."""
    target = Path(path).resolve()
    if not target.is_dir():
        return f"Error: Directory not found: {target}"

    entries: list[str] = []
    try:
        for i, item in enumerate(sorted(target.iterdir())):
            if i >= max_entries:
                entries.append(f"... and more (truncated at {max_entries})")
                break
            if item.is_dir():
                entries.append(f"  [DIR]  {item.name}/")
            else:
                size = item.stat().st_size
                entries.append(f"  [FILE] {item.name} ({size:,} bytes)")
    except PermissionError:
        return f"Error: Permission denied for {target}"

    header = f"Contents of {target}:\n"
    return header + "\n".join(entries)


@tool_definition(
    name="search_files",
    description="Search for files by name pattern in a directory tree.",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Root directory to search in.",
            },
            "pattern": {
                "type": "string",
                "description": "Glob pattern to match file names (e.g., '*.py', 'README*').",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum results to return. Default 20.",
            },
        },
        "required": ["path", "pattern"],
    },
)
def search_files(path: str, pattern: str, max_results: int = 20) -> str:
    """Search for files matching a glob pattern."""
    target = Path(path).resolve()
    if not target.is_dir():
        return f"Error: Directory not found: {target}"

    results: list[str] = []
    try:
        for match in target.rglob(pattern):
            if any(
                p.startswith(".") or p.lower() in {"node_modules", "__pycache__", "venv"}
                for p in match.parts
            ):
                continue
            results.append(str(match))
            if len(results) >= max_results:
                break
    except PermissionError:
        return f"Error: Permission denied searching {target}"

    if not results:
        return f"No files matching '{pattern}' found in {target}"
    return f"Found {len(results)} file(s):\n" + "\n".join(results)


@tool_definition(
    name="write_file",
    description="Write content to a file. Creates the file if it doesn't exist.",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the file to write.",
            },
            "content": {
                "type": "string",
                "description": "Content to write to the file.",
            },
        },
        "required": ["path", "content"],
    },
    requires_confirmation=True,
)
def write_file(path: str, content: str) -> str:
    """Write content to a file."""
    target = Path(path).resolve()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"Successfully wrote {len(content)} characters to {target}"
    except Exception as error:
        return f"Error writing file: {error}"


ALL_FILE_TOOLS = [read_file, list_directory, search_files, write_file]
