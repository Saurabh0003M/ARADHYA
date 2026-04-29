"""Context engine that aggregates machine and user context for the planner.

Inspired by OpenClaw's context engine, this module collects information from
multiple sources — filesystem index, active session, loaded skills, user
preferences, and optional system signals — into a structured context payload
that the planner and LLM system prompt can consume.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from src.aradhya.assistant_indexer import DirectoryIndexManager
from src.aradhya.assistant_models import AssistantPreferences
from src.aradhya.session_manager import Session
from src.aradhya.skills.skill_models import SkillRegistry


@dataclass(frozen=True)
class ContextSnapshot:
    """Aggregated context payload for the planner."""

    timestamp: str
    machine_name: str
    username: str
    cwd: str
    active_window_title: str
    active_skills: list[str]
    recent_session_topics: list[str]
    project_roots: list[str]
    recent_files: list[str]
    clipboard_text: str
    extra: dict[str, Any] = field(default_factory=dict)

    def to_prompt_block(self) -> str:
        """Format the context as a prompt injection block for the LLM."""
        parts = [
            f"[Context at {self.timestamp}]",
            f"Machine: {self.machine_name}",
            f"User: {self.username}",
            f"Working directory: {self.cwd}",
        ]
        if self.active_window_title:
            parts.append(f"Active window: {self.active_window_title}")
        if self.active_skills:
            parts.append(f"Active skills: {', '.join(self.active_skills)}")
        if self.recent_session_topics:
            parts.append(
                "Recent conversation topics: "
                + "; ".join(self.recent_session_topics[-5:])
            )
        if self.recent_files:
            parts.append(
                "Recently modified files: " + ", ".join(self.recent_files[:10])
            )
        if self.clipboard_text:
            clipped = self.clipboard_text[:200]
            parts.append(f"Clipboard preview: {clipped}")
        return "\n".join(parts)


class ContextEngine:
    """Collects and merges context from available sources."""

    def __init__(
        self,
        preferences: AssistantPreferences,
        index_manager: DirectoryIndexManager | None = None,
        skill_registry: SkillRegistry | None = None,
    ) -> None:
        self.preferences = preferences
        self.index_manager = index_manager
        self.skill_registry = skill_registry

    def build_snapshot(
        self,
        session: Session | None = None,
    ) -> ContextSnapshot:
        """Build a fresh context snapshot from all available sources."""

        active_skills: list[str] = []
        if self.skill_registry is not None:
            active_skills = [s.name for s in self.skill_registry.active_skills()]

        recent_topics: list[str] = []
        if session is not None:
            recent_topics = [
                m.content[:100]
                for m in session.messages[-10:]
                if m.role == "user" and m.content.strip()
            ]

        recent_files = self._find_recent_files()
        clipboard_text = self._read_clipboard()
        active_window = self._get_active_window_title()

        return ContextSnapshot(
            timestamp=datetime.now().isoformat(timespec="seconds"),
            machine_name=os.environ.get("COMPUTERNAME", os.environ.get("HOSTNAME", "unknown")),
            username=os.environ.get("USERNAME", os.environ.get("USER", "unknown")),
            cwd=str(Path.cwd()),
            active_window_title=active_window,
            active_skills=active_skills,
            recent_session_topics=recent_topics,
            project_roots=[str(r) for r in self.preferences.user_roots],
            recent_files=recent_files,
            clipboard_text=clipboard_text,
        )

    def _find_recent_files(self, limit: int = 10) -> list[str]:
        """Find recently modified files in configured user roots."""
        try:
            recent: list[tuple[float, str]] = []
            for root in self.preferences.user_roots:
                if not root.is_dir():
                    continue
                for path in root.rglob("*"):
                    if not path.is_file():
                        continue
                    if any(
                        part.startswith(".")
                        or part.lower() in {"node_modules", "__pycache__", "venv", ".git"}
                        for part in path.parts
                    ):
                        continue
                    try:
                        mtime = path.stat().st_mtime
                        recent.append((mtime, str(path)))
                    except (OSError, PermissionError):
                        continue
                    if len(recent) > 1000:
                        break
            recent.sort(key=lambda x: x[0], reverse=True)
            return [p for _, p in recent[:limit]]
        except Exception as error:
            logger.debug("Recent files scan failed: {}", error)
            return []

    def _read_clipboard(self) -> str:
        """Read the system clipboard on Windows. Returns empty on failure."""
        try:
            if os.name != "nt":
                return ""
            result = subprocess.run(
                ["powershell", "-Command", "Get-Clipboard"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode == 0:
                return result.stdout.strip()[:500]
        except Exception:
            pass
        return ""

    def _get_active_window_title(self) -> str:
        """Get the title of the currently active window on Windows."""
        try:
            if os.name != "nt":
                return ""
            import ctypes
            user32 = ctypes.windll.user32  # type: ignore[attr-defined]
            hwnd = user32.GetForegroundWindow()
            length = user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return ""
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            return buf.value
        except Exception:
            return ""
