"""Shared data models for the Aradhya assistant runtime."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

DEFAULT_SECURITY_BLOGS = (
    "https://krebsonsecurity.com/",
    "https://thehackernews.com/",
    "https://www.bleepingcomputer.com/",
)


class WakeSource(str, Enum):
    """Ways the assistant can be awakened."""

    FLOATING_ICON = "floating_icon"
    HOTKEY = "ctrl+win"


class PlanKind(str, Enum):
    """High-level action categories Aradhya can plan."""

    OPEN_PATH = "open_path"
    OPEN_SECURITY_BLOGS = "open_security_blogs"
    LOCATE_TXT_DENSE_FOLDER = "locate_txt_dense_folder"
    OPEN_YESTERDAYS_PROJECT = "open_yesterdays_project"
    OPEN_RECENT_GAME = "open_recent_game"
    SCREEN_CONTROL = "screen_control"
    EXTERNAL_DOCUMENT_HANDOFF = "external_document_handoff"
    DEBATE_RESEARCH = "debate_research"
    TOGGLE_DEBATE = "toggle_debate"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class DirectoryIndexPolicy:
    """Controls when and how the directory index is refreshed."""

    refresh_on_wake: bool = True
    refresh_on_local_query: bool = True
    ignored_names: tuple[str, ...] = (
        ".git",
        "__pycache__",
        "appdata",
        "cache",
        "node_modules",
        "temp",
        "tmp",
        "venv",
    )
    max_nodes: int | None = 25000


@dataclass(frozen=True)
class AssistantPreferences:
    """Preference bundle used by the assistant core."""

    user_roots: tuple[Path, ...]
    directory_index_path: Path
    confirmation_phrases: tuple[str, ...]
    security_blog_urls: tuple[str, ...]
    project_markers: tuple[str, ...]
    game_library_roots: tuple[Path, ...]
    allow_live_execution: bool = False
    directory_index_policy: DirectoryIndexPolicy = field(
        default_factory=DirectoryIndexPolicy
    )


@dataclass(frozen=True)
class PlanAction:
    """Planned action waiting for confirmation or execution."""

    kind: PlanKind
    summary: str
    requires_confirmation: bool = True
    uses_local_data: bool = False
    external_handoff: bool = False
    ready: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExecutionResult:
    """Outcome of a confirmed action."""

    success: bool
    message: str
    artifacts: tuple[str, ...] = ()


@dataclass(frozen=True)
class DirectoryIndexSnapshot:
    """Metadata about a directory index refresh."""

    path: Path
    generated_at: datetime
    reason: str
    scanned_roots: tuple[str, ...]
    node_count: int
    truncated: bool


@dataclass
class AssistantState:
    """Mutable conversational state."""

    is_awake: bool = False
    debate_mode_enabled: bool = False
    pending_plan: PlanAction | None = None


@dataclass(frozen=True)
class AssistantResponse:
    """Response returned to the UI or CLI after each interaction."""

    spoken_response: str
    transcript_echo: str = ""
    plan: PlanAction | None = None
    result: ExecutionResult | None = None
    awaiting_confirmation: bool = False
    index_snapshot: DirectoryIndexSnapshot | None = None


def _project_root_from_here() -> Path:
    return Path(__file__).resolve().parents[2]


def _build_default_user_roots(project_root: Path) -> tuple[Path, ...]:
    """Return safe default search roots for the current machine.

    The assistant should not assume a specific drive letter such as ``F:/``.
    Instead, it searches the current user's home folder and, when different,
    the cloned project root so the repo remains discoverable after a fresh clone.
    """

    roots: list[Path] = [Path.home()]
    if project_root not in roots and not str(project_root).startswith(str(Path.home())):
        roots.append(project_root)
    return tuple(roots)


def _resolve_paths(
    raw_paths: list[str] | tuple[str, ...] | None,
    project_root: Path,
    fallback: tuple[Path, ...],
) -> tuple[Path, ...]:
    if not raw_paths:
        return fallback

    resolved_paths: list[Path] = []
    for raw_path in raw_paths:
        path = Path(raw_path)
        if not path.is_absolute():
            path = project_root / path
        resolved_paths.append(path)

    return tuple(resolved_paths)


def build_default_preferences(project_root: Path | None = None) -> AssistantPreferences:
    """Build default preferences for the current workstation."""

    root = project_root or _project_root_from_here()

    return AssistantPreferences(
        user_roots=_build_default_user_roots(root),
        directory_index_path=root / "project_tree.txt",
        confirmation_phrases=("yes proceed", "proceed", "confirm", "go ahead"),
        security_blog_urls=DEFAULT_SECURITY_BLOGS,
        project_markers=(
            "pyproject.toml",
            "package.json",
            "requirements.txt",
            "Cargo.toml",
            ".git",
        ),
        game_library_roots=tuple(),
        allow_live_execution=False,
        directory_index_policy=DirectoryIndexPolicy(),
    )


def load_preferences(project_root: Path | None = None) -> AssistantPreferences:
    """Load preferences from disk and merge them over the defaults."""

    root = project_root or _project_root_from_here()
    defaults = build_default_preferences(root)
    preferences_path = root / "core" / "memory" / "preferences.json"

    if not preferences_path.exists():
        return defaults

    raw_text = preferences_path.read_text(encoding="utf-8").strip()
    if not raw_text:
        return defaults

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        return defaults

    raw_policy = data.get("directory_index_policy", {})
    policy = DirectoryIndexPolicy(
        refresh_on_wake=raw_policy.get(
            "refresh_on_wake", defaults.directory_index_policy.refresh_on_wake
        ),
        refresh_on_local_query=raw_policy.get(
            "refresh_on_local_query",
            defaults.directory_index_policy.refresh_on_local_query,
        ),
        ignored_names=tuple(
            raw_policy.get(
                "ignored_names", defaults.directory_index_policy.ignored_names
            )
        ),
        max_nodes=raw_policy.get(
            "max_nodes", defaults.directory_index_policy.max_nodes
        ),
    )

    directory_index_paths = _resolve_paths(
        [data.get("directory_index_path")]
        if data.get("directory_index_path")
        else None,
        root,
        (defaults.directory_index_path,),
    )

    return AssistantPreferences(
        user_roots=_resolve_paths(data.get("user_roots"), root, defaults.user_roots),
        directory_index_path=directory_index_paths[0],
        confirmation_phrases=tuple(
            data.get("confirmation_phrases", defaults.confirmation_phrases)
        ),
        security_blog_urls=tuple(
            data.get("security_blog_urls", defaults.security_blog_urls)
        ),
        project_markers=tuple(
            data.get("project_markers", defaults.project_markers)
        ),
        game_library_roots=_resolve_paths(
            data.get("game_library_roots"),
            root,
            defaults.game_library_roots,
        ),
        allow_live_execution=data.get(
            "allow_live_execution", defaults.allow_live_execution
        ),
        directory_index_policy=policy,
    )
