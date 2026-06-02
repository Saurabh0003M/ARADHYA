from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.aradhya.parasite.deduplicator import SkillDeduplicator


@dataclass
class FakeResult:
    text: str


class FakeProvider:
    def generate(self, *_args, **_kwargs):
        return FakeResult("MERGE")


class FakeAudit:
    def __init__(self) -> None:
        self.events = []

    def log_event(self, event_type, payload=None):
        self.events.append((event_type, payload or {}))


def _write_skill(
    root: Path,
    folder: str,
    *,
    name: str,
    description: str,
    intents: list[str],
) -> Path:
    skill_dir = root / "core" / "skills" / folder
    skill_dir.mkdir(parents=True)
    skill_dir.joinpath("SKILL.md").write_text(
        "---\n"
        f"name: {name}\n"
        f"description: {description}\n"
        "intents:\n" + "\n".join(f"  - {intent}" for intent in intents) + "\n"
        "---\n\n"
        f"# {name}\n",
        encoding="utf-8",
    )
    return skill_dir


def test_dedup_dry_run_returns_plan_without_deleting(tmp_path: Path, monkeypatch):
    user_skills = tmp_path / "user_skills"
    user_skills.mkdir()
    monkeypatch.setattr("src.aradhya.skills.skill_loader.skills_dir", lambda: user_skills)
    _write_skill(
        tmp_path,
        "native-agent",
        name="native-agent",
        description="agent design pattern orchestration workflow",
        intents=["agent design pattern"],
    )
    host_dir = _write_skill(
        tmp_path,
        "host-demo",
        name="host-demo",
        description="agent design pattern orchestration workflow",
        intents=["agent design pattern", "orchestration workflow"],
    )

    actions = SkillDeduplicator(
        tmp_path,
        provider=FakeProvider(),
    ).run_deduplication()

    assert actions
    assert actions[0]["status"] == "planned"
    assert host_dir.exists()


def test_dedup_live_requires_confirmation_gate(tmp_path: Path, monkeypatch):
    user_skills = tmp_path / "user_skills"
    user_skills.mkdir()
    monkeypatch.setattr("src.aradhya.skills.skill_loader.skills_dir", lambda: user_skills)
    _write_skill(
        tmp_path,
        "native-agent",
        name="native-agent",
        description="agent design pattern orchestration workflow",
        intents=["agent design pattern"],
    )
    host_dir = _write_skill(
        tmp_path,
        "host-demo",
        name="host-demo",
        description="agent design pattern orchestration workflow",
        intents=["agent design pattern", "orchestration workflow"],
    )

    actions = SkillDeduplicator(
        tmp_path,
        provider=FakeProvider(),
    ).run_deduplication(dry_run=False)

    assert actions[0]["status"] == "denied"
    assert host_dir.exists()


def test_dedup_live_merge_updates_base_and_deletes_duplicate(tmp_path: Path, monkeypatch):
    user_skills = tmp_path / "user_skills"
    user_skills.mkdir()
    monkeypatch.setattr("src.aradhya.skills.skill_loader.skills_dir", lambda: user_skills)
    base_dir = _write_skill(
        tmp_path,
        "native-agent",
        name="native-agent",
        description="agent design pattern orchestration workflow",
        intents=["agent design pattern"],
    )
    host_dir = _write_skill(
        tmp_path,
        "host-demo",
        name="host-demo",
        description="agent design pattern orchestration workflow",
        intents=["agent design pattern", "orchestration workflow"],
    )
    audit = FakeAudit()

    actions = SkillDeduplicator(
        tmp_path,
        provider=FakeProvider(),
        confirmation_gate=lambda _tool, _args: (True, False),
        audit_logger=audit,
    ).run_deduplication(dry_run=False)

    content = base_dir.joinpath("SKILL.md").read_text(encoding="utf-8")
    assert actions[0]["status"] == "merged"
    assert "orchestration workflow" in content
    assert not host_dir.exists()
    assert audit.events[0][0] == "parasite_dedup_merge"
