from __future__ import annotations

from pathlib import Path

from src.aradhya.providers.openrouter import OpenRouterTextModelProvider
from src.aradhya.runtime_profile import ModelProfile


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self):
        self.headers = {}
        self.last_payload = None
        self.post_calls = 0

    def post(self, url, *, json, timeout, stream=False):
        self.post_calls += 1
        self.last_payload = json
        return FakeResponse(
            {
                "model": json["model"],
                "choices": [
                    {
                        "message": {
                            "content": "ok",
                            "tool_calls": [],
                        }
                    }
                ],
            }
        )


def build_profile() -> ModelProfile:
    return ModelProfile(
        provider="openrouter",
        model_name="google/gemma-4-31b-it:free",
        base_url="https://openrouter.ai/api/v1",
        request_timeout_seconds=30,
        system_prompt="system",
        ollama_home=Path(".ollama"),
        ollama_models_path=Path(".ollama/models"),
        api_key="test-key",
        api_key_env="ARADHYA_OPENROUTER_API_KEY",
    )


def test_openrouter_forwards_openai_style_tools_unchanged():
    session = FakeSession()
    provider = OpenRouterTextModelProvider(build_profile(), session=session)

    provider.chat(
        [{"role": "user", "content": "use a tool"}],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read file",
                    "parameters": {"type": "object"},
                },
            }
        ],
    )

    assert session.last_payload["tools"][0]["function"]["name"] == "read_file"


def test_openrouter_blocks_private_prompt_before_network_call():
    session = FakeSession()
    provider = OpenRouterTextModelProvider(build_profile(), session=session)

    result = provider.generate("Use sk-or-v1-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa from F:\\ARADHYA")

    assert "privacy gate" in result.text
    assert session.post_calls == 0
    assert session.last_payload is None
