from __future__ import annotations

from pathlib import Path

from src.aradhya.parasite.pipeline import DigestionPipeline
from src.aradhya.skills.skill_loader import load_skills


def test_generated_skill_loads_and_deduplicates_intents(tmp_path: Path, monkeypatch):
    user_skills = tmp_path / "user_skills"
    user_skills.mkdir()
    monkeypatch.setattr("src.aradhya.skills.skill_loader.skills_dir", lambda: user_skills)
    target = tmp_path / "Hosts" / "Agentless"
    target.mkdir(parents=True)

    pipeline = DigestionPipeline(tmp_path)
    generated = pipeline._generate_skill_file(
        "Agentless",
        target,
        ["agent_framework", "agent_framework", "api_client"],
        {
            "description": '<p align="center"><a href="https://example.com">"Agentless"</a></p>',
            "type": "python",
            "dependencies": ["requests", "requests", "loguru"],
        },
    )

    assert len(generated) == 1
    registry = load_skills(tmp_path)
    skill = registry.get("host-agentless")

    assert skill is not None
    assert '"' not in skill.description
    assert len(skill.intents) == len(set(skill.intents))
    assert "how does Agentless work" in skill.intents
