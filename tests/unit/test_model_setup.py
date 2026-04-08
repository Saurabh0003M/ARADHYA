from __future__ import annotations

import json

from src.aradhya.model_provider import ModelHealth
from src.aradhya.model_setup import RECOMMENDED_OLLAMA_MODELS, bootstrap_runtime_profile
from src.aradhya.runtime_profile import build_default_runtime_profile, persist_model_name


class FakeProvider:
    def __init__(self, health: ModelHealth):
        self._health = health

    def health_check(self) -> ModelHealth:
        return self._health


def test_bootstrap_uses_only_installed_model_by_default(monkeypatch, tmp_path):
    profile = build_default_runtime_profile(tmp_path)
    health = ModelHealth(
        reachable=True,
        ready=False,
        provider="ollama",
        configured_model="gemma4:e4b",
        available_models=("phi4",),
        message="configured model missing",
    )
    saved_models: list[str] = []
    outputs: list[str] = []

    monkeypatch.setattr(
        "src.aradhya.model_setup.build_text_model_provider",
        lambda _profile: FakeProvider(health),
    )
    monkeypatch.setattr(
        "src.aradhya.model_setup.persist_model_name",
        lambda _project_root, model_name: saved_models.append(model_name)
        or tmp_path / "profile.json",
    )

    updated = bootstrap_runtime_profile(
        profile,
        tmp_path,
        input_func=lambda _prompt: "",
        output_handler=outputs.append,
    )

    assert updated.model.model_name == "phi4"
    assert saved_models == ["phi4"]
    assert any("Using it by default." in line for line in outputs)


def test_bootstrap_prompts_for_installed_model_selection(monkeypatch, tmp_path):
    profile = build_default_runtime_profile(tmp_path)
    health = ModelHealth(
        reachable=True,
        ready=False,
        provider="ollama",
        configured_model="gemma4:e4b",
        available_models=("phi4", "qwen2.5-coder:7b"),
        message="configured model missing",
    )
    saved_models: list[str] = []
    outputs: list[str] = []
    prompts: list[str] = []

    monkeypatch.setattr(
        "src.aradhya.model_setup.build_text_model_provider",
        lambda _profile: FakeProvider(health),
    )
    monkeypatch.setattr(
        "src.aradhya.model_setup.persist_model_name",
        lambda _project_root, model_name: saved_models.append(model_name)
        or tmp_path / "profile.json",
    )

    def fake_input(prompt: str) -> str:
        prompts.append(prompt)
        return "2"

    updated = bootstrap_runtime_profile(
        profile,
        tmp_path,
        input_func=fake_input,
        output_handler=outputs.append,
    )

    assert updated.model.model_name == "qwen2.5-coder:7b"
    assert saved_models == ["qwen2.5-coder:7b"]
    assert prompts == ["Select a model number or press Enter to keep the current profile: "]
    assert any("1. phi4" in line for line in outputs)
    assert any("2. qwen2.5-coder:7b" in line for line in outputs)


def test_bootstrap_recommends_download_catalog_when_no_models_exist(monkeypatch, tmp_path):
    profile = build_default_runtime_profile(tmp_path)
    health = ModelHealth(
        reachable=True,
        ready=False,
        provider="ollama",
        configured_model="gemma4:e4b",
        available_models=tuple(),
        message="no local models",
    )
    saved_models: list[str] = []
    outputs: list[str] = []
    expected_model = RECOMMENDED_OLLAMA_MODELS[0]

    monkeypatch.setattr(
        "src.aradhya.model_setup.build_text_model_provider",
        lambda _profile: FakeProvider(health),
    )
    monkeypatch.setattr(
        "src.aradhya.model_setup.persist_model_name",
        lambda _project_root, model_name: saved_models.append(model_name)
        or tmp_path / "profile.json",
    )

    updated = bootstrap_runtime_profile(
        profile,
        tmp_path,
        input_func=lambda _prompt: "1",
        output_handler=outputs.append,
    )

    assert updated.model.model_name == expected_model.name
    assert saved_models == [expected_model.name]
    assert any(expected_model.name in line for line in outputs)
    assert any(f"ollama pull {expected_model.name}" in line for line in outputs)


def test_bootstrap_keeps_profile_when_ollama_is_unreachable(monkeypatch, tmp_path):
    profile = build_default_runtime_profile(tmp_path)
    health = ModelHealth(
        reachable=False,
        ready=False,
        provider="ollama",
        configured_model="gemma4:e4b",
        available_models=tuple(),
        message="Ollama is not reachable",
    )
    outputs: list[str] = []

    monkeypatch.setattr(
        "src.aradhya.model_setup.build_text_model_provider",
        lambda _profile: FakeProvider(health),
    )

    updated = bootstrap_runtime_profile(
        profile,
        tmp_path,
        input_func=lambda _prompt: "",
        output_handler=outputs.append,
    )

    assert updated == profile
    assert any("https://ollama.com/download" in line for line in outputs)


def test_persist_model_name_updates_profile_json(tmp_path):
    profile = build_default_runtime_profile(tmp_path)
    profile_path = tmp_path / "core" / "memory" / "profile.json"
    profile_path.parent.mkdir(parents=True)
    profile_path.write_text(
        json.dumps(
            {
                "model": {
                    "provider": profile.model.provider,
                    "model_name": profile.model.model_name,
                    "base_url": profile.model.base_url,
                },
                "voice": {"provider": profile.voice.provider},
            }
        ),
        encoding="utf-8",
    )

    persist_model_name(tmp_path, "phi4-mini")

    payload = json.loads(profile_path.read_text(encoding="utf-8"))
    assert payload["model"]["model_name"] == "phi4-mini"
    assert payload["model"]["provider"] == "ollama"
    assert payload["voice"]["provider"] == profile.voice.provider
