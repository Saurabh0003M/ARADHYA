"""Data models for the Aradhya skills system.

Skills are modular capability units loaded from disk. Each skill is a folder
containing a SKILL.md file with YAML frontmatter and Markdown instructions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SkillRequirements:
    """Gating requirements that must be satisfied for a skill to load."""

    bins: tuple[str, ...] = ()
    env: tuple[str, ...] = ()
    python_packages: tuple[str, ...] = ()


@dataclass
class SkillDefinition:
    """A single loaded skill definition parsed from a SKILL.md file.

    If ``tool_module`` is set (e.g. ``"tools.py"``), the loader will
    attempt to dynamically import that Python file from the skill's
    ``base_dir`` and register any ``@tool_definition`` functions it finds
    into the agent's ``ToolRegistry``.  The skill must be in the trusted
    list (``~/.aradhya/trusted_skills.json``) for code execution.
    """

    name: str
    description: str
    instructions: str
    base_dir: Path
    enabled: bool = True
    requires: SkillRequirements = field(default_factory=SkillRequirements)
    intents: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    tool_module: str | None = None

    @property
    def skill_file(self) -> Path:
        return self.base_dir / "SKILL.md"


class SkillRegistry:
    """In-memory registry of loaded skills with enable/disable support."""

    def __init__(self) -> None:
        self._skills: dict[str, SkillDefinition] = {}

    def register(self, skill: SkillDefinition) -> None:
        """Register a loaded skill definition."""
        self._skills[skill.name] = skill

    def get(self, name: str) -> SkillDefinition | None:
        """Return a skill by name, or None if not found."""
        return self._skills.get(name)

    def enable(self, name: str) -> bool:
        """Enable a skill by name. Returns True if found and enabled."""
        skill = self._skills.get(name)
        if skill is None:
            return False
        skill.enabled = True
        return True

    def disable(self, name: str) -> bool:
        """Disable a skill by name. Returns True if found and disabled."""
        skill = self._skills.get(name)
        if skill is None:
            return False
        skill.enabled = False
        return True

    def active_skills(self) -> list[SkillDefinition]:
        """Return all currently enabled skills."""
        return [s for s in self._skills.values() if s.enabled]

    def all_skills(self) -> list[SkillDefinition]:
        """Return all registered skills regardless of enabled state."""
        return list(self._skills.values())

    def active_instructions(self) -> str:
        """Combine instructions from all active skills into a single prompt block."""
        parts: list[str] = []
        for skill in self.active_skills():
            if skill.instructions.strip():
                parts.append(
                    f"## Skill: {skill.name}\n"
                    f"{skill.description}\n\n"
                    f"{skill.instructions}"
                )
        return "\n\n---\n\n".join(parts)

    def select_for_prompt(
        self, user_prompt: str, max_skills: int = 5
    ) -> list[SkillDefinition]:
        """Return up to ``max_skills`` active skills most relevant to the prompt.

        Mirrors the intent matching in ``skill_loader.load_skills_for_intent``
        but operates on the already-loaded registry, so it is cheap enough to
        run on every agent turn (no disk rescans or requirement re-checks).
        Skills that declare no ``intents`` are treated as general-purpose and
        are always candidates.
        """
        active = self.active_skills()
        if not user_prompt or len(active) <= max_skills:
            return active

        prompt_lower = user_prompt.lower()
        scored: list[tuple[int, SkillDefinition]] = []
        for skill in active:
            if skill.intents:
                score = sum(
                    1 for intent in skill.intents if intent.lower() in prompt_lower
                )
            else:
                score = 1  # general-purpose skills are always candidates
            scored.append((score, skill))

        # Highest score first, then name for deterministic ties.
        scored.sort(key=lambda pair: (-pair[0], pair[1].name))
        selected = [skill for score, skill in scored if score > 0][:max_skills]
        if not selected:
            selected = [skill for _, skill in scored[:max_skills]]
        return selected

    def instructions_for_prompt(self, user_prompt: str, max_skills: int = 5) -> str:
        """Combine instructions from the skills most relevant to ``user_prompt``.

        Intent-filtered counterpart to :meth:`active_instructions` — injects
        only the top matching skills so the agent prompt stays focused.
        """
        parts: list[str] = []
        for skill in self.select_for_prompt(user_prompt, max_skills):
            if skill.instructions.strip():
                parts.append(
                    f"## Skill: {skill.name}\n"
                    f"{skill.description}\n\n"
                    f"{skill.instructions}"
                )
        return "\n\n---\n\n".join(parts)

    def active_intents(self) -> set[str]:
        """Return the union of all intents declared by active skills."""
        intents: set[str] = set()
        for skill in self.active_skills():
            intents.update(skill.intents)
        return intents

    @property
    def count(self) -> int:
        return len(self._skills)

    @property
    def active_count(self) -> int:
        return len(self.active_skills())
