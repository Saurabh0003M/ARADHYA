"""Provider abstraction for local reasoning models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import requests

from src.aradhya.runtime_profile import ModelProfile


@dataclass(frozen=True)
class ModelHealth:
    """Health summary for the configured model provider."""

    reachable: bool
    ready: bool
    provider: str
    configured_model: str
    available_models: tuple[str, ...]
    message: str


@dataclass(frozen=True)
class ModelResult:
    """Generated text plus provider metadata."""

    text: str
    model: str
    provider: str
    raw: dict[str, Any]


class TextModelProvider(Protocol):
    """Minimal protocol for swappable text model providers."""

    def health_check(self) -> ModelHealth:
        """Report whether the configured provider and model are available."""

    def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
    ) -> ModelResult:
        """Generate a response for the given prompt."""


class OllamaTextModelProvider:
    """Ollama-backed provider for local text generation."""

    def __init__(
        self,
        profile: ModelProfile,
        session: requests.Session | None = None,
    ):
        self.profile = profile
        self.session = session or requests.Session()

    def health_check(self) -> ModelHealth:
        try:
            response = self.session.get(
                f"{self.profile.base_url}/api/tags",
                timeout=self.profile.request_timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as error:
            return ModelHealth(
                reachable=False,
                ready=False,
                provider=self.profile.provider,
                configured_model=self.profile.model_name,
                available_models=tuple(),
                message=f"Ollama is not reachable at {self.profile.base_url}: {error}",
            )

        available_models = tuple(
            model.get("name", "")
            for model in payload.get("models", [])
            if model.get("name")
        )
        ready = self.profile.model_name in available_models
        message = (
            f"Configured model {self.profile.model_name} is available."
            if ready
            else (
                f"Ollama is reachable, but {self.profile.model_name} was not listed. "
                "Update profile.json or pull the model."
            )
        )

        return ModelHealth(
            reachable=True,
            ready=ready,
            provider=self.profile.provider,
            configured_model=self.profile.model_name,
            available_models=available_models,
            message=message,
        )

    def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
    ) -> ModelResult:
        payload = {
            "model": self.profile.model_name,
            "prompt": prompt,
            "system": system_prompt or self.profile.system_prompt,
            "stream": False,
        }
        response = self.session.post(
            f"{self.profile.base_url}/api/generate",
            json=payload,
            timeout=self.profile.request_timeout_seconds,
        )
        response.raise_for_status()
        raw = response.json()

        return ModelResult(
            text=raw.get("response", "").strip(),
            model=raw.get("model", self.profile.model_name),
            provider=self.profile.provider,
            raw=raw,
        )


def build_text_model_provider(profile: ModelProfile) -> TextModelProvider:
    """Construct the configured model provider."""

    provider = profile.provider.lower()
    if provider == "ollama":
        return OllamaTextModelProvider(profile)

    raise ValueError(
        f"Unsupported model provider '{profile.provider}'. "
        "Add a new provider implementation instead of hard-coding a model."
    )
