"""Unit tests for the intent-based dynamic skill loader."""

from __future__ import annotations

from pathlib import Path


from src.aradhya.skills.skill_loader import load_skills_for_intent
from src.aradhya.skills.skill_models import SkillDefinition, SkillRegistry, SkillRequirements


def _make_skill(name: str, intents: list[str], enabled: bool = True) -> SkillDefinition:
    return SkillDefinition(
        name=name,
        description=f"Skill: {name}",
        instructions="Do the thing.",
        base_dir=Path(f"/fake/{name}"),
        enabled=enabled,
        requires=SkillRequirements(bins=(), env=(), python_packages=()),
        intents=tuple(intents),
        metadata={},
        tool_module=None,
    )


def _make_registry(*skills: SkillDefinition) -> SkillRegistry:
    reg = SkillRegistry()
    for s in skills:
        reg.register(s)
    return reg


class TestLoadSkillsForIntent:
    def test_returns_all_when_few_skills(self, tmp_path: Path) -> None:
        """If there are ≤ max_skills, return everything regardless of prompt."""
        from unittest.mock import patch

        skill_a = _make_skill("git", ["git", "commit", "branch"])
        skill_b = _make_skill("voice", ["voice", "speak"])
        full_reg = _make_registry(skill_a, skill_b)

        with patch(
            "src.aradhya.skills.skill_loader.load_skills",
            return_value=full_reg,
        ):
            result = load_skills_for_intent(tmp_path, "do something random", max_skills=5)

        assert len(result.all_skills()) == 2

    def test_filters_by_matching_intent(self, tmp_path: Path) -> None:
        """Skills whose intents appear in the prompt should be selected."""
        from unittest.mock import patch

        skills = [
            _make_skill("git", ["git", "commit", "branch"]),
            _make_skill("voice", ["voice", "speak", "microphone"]),
            _make_skill("browser", ["web", "browse", "url"]),
            _make_skill("shell", ["terminal", "command", "shell"]),
            _make_skill("search", ["search", "find", "grep"]),
            _make_skill("schedule", ["schedule", "cron", "timer"]),
        ]
        full_reg = _make_registry(*skills)

        with patch(
            "src.aradhya.skills.skill_loader.load_skills",
            return_value=full_reg,
        ):
            result = load_skills_for_intent(
                tmp_path,
                "can you commit my changes to git and search for bugs?",
                max_skills=3,
            )

        names = {s.name for s in result.all_skills()}
        assert "git" in names
        assert "search" in names

    def test_fallback_when_no_intent_match(self, tmp_path: Path) -> None:
        """If no skill matches the prompt, return top max_skills by name."""
        from unittest.mock import patch

        skills = [
            _make_skill("alpha", ["alpha_only_keyword"]),
            _make_skill("beta", ["beta_only_keyword"]),
            _make_skill("gamma", ["gamma_only_keyword"]),
            _make_skill("delta", ["delta_only_keyword"]),
            _make_skill("epsilon", ["epsilon_only_keyword"]),
            _make_skill("zeta", ["zeta_only_keyword"]),
        ]
        full_reg = _make_registry(*skills)

        with patch(
            "src.aradhya.skills.skill_loader.load_skills",
            return_value=full_reg,
        ):
            result = load_skills_for_intent(
                tmp_path,
                "completely unrelated topic",
                max_skills=3,
            )

        assert len(result.all_skills()) == 3

    def test_general_skills_always_included(self, tmp_path: Path) -> None:
        """Skills with no intents declared are always included (general-purpose)."""
        from unittest.mock import patch

        skills = [
            _make_skill("general", []),  # no intents → always included
            _make_skill("very-specific", ["blockchain", "nft", "web3"]),
            _make_skill("another-specific", ["machine_learning", "pytorch"]),
            _make_skill("more-specific", ["kubernetes", "docker", "k8s"]),
            _make_skill("even-more", ["typescript", "react", "frontend"]),
            _make_skill("last", ["golang", "goroutine"]),
        ]
        full_reg = _make_registry(*skills)

        with patch(
            "src.aradhya.skills.skill_loader.load_skills",
            return_value=full_reg,
        ):
            result = load_skills_for_intent(
                tmp_path,
                "just do something simple",
                max_skills=3,
            )

        names = {s.name for s in result.all_skills()}
        assert "general" in names

    def test_disabled_skills_excluded(self, tmp_path: Path) -> None:
        """Disabled skills should never appear in the result."""
        from unittest.mock import patch

        skills = [
            _make_skill("active", ["active", "task"]),
            _make_skill("disabled_skill", ["active", "task"], enabled=False),
        ]
        full_reg = _make_registry(*skills)

        with patch(
            "src.aradhya.skills.skill_loader.load_skills",
            return_value=full_reg,
        ):
            result = load_skills_for_intent(
                tmp_path,
                "do an active task",
                max_skills=5,
            )

        names = {s.name for s in result.all_skills()}
        assert "disabled_skill" not in names

    def test_empty_prompt_returns_all(self, tmp_path: Path) -> None:
        """Empty prompt should return all skills (no filtering)."""
        from unittest.mock import patch

        skills = [_make_skill(f"skill_{i}", [f"kw{i}"]) for i in range(6)]
        full_reg = _make_registry(*skills)

        with patch(
            "src.aradhya.skills.skill_loader.load_skills",
            return_value=full_reg,
        ):
            result = load_skills_for_intent(tmp_path, "", max_skills=3)

        # Empty prompt → return full registry
        assert len(result.all_skills()) == 6
