"""Skill installer — download and register new skills from external sources.

Aradhya can absorb new capabilities at runtime from:
1. Git repositories (cloned into ``~/.aradhya/skills/``)
2. Web URLs (content fetched and converted to a skill)
3. Raw code or prompt text (wrapped into a skill folder)

Inspired by ClawHub's skill installation mechanism, but adapted for
Aradhya's lightweight SKILL.md + optional Python tool module architecture.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from src.aradhya.tools.tool_registry import tool_definition

SKILLS_DIR = Path.home() / ".aradhya" / "skills"
TRUST_FILE = Path.home() / ".aradhya" / "trusted_skills.json"


def _load_trusted() -> set[str]:
    """Load the set of trusted skill names."""
    if not TRUST_FILE.is_file():
        return set()
    try:
        data = json.loads(TRUST_FILE.read_text(encoding="utf-8"))
        return set(data.get("trusted", []))
    except (json.JSONDecodeError, OSError):
        return set()


def _save_trusted(names: set[str]) -> None:
    """Persist the trusted skill names."""
    TRUST_FILE.parent.mkdir(parents=True, exist_ok=True)
    TRUST_FILE.write_text(
        json.dumps({"trusted": sorted(names)}, indent=2) + "\n",
        encoding="utf-8",
    )


def _sanitize_name(raw: str) -> str:
    """Convert a raw string into a valid skill directory name."""
    name = re.sub(r"[^a-z0-9_-]", "_", raw.lower().strip())
    name = re.sub(r"_+", "_", name).strip("_")
    return name or "unnamed_skill"


def _extract_name_from_url(url: str) -> str:
    """Extract a skill name from a git URL."""
    # Handle GitHub URLs like https://github.com/user/repo-name.git
    parts = url.rstrip("/").rstrip(".git").split("/")
    return _sanitize_name(parts[-1]) if parts else "imported_skill"


def _create_skill_md(
    skill_dir: Path,
    name: str,
    description: str,
    instructions: str,
    *,
    tool_module: str | None = None,
    source: str = "",
) -> Path:
    """Create a SKILL.md file in the given directory."""
    frontmatter_lines = [
        f"name: {name}",
        f"description: {description}",
        "enabled: true",
    ]
    if tool_module:
        frontmatter_lines.append(f"tool_module: {tool_module}")
    if source:
        frontmatter_lines.append(f"  source: {source}")

    content = (
        "---\n"
        + "\n".join(frontmatter_lines)
        + "\n---\n\n"
        + instructions
        + "\n"
    )

    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(content, encoding="utf-8")
    return skill_file


@tool_definition(
    name="install_skill_from_git",
    description=(
        "Install a new skill from a Git repository. The repo is cloned into "
        "~/.aradhya/skills/ and its SKILL.md is registered. If the repo "
        "doesn't have a SKILL.md, one is auto-generated from the README."
    ),
    parameters={
        "type": "object",
        "properties": {
            "git_url": {
                "type": "string",
                "description": "Git clone URL (https or ssh).",
            },
            "skill_name": {
                "type": "string",
                "description": "Override the skill name (optional, derived from URL otherwise).",
            },
        },
        "required": ["git_url"],
    },
    requires_confirmation=True,
)
def install_skill_from_git(git_url: str, skill_name: str = "") -> str:
    """Clone a git repo and register it as an Aradhya skill."""
    if not git_url.strip():
        return "Error: git_url is required."

    name = _sanitize_name(skill_name) if skill_name else _extract_name_from_url(git_url)
    target_dir = SKILLS_DIR / name

    if target_dir.exists():
        return (
            f"Skill '{name}' already exists at {target_dir}. "
            f"Use uninstall_skill('{name}') first to replace it."
        )

    SKILLS_DIR.mkdir(parents=True, exist_ok=True)

    try:
        result = subprocess.run(
            ["git", "clone", "--depth", "1", git_url, str(target_dir)],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            return f"Git clone failed: {result.stderr.strip()}"
    except FileNotFoundError:
        return "Error: git is not installed or not on PATH."
    except subprocess.TimeoutExpired:
        return "Error: git clone timed out after 120 seconds."

    # Check if SKILL.md already exists in the repo
    skill_file = target_dir / "SKILL.md"
    if not skill_file.is_file():
        # Try to auto-generate from README
        readme = _find_readme(target_dir)
        if readme:
            instructions = readme.read_text(encoding="utf-8", errors="replace")[:4000]
        else:
            instructions = f"Skill imported from {git_url}"

        _create_skill_md(
            target_dir,
            name=name,
            description=f"Imported from {git_url}",
            instructions=instructions,
            source=git_url,
        )
        logger.info("Auto-generated SKILL.md for '{}'", name)

    # Check for Python tool modules
    tool_files = list(target_dir.glob("tools.py")) + list(target_dir.glob("*_tools.py"))
    if tool_files:
        logger.info("Found tool modules in '{}': {}", name, [f.name for f in tool_files])

    logger.info("Installed skill '{}' from {}", name, git_url)
    return (
        f"Skill '{name}' installed at {target_dir}. "
        f"It will be available in the next agent loop turn. "
        f"Found: SKILL.md={'yes' if skill_file.is_file() else 'auto-generated'}, "
        f"tool_modules={[f.name for f in tool_files]}"
    )


@tool_definition(
    name="install_skill_from_url",
    description=(
        "Install a skill from a web URL. Fetches the content, extracts "
        "instructions, and creates a skill folder with a SKILL.md file."
    ),
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "URL to fetch skill content from (e.g., ClawHub page, GitHub raw file).",
            },
            "skill_name": {
                "type": "string",
                "description": "Name for the skill.",
            },
        },
        "required": ["url", "skill_name"],
    },
    requires_confirmation=True,
)
def install_skill_from_url(url: str, skill_name: str) -> str:
    """Fetch content from a URL and create a skill from it."""
    import requests

    name = _sanitize_name(skill_name)
    target_dir = SKILLS_DIR / name

    if target_dir.exists():
        return f"Skill '{name}' already exists. Uninstall first."

    try:
        resp = requests.get(url, timeout=30, headers={"User-Agent": "Aradhya/1.0"})
        resp.raise_for_status()
        content = resp.text[:8000]
    except Exception as error:
        return f"Failed to fetch URL: {error}"

    # Strip HTML if it looks like a web page
    if "<html" in content.lower() or "<body" in content.lower():
        content = re.sub(r"<[^>]+>", "", content)
        content = re.sub(r"\s+", " ", content).strip()

    target_dir.mkdir(parents=True, exist_ok=True)
    _create_skill_md(
        target_dir,
        name=name,
        description=f"Imported from {url}",
        instructions=content,
        source=url,
    )

    logger.info("Installed skill '{}' from URL {}", name, url)
    return f"Skill '{name}' created at {target_dir} with content from {url}."


@tool_definition(
    name="install_skill_from_code",
    description=(
        "Create a skill directly from provided code or instruction text. "
        "Use this when the user pastes code, a prompt, or instructions that "
        "should become a new Aradhya capability."
    ),
    parameters={
        "type": "object",
        "properties": {
            "skill_name": {
                "type": "string",
                "description": "Name for the new skill.",
            },
            "description": {
                "type": "string",
                "description": "Short description of what the skill does.",
            },
            "instructions": {
                "type": "string",
                "description": (
                    "The skill instructions (Markdown) that will be injected "
                    "into the agent's system prompt when this skill is active."
                ),
            },
            "python_code": {
                "type": "string",
                "description": (
                    "Optional Python code that defines @tool_definition functions. "
                    "If provided, saved as tools.py in the skill directory and "
                    "dynamically loaded as agent tools."
                ),
            },
        },
        "required": ["skill_name", "description", "instructions"],
    },
    requires_confirmation=True,
)
def install_skill_from_code(
    skill_name: str,
    description: str,
    instructions: str,
    python_code: str = "",
) -> str:
    """Create a skill from provided text or code."""
    name = _sanitize_name(skill_name)
    target_dir = SKILLS_DIR / name

    if target_dir.exists():
        return f"Skill '{name}' already exists. Uninstall first."

    target_dir.mkdir(parents=True, exist_ok=True)

    tool_module = None
    if python_code.strip():
        tools_file = target_dir / "tools.py"
        tools_file.write_text(python_code, encoding="utf-8")
        tool_module = "tools.py"
        logger.info("Saved tool module for skill '{}'", name)

    _create_skill_md(
        target_dir,
        name=name,
        description=description,
        instructions=instructions,
        tool_module=tool_module,
        source="user-provided",
    )

    logger.info("Created skill '{}' from provided code/instructions", name)
    parts = [f"Skill '{name}' created at {target_dir}."]
    if tool_module:
        parts.append(f"Tool module '{tool_module}' saved — its tools will be loaded on next restart.")
    return " ".join(parts)


@tool_definition(
    name="uninstall_skill",
    description="Remove an installed skill by name.",
    parameters={
        "type": "object",
        "properties": {
            "skill_name": {
                "type": "string",
                "description": "Name of the skill to uninstall.",
            },
        },
        "required": ["skill_name"],
    },
    requires_confirmation=True,
)
def uninstall_skill(skill_name: str) -> str:
    """Remove a skill directory from ~/.aradhya/skills/."""
    name = _sanitize_name(skill_name)
    target_dir = SKILLS_DIR / name

    if not target_dir.exists():
        return f"Skill '{name}' not found at {target_dir}."

    try:
        shutil.rmtree(target_dir)
        # Remove from trusted list
        trusted = _load_trusted()
        trusted.discard(name)
        _save_trusted(trusted)
        logger.info("Uninstalled skill '{}'", name)
        return f"Skill '{name}' uninstalled."
    except Exception as error:
        return f"Error uninstalling skill: {error}"


@tool_definition(
    name="trust_skill",
    description=(
        "Mark an external skill as trusted, allowing its Python tool modules "
        "to be loaded and executed. Required before code-based skills can run."
    ),
    parameters={
        "type": "object",
        "properties": {
            "skill_name": {
                "type": "string",
                "description": "Name of the skill to trust.",
            },
        },
        "required": ["skill_name"],
    },
    requires_confirmation=True,
)
def trust_skill(skill_name: str) -> str:
    """Add a skill to the trusted list."""
    name = _sanitize_name(skill_name)
    target_dir = SKILLS_DIR / name

    if not target_dir.exists():
        return f"Skill '{name}' not found."

    trusted = _load_trusted()
    trusted.add(name)
    _save_trusted(trusted)
    logger.info("Trusted skill '{}'", name)
    return f"Skill '{name}' is now trusted. Its tool modules will be loaded."


def _find_readme(directory: Path) -> Path | None:
    """Find a README file in a directory."""
    for name in ("README.md", "readme.md", "README.txt", "README"):
        candidate = directory / name
        if candidate.is_file():
            return candidate
    return None


ALL_SKILL_INSTALLER_TOOLS = [
    install_skill_from_git,
    install_skill_from_url,
    install_skill_from_code,
    uninstall_skill,
    trust_skill,
]
