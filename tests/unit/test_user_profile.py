"""P1-4: structured user-context store for general form assistance.

Covers the store (load/save/set/clear), the get_user_profile tool, the
keys-only prompt injection (sensitive values stay out of the prompt), and the
/profile command."""

from __future__ import annotations

import json
from datetime import datetime

from src.aradhya import main
from src.aradhya.assistant_core import AradhyaAssistant
from src.aradhya.assistant_models import AssistantPreferences, DirectoryIndexPolicy
from src.aradhya.tools import profile_tools
from src.aradhya.tools.profile_tools import get_user_profile, set_active_user_profile
from src.aradhya.user_profile import StructuredProfile, is_sensitive_key, profile_path


# ── store ──────────────────────────────────────────────────────────────

def test_set_get_clear_roundtrip(tmp_path):
    profile = StructuredProfile(tmp_path / "p.json")
    profile.set("Email", "me@example.com")
    assert profile.get("email") == "me@example.com"  # key normalized
    assert profile.clear("email") is True
    assert profile.get("email") is None


def test_save_and_load(tmp_path):
    path = tmp_path / "p.json"
    profile = StructuredProfile(path)
    profile.set("full_name", "Ada Lovelace")
    profile.set("phone", "555-1234")
    profile.save()

    reloaded = StructuredProfile.load(path)
    assert reloaded.get("full_name") == "Ada Lovelace"
    assert reloaded.get("phone") == "555-1234"


def test_load_tolerates_missing_or_corrupt(tmp_path):
    assert StructuredProfile.load(tmp_path / "nope.json").is_empty()
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert StructuredProfile.load(bad).is_empty()


def test_non_sensitive_keys_excludes_sensitive(tmp_path):
    profile = StructuredProfile(tmp_path / "p.json")
    profile.set("full_name", "Ada")
    profile.set("phone", "555")
    assert "phone" not in profile.non_sensitive_keys()
    assert "full_name" in profile.non_sensitive_keys()
    assert is_sensitive_key("phone") is True


# ── get_user_profile tool ──────────────────────────────────────────────

def test_tool_reports_empty_when_unset():
    set_active_user_profile(None)
    out = get_user_profile()
    assert "No structured profile" in out


def test_tool_lists_saved_fields(tmp_path):
    profile = StructuredProfile(tmp_path / "p.json")
    profile.set("full_name", "Ada")
    profile.set("phone", "555-1234")
    set_active_user_profile(profile)
    try:
        out = get_user_profile()
        assert "Ada" in out
        assert "555-1234" in out
        assert "(sensitive)" in out  # phone flagged
    finally:
        set_active_user_profile(None)


def test_tool_registered():
    names = {t._tool_def.name for t in profile_tools.ALL_PROFILE_TOOLS}
    assert "get_user_profile" in names


# ── assistant wiring + prompt injection ────────────────────────────────

def _build_preferences(tmp_path):
    return AssistantPreferences(
        user_roots=(tmp_path,),
        directory_index_path=tmp_path / "directory-index.txt",
        context_cache_dir=tmp_path / "context-cache",
        confirmation_phrases=("yes proceed",),
        security_blog_urls=(),
        project_markers=("pyproject.toml",),
        game_library_roots=tuple(),
        allow_live_execution=False,
        directory_index_policy=DirectoryIndexPolicy(max_nodes=1000),
    )


def _assistant(tmp_path):
    return AradhyaAssistant(
        _build_preferences(tmp_path),
        model_provider=None,
        now_provider=lambda: datetime(2026, 6, 19, 10, 0, 0),
        project_root=tmp_path,
    )


def test_profile_block_empty_when_no_profile(tmp_path):
    assistant = _assistant(tmp_path)
    assert assistant._build_user_profile_block() == ""


def test_profile_block_lists_keys_not_sensitive_values(tmp_path):
    # Seed the profile file the assistant loads from.
    (tmp_path / "core" / "memory" / "user_context").mkdir(parents=True)
    path = profile_path(tmp_path)
    path.write_text(
        json.dumps({"full_name": "Ada Lovelace", "phone": "555-9999"}),
        encoding="utf-8",
    )
    assistant = _assistant(tmp_path)

    block = assistant._build_user_profile_block()

    assert "Full name" in block            # label present
    assert "Phone number" in block         # sensitive field name present
    assert "555-9999" not in block         # sensitive VALUE never injected
    assert "Ada Lovelace" not in block     # values not injected (keys only)
    assert "get_user_profile" in block


# ── /profile command ───────────────────────────────────────────────────

def test_profile_command_set_and_persist(tmp_path, monkeypatch):
    assistant = _assistant(tmp_path)
    monkeypatch.setattr(main, "render_info", lambda msg: None)
    monkeypatch.setattr(main, "render_error", lambda msg: None)

    main._handle_profile(assistant=assistant, command="/profile set email me@example.com")

    assert assistant.user_profile.get("email") == "me@example.com"
    # persisted to disk
    saved = json.loads(profile_path(tmp_path).read_text(encoding="utf-8"))
    assert saved["email"] == "me@example.com"


def test_profile_command_view_masks_sensitive(tmp_path, monkeypatch):
    assistant = _assistant(tmp_path)
    assistant.user_profile.set("full_name", "Ada")
    assistant.user_profile.set("phone", "555-1234")
    shown: list[str] = []
    monkeypatch.setattr(main, "render_info", lambda msg: shown.append(msg))

    main._handle_profile(assistant=assistant, command="/profile")

    text = "\n".join(shown)
    assert "Ada" in text             # non-sensitive shown
    assert "555-1234" not in text    # sensitive masked
    assert "(saved)" in text


def test_profile_command_clear(tmp_path, monkeypatch):
    assistant = _assistant(tmp_path)
    assistant.user_profile.set("city", "London")
    assistant.user_profile.save()
    monkeypatch.setattr(main, "render_info", lambda msg: None)
    monkeypatch.setattr(main, "render_warning", lambda msg: None)

    main._handle_profile(assistant=assistant, command="/profile clear city")

    assert assistant.user_profile.get("city") is None
