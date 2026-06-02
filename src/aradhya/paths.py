"""Centralized path resolution for Aradhya / Parasite OS.

All filesystem paths in the system resolve through this module.
This makes the OS fully portable — it can live on any drive letter,
inside a VirtualBox/VMware VM image, or on an external SSD.

Resolution order:
    1. ``ARADHYA_HOME`` env var — overrides everything
    2. ``<project_root>/parasite.toml`` → ``[paths].home``
    3. Default: ``~/.aradhya``

Usage::

    from src.aradhya.paths import aradhya_home, aradhya_path

    home = aradhya_home()                    # e.g. D:\\ParasiteOS\\.aradhya
    audit = aradhya_path("audit")            # e.g. D:\\ParasiteOS\\.aradhya\\audit
    hooks = aradhya_path("hooks")            # e.g. D:\\ParasiteOS\\.aradhya\\hooks
    sessions = aradhya_path("sessions")      # etc.

VM portability:
    When packaging as a VDI/VMDK, set ARADHYA_HOME in the guest OS
    or place a ``parasite.toml`` at the project root with::

        [paths]
        home = "/opt/aradhya"   # Linux VM
        # or
        home = "D:\\ParasiteOS"  # Windows VM

    The entire system will resolve all paths relative to that root.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from loguru import logger

# ---------------------------------------------------------------------------
# Core resolution
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def aradhya_home() -> Path:
    """Resolve the ARADHYA home directory.

    Resolution order:
        1. ARADHYA_HOME environment variable
        2. parasite.toml in project root (if discoverable)
        3. ~/.aradhya (default)

    The result is cached for the process lifetime.
    """
    # 1. Environment variable — highest priority (VM/container override)
    env_home = os.environ.get("ARADHYA_HOME")
    if env_home:
        home = Path(env_home).resolve()
        logger.debug("ARADHYA_HOME from env: {}", home)
        return home

    # 2. Try to find parasite.toml in project root
    toml_home = _read_parasite_toml_home()
    if toml_home is not None:
        logger.debug("ARADHYA_HOME from parasite.toml: {}", toml_home)
        return toml_home

    # 3. Default: ~/.aradhya
    home = Path.home() / ".aradhya"
    logger.debug("ARADHYA_HOME default: {}", home)
    return home


def aradhya_path(*parts: str) -> Path:
    """Resolve a path relative to ARADHYA_HOME.

    Examples::

        aradhya_path("audit")           → ~/.aradhya/audit
        aradhya_path("hooks")           → ~/.aradhya/hooks
        aradhya_path("sessions")        → ~/.aradhya/sessions
        aradhya_path("skills")          → ~/.aradhya/skills
        aradhya_path("worktrees")       → ~/.aradhya/worktrees
    """
    return aradhya_home().joinpath(*parts)


def ensure_aradhya_dir(*parts: str) -> Path:
    """Like aradhya_path() but also creates the directory if needed."""
    path = aradhya_path(*parts)
    path.mkdir(parents=True, exist_ok=True)
    return path


# ---------------------------------------------------------------------------
# Project root discovery
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def find_project_root() -> Path | None:
    """Walk up from CWD looking for markers of the project root.

    Looks for: pyproject.toml, .git, AGENTS.md, parasite.toml
    """
    cwd = Path.cwd().resolve()
    markers = {"pyproject.toml", ".git", "AGENTS.md", "parasite.toml"}

    for parent in [cwd, *cwd.parents]:
        if any((parent / m).exists() for m in markers):
            return parent
    return None


# ---------------------------------------------------------------------------
# parasite.toml reader
# ---------------------------------------------------------------------------


def _read_parasite_toml_home() -> Path | None:
    """Try to read [paths].home from parasite.toml at project root."""
    root = find_project_root()
    if root is None:
        return None

    toml_path = root / "parasite.toml"
    if not toml_path.is_file():
        return None

    try:
        try:
            import tomllib  # Python 3.11+  # pylint: disable=import-outside-toplevel
        except ImportError:
            try:
                import tomli as tomllib  # type: ignore[no-redef]  # pylint: disable=import-outside-toplevel
            except ImportError:
                return None

        data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
        home_str = data.get("paths", {}).get("home")
        if home_str:
            return Path(home_str).resolve()
    except Exception as exc:
        logger.warning("Failed to read parasite.toml: {}", exc)

    return None


# ---------------------------------------------------------------------------
# Well-known subdirectories
# ---------------------------------------------------------------------------


def audit_dir() -> Path:
    """~/.aradhya/audit"""
    return ensure_aradhya_dir("audit")


def hooks_dir() -> Path:
    """~/.aradhya/hooks"""
    return ensure_aradhya_dir("hooks")


def sessions_dir() -> Path:
    """~/.aradhya/sessions"""
    return ensure_aradhya_dir("sessions")


def skills_dir() -> Path:
    """~/.aradhya/skills"""
    return ensure_aradhya_dir("skills")


def agents_dir() -> Path:
    """~/.aradhya/agents"""
    return ensure_aradhya_dir("agents")


def worktrees_dir() -> Path:
    """~/.aradhya/worktrees"""
    return ensure_aradhya_dir("worktrees")


def notes_dir() -> Path:
    """~/.aradhya/notes"""
    return ensure_aradhya_dir("notes")


def state_dir() -> Path:
    """~/.aradhya (state files live at root level)"""
    return ensure_aradhya_dir()


def repos_dir() -> Path:
    """~/.aradhya/repos — digested host repos archive"""
    return ensure_aradhya_dir("repos")


# ---------------------------------------------------------------------------
# Cache invalidation (for tests)
# ---------------------------------------------------------------------------


def reset_cache() -> None:
    """Clear cached path resolution. Used in tests."""
    aradhya_home.cache_clear()
    find_project_root.cache_clear()
