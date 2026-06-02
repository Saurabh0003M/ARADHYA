"""Loader that discovers and parses SKILL.md files into a SkillRegistry.

Skill directories are scanned in precedence order:
1. ``core/skills/`` — bundled skills shipped with Aradhya
2. ``~/.aradhya/skills/`` — user-installed global skills
3. Any extra directories from configuration

Each skill folder must contain a ``SKILL.md`` file.  The file uses YAML
frontmatter (delimited by ``---``) followed by Markdown instructions.
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Any

from loguru import logger

from src.aradhya.paths import skills_dir
from src.aradhya.skills.skill_models import (
    SkillDefinition,
    SkillRegistry,
    SkillRequirements,
)

SKILL_FILENAME = "SKILL.md"
_FRONTMATTER_RE = re.compile(
    r"\A\s*---\s*\n(.*?)\n---\s*\n(.*)",
    re.DOTALL,
)


def load_skills(
    project_root: Path,
    extra_dirs: list[Path] | None = None,
) -> SkillRegistry:
    """Scan standard skill directories and return a populated SkillRegistry."""

    registry = SkillRegistry()
    search_dirs = _build_search_dirs(project_root, extra_dirs)

    for search_dir in search_dirs:
        if not search_dir.is_dir():
            logger.debug("Skill directory does not exist: {}", search_dir)
            continue

        for candidate in sorted(search_dir.iterdir()):
            if not candidate.is_dir():
                continue

            skill_file = candidate / SKILL_FILENAME
            if not skill_file.is_file():
                continue

            try:
                skill = _parse_skill_file(skill_file, candidate)
            except Exception as error:
                logger.warning("Failed to parse skill at {}: {}", candidate, error)
                continue

            if not _check_requirements(skill):
                logger.info(
                    "Skill '{}' is disabled because requirements are not met",
                    skill.name,
                )
                skill.enabled = False

            if registry.get(skill.name) is not None:
                logger.debug(
                    "Skill '{}' already loaded; skipping duplicate at {}",
                    skill.name,
                    candidate,
                )
                continue

            registry.register(skill)
            logger.info(
                "Loaded skill '{}' from {} (enabled={})",
                skill.name,
                candidate,
                skill.enabled,
            )

    return registry


def load_skills_for_intent(
    project_root: Path,
    user_prompt: str,
    *,
    extra_dirs: list[Path] | None = None,
    max_skills: int = 5,
) -> SkillRegistry:
    """Load all skills then return only those matching the user's intent.

    Implements Codex-style dynamic plugin loading: instead of injecting every
    skill into the system prompt (which wastes tokens and dilutes focus),
    this function matches the first prompt against each skill's ``intents``
    list and returns only the top-N most relevant skills.

    Matching is keyword-based: for each skill, we count how many of its
    intent phrases appear as substrings of the (lowercase) user prompt.
    Skills with zero matches are excluded unless the registry has fewer
    than ``max_skills`` candidates.

    Args:
        project_root: Root of the ARADHYA project.
        user_prompt: The first message from the user in the session.
        extra_dirs: Optional additional skill directories to scan.
        max_skills: Maximum number of skills to inject into context.

    Returns:
        A ``SkillRegistry`` containing only the matched/selected skills.
    """
    full_registry = load_skills(project_root, extra_dirs)
    all_skills = [s for s in full_registry.all_skills() if s.enabled]

    if not user_prompt or len(all_skills) <= max_skills:
        # No intent filtering needed — return only enabled skills
        if len(all_skills) == len(full_registry.all_skills()):
            return full_registry
        filtered = SkillRegistry()
        for skill in all_skills:
            filtered.register(skill)
        return filtered

    prompt_lower = user_prompt.lower()

    scored: list[tuple[int, "SkillDefinition"]] = []  # type: ignore[name-defined]  # noqa: F821
    for skill in all_skills:
        if not skill.enabled:
            continue
        score = 0
        for intent in skill.intents:
            if intent.lower() in prompt_lower:
                score += 1
        # Always include skills with no intents declared (general-purpose)
        if not skill.intents:
            score = 1
        scored.append((score, skill))

    # Sort by score descending, then by name for determinism
    scored.sort(key=lambda x: (-x[0], x[1].name))

    # Take top-N, always including at least skills that matched
    selected = [skill for score, skill in scored if score > 0][:max_skills]
    if not selected:
        # Fallback: return the top max_skills by name if nothing matched
        selected = [skill for _, skill in scored[:max_skills]]

    filtered = SkillRegistry()
    for skill in selected:
        filtered.register(skill)
        logger.info(
            "Intent-based loader: injecting skill '{}' for prompt",
            skill.name,
        )

    return filtered


def _build_search_dirs(
    project_root: Path,
    extra_dirs: list[Path] | None,
) -> list[Path]:
    """Return the ordered list of directories to scan for skills."""

    dirs: list[Path] = [
        project_root / "core" / "skills",
        skills_dir(),
    ]
    if extra_dirs:
        dirs.extend(extra_dirs)
    return dirs


def _parse_skill_file(
    skill_file: Path,
    base_dir: Path,
) -> SkillDefinition:
    """Parse a SKILL.md file into a SkillDefinition."""

    raw = skill_file.read_text(encoding="utf-8")
    frontmatter, instructions = _split_frontmatter(raw)

    return _parse_frontmatter(frontmatter, instructions.strip(), base_dir)


def _parse_frontmatter(
    frontmatter: dict[str, Any],
    instructions: str,
    base_dir: Path,
) -> SkillDefinition:
    """Convert raw frontmatter dict and body into a SkillDefinition."""

    name = frontmatter.get("name") or base_dir.name
    description = frontmatter.get("description", "")
    enabled = frontmatter.get("enabled", True)
    raw_requires = frontmatter.get("requires", {})
    raw_intents = frontmatter.get("intents", [])
    metadata = frontmatter.get("metadata", {})

    requirements = SkillRequirements(
        bins=tuple(raw_requires.get("bins", [])),
        env=tuple(raw_requires.get("env", [])),
        python_packages=tuple(raw_requires.get("python_packages", [])),
    )

    tool_module_raw = frontmatter.get("tool_module", None)
    tool_module = str(tool_module_raw) if tool_module_raw else None

    return SkillDefinition(
        name=str(name),
        description=str(description),
        instructions=instructions,
        base_dir=base_dir,
        enabled=bool(enabled),
        requires=requirements,
        intents=tuple(str(i) for i in raw_intents),
        metadata=metadata if isinstance(metadata, dict) else {},
        tool_module=tool_module,
    )


def _split_frontmatter(raw: str) -> tuple[dict[str, Any], str]:
    """Split a SKILL.md file into YAML frontmatter dict and Markdown body.

    Uses a lightweight YAML-subset parser to avoid adding PyYAML as a
    hard dependency.  Supports simple ``key: value`` pairs and lists
    with ``- item`` notation at one nesting level.
    """

    match = _FRONTMATTER_RE.match(raw)
    if not match:
        return {}, raw

    frontmatter_text = match.group(1)
    body = match.group(2)
    return _parse_simple_yaml(frontmatter_text), body


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    """Parse a minimal YAML subset with up to 2 levels of nesting.

    Supports:
    - Top-level ``key: scalar``
    - Top-level ``key:`` followed by ``  - list_item``
    - Top-level ``key:`` followed by ``  sub_key: scalar``
    - Top-level ``key:`` followed by ``  sub_key:`` and ``    - list_item``

    This avoids pulling in PyYAML for a small frontmatter block.
    """

    result: dict[str, Any] = {}
    l0_key: str | None = None  # current top-level key
    l0_list: list[str] | None = None  # list collecting for l0_key
    l0_dict: dict[str, Any] | None = None  # dict collecting for l0_key
    l1_key: str | None = None  # current sub-key inside l0_dict
    l1_list: list[str] | None = None  # list collecting for l1_key

    def _flush_l1() -> None:
        """Flush any pending l1 list into the l0 dict."""
        nonlocal l1_key, l1_list
        if l1_list is not None and l1_key is not None and l0_dict is not None:
            l0_dict[l1_key] = l1_list
        l1_key = None
        l1_list = None

    def _flush_l0() -> None:
        """Flush any pending l0 collection into result."""
        nonlocal l0_key, l0_list, l0_dict
        _flush_l1()
        if l0_key is not None:
            if l0_dict is not None:
                result[l0_key] = l0_dict
            elif l0_list is not None:
                result[l0_key] = l0_list
        l0_key = None
        l0_list = None
        l0_dict = None

    def _parse_scalar(val: str) -> Any:
        val = val.strip().strip("\"'")
        if val.lower() == "true":
            return True
        if val.lower() == "false":
            return False
        try:
            return int(val)
        except ValueError:
            pass
        try:
            return float(val)
        except ValueError:
            pass
        return val

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        indent = len(line) - len(line.lstrip())

        # 4-space (or 3+) indent: list item under a sub-key
        if indent >= 4 and stripped.startswith("- ") and l1_key is not None:
            value = stripped[2:].strip().strip("\"'")
            if l1_list is not None:
                l1_list.append(value)
            continue

        # 2-space indent: sub-key or list item under a top-level key
        if indent >= 2 and indent < 4:
            if stripped.startswith("- ") and l0_key is not None:
                # List item directly under the top-level key
                _flush_l1()
                value = stripped[2:].strip().strip("\"'")
                if l0_list is not None:
                    l0_list.append(value)
                continue

            if ":" in stripped and l0_key is not None:
                # Sub-key under the top-level key
                _flush_l1()
                if l0_dict is None:
                    l0_dict = {}
                sub_key, _, sub_val = stripped.partition(":")
                sub_val = sub_val.strip()
                l1_key = sub_key.strip()
                if not sub_val:
                    # Sub-key with no value → expect list items below
                    l1_list = []
                else:
                    l0_dict[l1_key] = _parse_scalar(sub_val)
                    l1_key = None
                continue

        # Top-level key: value (no indent)
        if indent == 0 and ":" in stripped:
            _flush_l0()
            key, _, value = stripped.partition(":")
            l0_key = key.strip()
            value = value.strip()

            if not value:
                l0_list = []
                continue

            result[l0_key] = _parse_scalar(value)
            l0_key = None
            continue

    _flush_l0()
    return result


def _check_requirements(skill: SkillDefinition) -> bool:
    """Return True if all of a skill's gating requirements are satisfied."""

    for binary in skill.requires.bins:
        if shutil.which(binary) is None:
            logger.debug(
                "Skill '{}' requires binary '{}' which is not on PATH",
                skill.name,
                binary,
            )
            return False

    for env_var in skill.requires.env:
        if not os.environ.get(env_var):
            logger.debug(
                "Skill '{}' requires env var '{}' which is not set",
                skill.name,
                env_var,
            )
            return False

    for package in skill.requires.python_packages:
        try:
            __import__(package.replace("-", "_"))
        except ImportError:
            logger.debug(
                "Skill '{}' requires Python package '{}' which is not installed",
                skill.name,
                package,
            )
            return False

    return True
