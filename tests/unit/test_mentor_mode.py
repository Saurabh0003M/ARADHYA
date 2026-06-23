"""P1-7: mentor do/teach mode.

The same task must produce different agent instructions in do vs teach mode,
and the mode is settable/validated and toggle-able via /mentor."""

from __future__ import annotations

from datetime import datetime

import pytest

from src.aradhya import main
from src.aradhya.assistant_core import AradhyaAssistant
from src.aradhya.assistant_models import (
    AssistantPreferences,
    DirectoryIndexPolicy,
)


def build_test_preferences(tmp_path):
    return AssistantPreferences(
        user_roots=(tmp_path,),
        directory_index_path=tmp_path / "directory-index.txt",
        context_cache_dir=tmp_path / "context-cache",
        confirmation_phrases=("yes proceed",),
        security_blog_urls=("https://example.com/security",),
        project_markers=("pyproject.toml",),
        game_library_roots=tuple(),
        allow_live_execution=False,
        directory_index_policy=DirectoryIndexPolicy(max_nodes=1000),
    )


def build_assistant(tmp_path) -> AradhyaAssistant:
    return AradhyaAssistant(
        build_test_preferences(tmp_path),
        model_provider=None,
        now_provider=lambda: datetime(2026, 6, 19, 10, 0, 0),
    )


# ── set_mentor_mode ────────────────────────────────────────────────────

def test_default_mode_is_do(tmp_path):
    assistant = build_assistant(tmp_path)
    assert assistant.state.mentor_mode == "do"


def test_set_teach_mode(tmp_path):
    assistant = build_assistant(tmp_path)
    message = assistant.set_mentor_mode("teach")
    assert assistant.state.mentor_mode == "teach"
    assert "teach" in message.lower()


def test_set_mode_with_skill_level(tmp_path):
    assistant = build_assistant(tmp_path)
    assistant.set_mentor_mode("teach", "Beginner")
    assert assistant.state.skill_level == "beginner"


def test_set_mode_normalizes_case(tmp_path):
    assistant = build_assistant(tmp_path)
    assistant.set_mentor_mode("TEACH")
    assert assistant.state.mentor_mode == "teach"


def test_invalid_mode_raises(tmp_path):
    assistant = build_assistant(tmp_path)
    with pytest.raises(ValueError):
        assistant.set_mentor_mode("bogus")


# ── prompt variants (the behavioural core) ─────────────────────────────

def test_mentor_block_differs_between_modes(tmp_path):
    assistant = build_assistant(tmp_path)

    assistant.set_mentor_mode("do")
    do_block = assistant._mentor_mode_block()
    assistant.set_mentor_mode("teach")
    teach_block = assistant._mentor_mode_block()

    assert "DO" in do_block
    assert "TEACH" in teach_block
    assert do_block != teach_block
    # teach mode must forbid acting for the user
    assert "do not perform actions" in teach_block.lower()


def test_skill_level_appears_in_block(tmp_path):
    assistant = build_assistant(tmp_path)
    assistant.set_mentor_mode("teach", "beginner")
    assert "beginner" in assistant._mentor_mode_block().lower()


def test_system_prompt_reflects_mode(tmp_path):
    assistant = build_assistant(tmp_path)

    assistant.set_mentor_mode("do")
    do_prompt = assistant._build_agent_system_prompt(None)
    assistant.set_mentor_mode("teach")
    teach_prompt = assistant._build_agent_system_prompt(None)

    assert "Mentor mode: DO" in do_prompt
    assert "Mentor mode: TEACH" in teach_prompt
    assert do_prompt != teach_prompt


# ── /mentor command handler ────────────────────────────────────────────

def test_mentor_command_sets_mode(tmp_path, monkeypatch):
    assistant = build_assistant(tmp_path)
    messages: list[str] = []
    monkeypatch.setattr(main, "render_info", lambda msg: messages.append(msg))

    main._handle_mentor(assistant=assistant, command="/mentor teach beginner")

    assert assistant.state.mentor_mode == "teach"
    assert assistant.state.skill_level == "beginner"
    assert messages


def test_mentor_command_reports_current_when_no_arg(tmp_path, monkeypatch):
    assistant = build_assistant(tmp_path)
    messages: list[str] = []
    monkeypatch.setattr(main, "render_info", lambda msg: messages.append(msg))

    main._handle_mentor(assistant=assistant, command="/mentor")

    assert messages and "do" in messages[0].lower()


def test_mentor_command_rejects_bad_mode(tmp_path, monkeypatch):
    assistant = build_assistant(tmp_path)
    errors: list[str] = []
    monkeypatch.setattr(main, "render_error", lambda msg: errors.append(msg))
    monkeypatch.setattr(main, "render_info", lambda msg: None)

    main._handle_mentor(assistant=assistant, command="/mentor sideways")

    assert errors
    assert assistant.state.mentor_mode == "do"  # unchanged


# ── guided-workflows skill ─────────────────────────────────────────────

def test_guided_workflows_skill_loads():
    from pathlib import Path

    from src.aradhya.skills.skill_loader import load_skills

    registry = load_skills(Path("."))
    skill = registry.get("guided-workflows")
    assert skill is not None
    assert skill.enabled is True
    assert "TEACH_ME" in skill.intents
