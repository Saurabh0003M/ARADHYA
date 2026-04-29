from __future__ import annotations

from pathlib import Path

from src.aradhya.model_provider import OllamaTextModelProvider
from src.aradhya.runtime_profile import ModelProfile


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, payload):
        self.payload = payload
        self.last_post = None

    def post(self, url, *, json, timeout):
        self.last_post = {"url": url, "json": json, "timeout": timeout}
        return FakeResponse(self.payload)


def build_profile() -> ModelProfile:
    return ModelProfile(
        provider="ollama",
        model_name="fake-model",
        base_url="http://127.0.0.1:11434",
        request_timeout_seconds=30,
        system_prompt="system",
        ollama_home=Path(".ollama"),
        ollama_models_path=Path(".ollama/models"),
    )


def test_ollama_chat_parses_tool_calls_from_dict_arguments():
    session = FakeSession(
        {
            "model": "fake-model",
            "message": {
                "content": "",
                "tool_calls": [
                    {
                        "id": "abc",
                        "function": {
                            "name": "read_file",
                            "arguments": {"path": "README.md"},
                        },
                    }
                ],
            },
        }
    )
    provider = OllamaTextModelProvider(build_profile(), session=session)

    result = provider.chat(
        [{"role": "user", "content": "read"}],
        tools=[{"type": "function", "function": {"name": "read_file"}}],
    )

    assert result.text == ""
    assert result.tool_calls[0].id == "abc"
    assert result.tool_calls[0].name == "read_file"
    assert result.tool_calls[0].arguments == {"path": "README.md"}
    assert session.last_post["json"]["tools"][0]["function"]["name"] == "read_file"


def test_ollama_chat_parses_tool_calls_from_json_string_arguments():
    session = FakeSession(
        {
            "model": "fake-model",
            "message": {
                "content": "working",
                "tool_calls": [
                    {
                        "function": {
                            "name": "web_search",
                            "arguments": '{"query": "aradhya"}',
                        },
                    }
                ],
            },
        }
    )
    provider = OllamaTextModelProvider(build_profile(), session=session)

    result = provider.chat([{"role": "user", "content": "search"}])

    assert result.text == "working"
    assert result.tool_calls[0].name == "web_search"
    assert result.tool_calls[0].arguments == {"query": "aradhya"}
