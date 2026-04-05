from __future__ import annotations

import json

from src.aradhya.model_provider import OllamaTextModelProvider
from src.aradhya.runtime_profile import (
    ModelProfile,
    VoiceProfile,
    build_default_runtime_profile,
    load_runtime_profile,
)
from src.aradhya.voice_pipeline import VoiceInboxManager


class DummyResponse:
    def __init__(self, payload, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class DummySession:
    def __init__(self):
        self.last_post_json = None

    def get(self, url, timeout):
        return DummyResponse({"models": [{"name": "gemma4:e4b"}, {"name": "phi4"}]})

    def post(self, url, json, timeout):
        self.last_post_json = json
        return DummyResponse({"model": json["model"], "response": "planned response"})


def test_load_runtime_profile_reads_custom_model_and_voice_paths(tmp_path):
    (tmp_path / "core" / "memory").mkdir(parents=True)
    profile_payload = {
        "model": {
            "provider": "ollama",
            "model_name": "gemma5",
            "base_url": "http://localhost:11434",
        },
        "voice": {
            "provider": "manual_transcript",
            "audio_inbox_dir": "audio/dropbox",
        },
    }
    (tmp_path / "core" / "memory" / "profile.json").write_text(
        json.dumps(profile_payload),
        encoding="utf-8",
    )

    profile = load_runtime_profile(tmp_path)

    assert profile.model.model_name == "gemma5"
    assert profile.voice.audio_inbox_dir == tmp_path / "audio" / "dropbox"


def test_ollama_provider_uses_configured_model_name():
    profile = ModelProfile(
        provider="ollama",
        model_name="gemma4:e4b",
        base_url="http://127.0.0.1:11434",
        request_timeout_seconds=30,
        system_prompt="System prompt",
        ollama_home=build_default_runtime_profile().model.ollama_home,
        ollama_models_path=build_default_runtime_profile().model.ollama_models_path,
    )
    session = DummySession()
    provider = OllamaTextModelProvider(profile, session=session)

    health = provider.health_check()
    result = provider.generate("hello world")

    assert health.ready is True
    assert "gemma4:e4b" in health.available_models
    assert session.last_post_json["model"] == "gemma4:e4b"
    assert result.model == "gemma4:e4b"
    assert result.text == "planned response"


def test_voice_inbox_manual_transcript_flow_moves_audio_and_saves_text(tmp_path):
    profile = VoiceProfile(
        provider="manual_transcript",
        audio_inbox_dir=tmp_path / "audio" / "inbox",
        processed_audio_dir=tmp_path / "audio" / "processed",
        transcripts_dir=tmp_path / "audio" / "transcripts",
        manual_transcripts_dir=tmp_path / "audio" / "manual_transcripts",
        supported_extensions=(".mp3", ".wav"),
        whisper_command_template=None,
        poll_on_wake=True,
    )
    manager = VoiceInboxManager(profile)
    manager.ensure_directories()

    audio_path = profile.audio_inbox_dir / "meeting.mp3"
    audio_path.write_text("fake audio bytes", encoding="utf-8")
    manual_transcript = profile.manual_transcripts_dir / "meeting.txt"
    manual_transcript.write_text("open notes folder", encoding="utf-8")

    results = manager.process_pending_audio()

    assert len(results) == 1
    result = results[0]
    assert result.status == "processed"
    assert result.transcript_text == "open notes folder"
    assert result.transcript_path is not None
    assert result.transcript_path.read_text(encoding="utf-8").strip() == "open notes folder"
    assert result.archived_audio_path is not None
    assert result.archived_audio_path.exists()
    assert not audio_path.exists()
