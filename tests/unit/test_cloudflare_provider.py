from __future__ import annotations

from pathlib import Path

from requests import HTTPError

from src.aradhya.providers.cloudflare import CloudflareWorkersAITextModelProvider
from src.aradhya.runtime_profile import ModelProfile


class FakeResponse:
    def __init__(self, payload, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def raise_for_status(self):
        if self.status_code >= 400:
            error = HTTPError(f"HTTP {self.status_code}")
            error.response = self
            raise error

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, post_payload=None, get_payload=None):
        self.headers = {}
        self.last_post = None
        self.last_get = None
        self.post_calls = 0
        self.get_calls = 0
        self.post_payload = post_payload or {
            "success": True,
            "result": {"response": "PEP 8 guidance"},
        }
        self.get_payload = get_payload or {
            "success": True,
            "result": [{"id": "@cf/zai-org/glm-5.2"}],
        }

    def get(self, url, *, params, timeout):
        self.get_calls += 1
        self.last_get = {"url": url, "params": params, "timeout": timeout}
        return FakeResponse(self.get_payload)

    def post(self, url, *, json, timeout):
        self.post_calls += 1
        self.last_post = {"url": url, "json": json, "timeout": timeout}
        return FakeResponse(self.post_payload)


def build_profile(**overrides) -> ModelProfile:
    values = {
        "provider": "cloudflare",
        "model_name": "@cf/zai-org/glm-5.2",
        "base_url": "https://api.cloudflare.com/client/v4",
        "request_timeout_seconds": 30,
        "system_prompt": "You are a friendly assistant",
        "ollama_home": Path(".ollama"),
        "ollama_models_path": Path(".ollama/models"),
        "api_key": "test-token",
        "api_key_env": "CLOUDFLARE_API_TOKEN",
        "api_key_fallback_envs": ("CLOUDFLARE_AUTH_TOKEN",),
        "account_id": "test-account",
        "account_id_env": "CLOUDFLARE_ACCOUNT_ID",
    }
    values.update(overrides)
    return ModelProfile(**values)


def test_cloudflare_generate_posts_workers_ai_messages():
    session = FakeSession()
    provider = CloudflareWorkersAITextModelProvider(build_profile(), session=session)

    result = provider.generate("Tell me all about PEP-8")

    assert result.text == "PEP 8 guidance"
    assert result.provider == "cloudflare"
    assert session.headers["Authorization"] == "Bearer test-token"
    assert session.last_post["url"] == (
        "https://api.cloudflare.com/client/v4/accounts/test-account/"
        "ai/run/@cf/zai-org/glm-5.2"
    )
    assert session.last_post["json"]["messages"] == [
        {"role": "system", "content": "You are a friendly assistant"},
        {"role": "user", "content": "Tell me all about PEP-8"},
    ]


def test_cloudflare_blocks_private_prompt_before_network_call():
    session = FakeSession()
    provider = CloudflareWorkersAITextModelProvider(build_profile(), session=session)

    result = provider.generate(
        "Use CLOUDFLARE_API_TOKEN=abcdefghijklmnopqrstuvwxyz1234567890"
    )

    assert "privacy gate" in result.text
    assert session.post_calls == 0
    assert session.last_post is None


def test_cloudflare_health_checks_configured_model_catalog():
    session = FakeSession()
    provider = CloudflareWorkersAITextModelProvider(build_profile(), session=session)

    health = provider.health_check()

    assert health.reachable is True
    assert health.ready is True
    assert health.configured_model == "@cf/zai-org/glm-5.2"
    assert session.last_get["url"] == (
        "https://api.cloudflare.com/client/v4/accounts/test-account/"
        "ai/models/search"
    )
    assert session.last_get["params"] == {"search": "@cf/zai-org/glm-5.2"}


def test_cloudflare_health_reports_missing_configuration_without_network_call():
    session = FakeSession()
    provider = CloudflareWorkersAITextModelProvider(
        build_profile(account_id="", api_key=""),
        session=session,
    )

    health = provider.health_check()

    assert health.reachable is False
    assert health.ready is False
    assert "CLOUDFLARE_ACCOUNT_ID" in health.message
    assert "CLOUDFLARE_API_TOKEN or CLOUDFLARE_AUTH_TOKEN" in health.message
    assert session.get_calls == 0
