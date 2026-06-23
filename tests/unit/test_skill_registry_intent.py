"""P0-3: SkillRegistry.select_for_prompt / instructions_for_prompt inject only
the skills relevant to the current request, capped at max_skills, instead of
dumping every active skill into the agent prompt."""

from __future__ import annotations

from pathlib import Path

from src.aradhya.skills.skill_models import SkillDefinition, SkillRegistry


def _skill(name: str, *intents: str, enabled: bool = True) -> SkillDefinition:
    return SkillDefinition(
        name=name,
        description=f"{name} description",
        instructions=f"Instructions for {name}",
        base_dir=Path("."),
        enabled=enabled,
        intents=tuple(intents),
    )


def _registry(*skills: SkillDefinition) -> SkillRegistry:
    registry = SkillRegistry()
    for skill in skills:
        registry.register(skill)
    return registry


def test_few_skills_returns_all_regardless_of_prompt():
    registry = _registry(_skill("a", "FOO"), _skill("b", "BAR"))

    selected = registry.select_for_prompt("totally unrelated request", max_skills=5)

    assert {s.name for s in selected} == {"a", "b"}


def test_intent_match_selected_over_non_match_when_over_cap():
    # 6 skills, cap 2: only the intent-matching skills should win.
    registry = _registry(
        _skill("jobs", "FIND_JOBS"),
        _skill("disk", "DISK_CLEANUP"),
        _skill("c", "NOPE_C"),
        _skill("d", "NOPE_D"),
        _skill("e", "NOPE_E"),
        _skill("f", "NOPE_F"),
    )

    selected = registry.select_for_prompt("please find_jobs for me", max_skills=2)

    assert [s.name for s in selected] == ["jobs"]


def test_general_purpose_skills_always_candidates():
    # A skill with no declared intents is general-purpose and stays a candidate
    # even when other skills match the prompt, under the cap.
    registry = _registry(
        _skill("general"),  # no intents
        _skill("jobs", "FIND_JOBS"),
        _skill("c", "NOPE_C"),
        _skill("d", "NOPE_D"),
        _skill("e", "NOPE_E"),
        _skill("f", "NOPE_F"),
    )

    selected = registry.select_for_prompt("find_jobs now", max_skills=3)
    names = {s.name for s in selected}

    assert "jobs" in names
    assert "general" in names
    assert len(selected) <= 3


def test_disabled_skills_excluded():
    registry = _registry(
        _skill("on", "FIND_JOBS"),
        _skill("off", "FIND_JOBS", enabled=False),
    )

    selected = registry.select_for_prompt("find_jobs", max_skills=5)

    assert [s.name for s in selected] == ["on"]


def test_instructions_for_prompt_only_includes_selected():
    registry = _registry(
        _skill("jobs", "FIND_JOBS"),
        _skill("disk", "DISK_CLEANUP"),
        _skill("c", "NOPE_C"),
        _skill("d", "NOPE_D"),
        _skill("e", "NOPE_E"),
        _skill("f", "NOPE_F"),
    )

    block = registry.instructions_for_prompt("find_jobs please", max_skills=1)

    assert "Instructions for jobs" in block
    assert "Instructions for disk" not in block
