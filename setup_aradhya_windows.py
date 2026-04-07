#!/usr/bin/env python3
"""
Portable Windows setup helper for the Aradhya repository.

This script prepares the common runtime folders relative to the cloned repo
instead of assuming a fixed drive letter or user-specific path.
"""

from __future__ import annotations

from pathlib import Path


def ensure_directory(path: Path) -> None:
    """Create one directory and print a short status line."""

    path.mkdir(parents=True, exist_ok=True)
    print(f"[ok] {path}")


def main() -> None:
    """Prepare the common folders that a fresh clone expects."""

    repo_root = Path(__file__).resolve().parent
    print(f"Preparing Aradhya in: {repo_root}")

    runtime_directories = (
        repo_root / "audio" / "inbox",
        repo_root / "audio" / "processed",
        repo_root / "audio" / "transcripts",
        repo_root / "audio" / "manual_transcripts",
        repo_root / "data" / "raw",
        repo_root / "data" / "processed",
        repo_root / "core" / "logs",
    )

    for directory in runtime_directories:
        # All runtime paths are created relative to the cloned repository so
        # the project stays portable across machines and drive letters.
        ensure_directory(directory)

    print()
    print("Next steps:")
    print("1. py -3.10 -m venv venv")
    print("2. venv\\Scripts\\python.exe -m pip install --upgrade pip")
    print("3. venv\\Scripts\\python.exe -m pip install -r requirements.txt")
    print("4. venv\\Scripts\\python.exe -m pip install -r requirements-dev.txt")
    print("5. venv\\Scripts\\python.exe -m core.agent.aradhya")


if __name__ == "__main__":
    main()
