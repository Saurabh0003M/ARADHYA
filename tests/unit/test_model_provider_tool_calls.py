from __future__ import annotations

from pathlib import Path

from requests.exceptions import HTTPError

from src.aradhya.model_provider import OllamaTextModelProvider
from src.aradhya.runtime_profile import ModelProfile


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


class GenerateFallbackSession:
    def __init__(self):
        self.posts = []

    def post(self, url, *, json, timeout):
        self.posts.append({"url": url, "json": json, "timeout": timeout})
        if url.endswith("/api/generate"):
            return FakeResponse({"error": "generation failed"}, status_code=500)
        return FakeResponse(
            {
                "model": "fake-model",
                "message": {"content": "chat fallback response"},
            }
        )


class UnrunnableModelSession:
    def get(self, url, *, timeout):
        return FakeResponse({"models": [{"name": "fake-model"}]})

    def post(self, url, *, json, timeout):
        return FakeResponse(
            {"error": "model requires more system memory"},
            status_code=500,
        )


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


def test_ollama_generate_retries_chat_when_generate_endpoint_fails():
    session = GenerateFallbackSession()
    provider = OllamaTextModelProvider(build_profile(), session=session)

    result = provider.generate("hello")

    assert result.text == "chat fallback response"
    assert result.raw["generate_fallback"] == "chat"
    assert session.posts[0]["url"].endswith("/api/generate")
    assert session.posts[1]["url"].endswith("/api/chat")
    assert session.posts[1]["json"]["messages"][0] == {
        "role": "system",
        "content": "system",
    }


def test_ollama_health_check_reports_installed_but_unrunnable_model():
    provider = OllamaTextModelProvider(build_profile(), session=UnrunnableModelSession())

    health = provider.health_check()

    assert health.reachable is True
    assert health.ready is False
    assert "installed but cannot run" in health.message
    assert "model requires more system memory" in health.message
