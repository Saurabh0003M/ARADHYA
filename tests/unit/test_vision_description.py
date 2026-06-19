"""P1-3: multimodal screenshot description.

Covers the Ollama describe_image payload/parse, vision-model resolution, the
cloud provider's local-first refusal, and the describe_screen tool wiring
(provider registry, capture failure, success, no-provider)."""

from __future__ import annotations

import base64
from pathlib import Path

import pytest
from requests.exceptions import HTTPError

from src.aradhya.model_provider import ModelResult, OllamaTextModelProvider
from src.aradhya.runtime_profile import ModelProfile
from src.aradhya.tools import vision_tools
from src.aradhya.tools.vision_tools import describe_screen, set_active_vision_provider


class FakeResponse:
    def __init__(self, payload, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            error = HTTPError(f"HTTP {self.status_code}")
            error.response = self
            raise error

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, payload):
        self.payload = payload
        self.last_post = None

    def post(self, url, *, json, timeout):
        self.last_post = {"url": url, "json": json, "timeout": timeout}
        return FakeResponse(self.payload)


def build_profile(vision_model: str = "") -> ModelProfile:
    return ModelProfile(
        provider="ollama",
        model_name="text-model",
        base_url="http://127.0.0.1:11434",
        request_timeout_seconds=30,
        system_prompt="system",
        ollama_home=Path(".ollama"),
        ollama_models_path=Path(".ollama/models"),
        vision_model=vision_model,
    )


# ── Ollama describe_image ──────────────────────────────────────────────

def test_describe_image_sends_base64_and_parses(tmp_path):
    image = tmp_path / "shot.png"
    image.write_bytes(b"\x89PNG fake bytes")
    session = FakeSession({"model": "moondream", "message": {"content": "A login form."}})
    provider = OllamaTextModelProvider(build_profile(vision_model="moondream"), session=session)

    result = provider.describe_image(str(image), "What is on screen?")

    assert result.text == "A login form."
    sent = session.last_post
    assert sent["url"].endswith("/api/chat")
    message = sent["json"]["messages"][0]
    assert message["content"] == "What is on screen?"
    # image carried as base64 with no data-uri prefix
    assert message["images"] == [base64.b64encode(b"\x89PNG fake bytes").decode("ascii")]
    assert sent["json"]["model"] == "moondream"


def test_describe_image_prefers_explicit_model_then_vision_then_text(tmp_path):
    image = tmp_path / "shot.png"
    image.write_bytes(b"x")

    # explicit override wins
    s1 = FakeSession({"message": {"content": "ok"}})
    OllamaTextModelProvider(build_profile("vis"), session=s1).describe_image(
        str(image), "p", model="override"
    )
    assert s1.last_post["json"]["model"] == "override"

    # else profile.vision_model
    s2 = FakeSession({"message": {"content": "ok"}})
    OllamaTextModelProvider(build_profile("vis"), session=s2).describe_image(str(image), "p")
    assert s2.last_post["json"]["model"] == "vis"

    # else fall back to text model_name
    s3 = FakeSession({"message": {"content": "ok"}})
    OllamaTextModelProvider(build_profile(""), session=s3).describe_image(str(image), "p")
    assert s3.last_post["json"]["model"] == "text-model"


def test_describe_image_missing_file_returns_error_result():
    provider = OllamaTextModelProvider(build_profile("vis"), session=FakeSession({}))
    result = provider.describe_image("does/not/exist.png", "p")
    assert "Could not read image" in result.text


# ── OpenRouter local-first refusal ─────────────────────────────────────

def test_openrouter_describe_image_refuses_to_keep_local():
    from src.aradhya.providers.openrouter import OpenRouterTextModelProvider

    profile = ModelProfile(
        provider="openrouter",
        model_name="some/model",
        base_url="https://openrouter.ai/api/v1",
        request_timeout_seconds=30,
        system_prompt="system",
        ollama_home=Path(".ollama"),
        ollama_models_path=Path(".ollama/models"),
        api_key="sk-test",
    )
    provider = OpenRouterTextModelProvider(profile)
    result = provider.describe_image("shot.png", "describe")

    assert isinstance(result, ModelResult)
    assert "local" in result.text.lower()
    assert result.raw.get("vision") == "disabled_cloud_local_first"


# ── describe_screen tool ───────────────────────────────────────────────

class FakeVisionProvider:
    def __init__(self, text: str):
        self.text = text
        self.described: list[tuple[str, str]] = []

    def describe_image(self, image_path: str, prompt: str, *, model=None) -> ModelResult:
        self.described.append((image_path, prompt))
        return ModelResult(text=self.text, model="vis", provider="ollama", raw={})


@pytest.fixture(autouse=True)
def _clear_provider():
    set_active_vision_provider(None)
    yield
    set_active_vision_provider(None)


def test_describe_screen_without_provider():
    out = describe_screen("what is on screen?")
    assert "No vision model" in out


def test_describe_screen_success(monkeypatch):
    provider = FakeVisionProvider("A settings window with a Save button.")
    set_active_vision_provider(provider)
    # Stub capture so the test doesn't touch a real screen.
    monkeypatch.setattr(vision_tools, "_capture_screen_to", lambda path, region=None: True)

    out = describe_screen("describe the window")

    assert "A settings window" in out
    assert provider.described and provider.described[0][1] == "describe the window"


def test_describe_screen_capture_failure(monkeypatch):
    set_active_vision_provider(FakeVisionProvider("unused"))
    monkeypatch.setattr(vision_tools, "_capture_screen_to", lambda path, region=None: False)

    out = describe_screen("describe")

    assert "Failed to capture screen" in out


def test_describe_screen_registered_in_all_vision_tools():
    names = {t._tool_def.name for t in vision_tools.ALL_VISION_TOOLS}
    assert "describe_screen" in names


# ── screen-reader skill is enabled now ─────────────────────────────────

def test_screen_reader_skill_enabled():
    from src.aradhya.skills.skill_loader import load_skills

    registry = load_skills(Path("."))
    skill = registry.get("screen-reader")
    assert skill is not None
    assert skill.enabled is True
    assert "SCREEN_DESCRIBE" in skill.intents
