"""Provider abstraction for local reasoning models."""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any, Iterator, Protocol

from loguru import logger
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


@dataclass(frozen=True)
class ModelToolCall:
    """Structured tool call requested by the model provider."""

    name: str
    arguments: dict[str, Any]
    id: str = ""


@dataclass(frozen=True)
class ModelChatResult:
    """Chat response with optional provider-native tool calls."""

    text: str
    model: str
    provider: str
    raw: dict[str, Any]
    tool_calls: tuple[ModelToolCall, ...] = ()


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

    def generate_stream(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
    ) -> Iterator[str]:
        """Stream a response for the given prompt, yielding text chunks."""

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        system_prompt: str | None = None,
    ) -> ModelChatResult:
        """Generate a chat response, optionally with structured tool calls."""

    def chat_stream(
        self,
        messages: list[dict[str, Any]],
        *,
        system_prompt: str | None = None,
    ) -> Iterator[str]:
        """Stream a chat response, yielding text chunks."""

    def describe_image(
        self,
        image_path: str,
        prompt: str,
        *,
        model: str | None = None,
    ) -> ModelResult:
        """Describe an image using a multimodal model."""


def _encode_image_base64(image_path: str) -> str:
    """Return the base64 contents of an image file (no data-URI prefix)."""
    import base64
    from pathlib import Path

    data = Path(image_path).read_bytes()
    return base64.b64encode(data).decode("ascii")


class OllamaTextModelProvider:
    """Ollama-backed provider for local text generation."""

    _health_cache_ttl_seconds = 30.0

    def __init__(
        self,
        profile: ModelProfile,
        session: requests.Session | None = None,
    ):
        self.profile = profile
        self.session = session or requests.Session()
        self._cached_health: tuple[float, ModelHealth] | None = None

    def health_check(self) -> ModelHealth:
        now = time.monotonic()
        if self._cached_health is not None:
            cached_at, cached_health = self._cached_health
            if now - cached_at <= self._health_cache_ttl_seconds:
                return cached_health

        logger.debug(
            "Checking Ollama health at {} for model {}",
            self.profile.base_url,
            self.profile.model_name,
        )
        try:
            response = self.session.get(
                f"{self.profile.base_url}/api/tags",
                timeout=self.profile.request_timeout_seconds,
            )
            self._raise_for_status_with_details(response)
            payload = response.json()
        except requests.RequestException as error:
            health = ModelHealth(
                reachable=False,
                ready=False,
                provider=self.profile.provider,
                configured_model=self.profile.model_name,
                available_models=tuple(),
                message=f"Ollama is not reachable at {self.profile.base_url}: {error}",
            )
            self._cached_health = (now, health)
            return health

        available_models = tuple(
            model.get("name", "")
            for model in payload.get("models", [])
            if model.get("name")
        )
        ready = self.profile.model_name in available_models
        if ready:
            ready, message = self._probe_model_ready()
        else:
            message = (
                f"Ollama is reachable, but {self.profile.model_name} was not listed. "
                "Update profile.json or pull the model."
            )

        health = ModelHealth(
            reachable=True,
            ready=ready,
            provider=self.profile.provider,
            configured_model=self.profile.model_name,
            available_models=available_models,
            message=message,
        )
        self._cached_health = (now, health)
        return health

    def _probe_model_ready(self) -> tuple[bool, str]:
        payload = {
            "model": self.profile.model_name,
            "prompt": "ok",
            "stream": False,
            "options": {"num_predict": 1},
        }
        try:
            response = self.session.post(
                f"{self.profile.base_url}/api/generate",
                json=payload,
                timeout=self.profile.request_timeout_seconds,
            )
            self._raise_for_status_with_details(response)
        except requests.RequestException as error:
            return (
                False,
                f"Configured model {self.profile.model_name} is installed but cannot run: {error}",
            )

        return True, f"Configured model {self.profile.model_name} is available and runnable."

    def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
    ) -> ModelResult:
        logger.debug(
            "Sending prompt to Ollama model {} with system prompt override={}",
            self.profile.model_name,
            system_prompt is not None,
        )
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
        try:
            self._raise_for_status_with_details(response)
        except requests.HTTPError as error:
            if self._should_retry_generate_as_chat(error):
                logger.warning(
                    "Ollama /api/generate failed for model {}; retrying /api/chat",
                    self.profile.model_name,
                )
                return self._generate_via_chat(prompt, system_prompt=system_prompt)
            raise
        raw = response.json()

        return ModelResult(
            text=raw.get("response", "").strip(),
            model=raw.get("model", self.profile.model_name),
            provider=self.profile.provider,
            raw=raw,
        )

    def _should_retry_generate_as_chat(self, error: requests.HTTPError) -> bool:
        response = getattr(error, "response", None)
        status_code = getattr(response, "status_code", None)
        return status_code is None or status_code >= 500 or status_code in {404, 405}

    def _generate_via_chat(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
    ) -> ModelResult:
        result = self.chat(
            [{"role": "user", "content": prompt}],
            system_prompt=system_prompt or self.profile.system_prompt,
        )
        raw = dict(result.raw)
        raw["generate_fallback"] = "chat"
        return ModelResult(
            text=result.text,
            model=result.model,
            provider=result.provider,
            raw=raw,
        )

    def generate_stream(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
    ) -> Iterator[str]:
        logger.debug(
            "Streaming prompt to Ollama model {} with system prompt override={}",
            self.profile.model_name,
            system_prompt is not None,
        )
        payload = {
            "model": self.profile.model_name,
            "prompt": prompt,
            "system": system_prompt or self.profile.system_prompt,
            "stream": True,
        }
        response = self.session.post(
            f"{self.profile.base_url}/api/generate",
            json=payload,
            timeout=self.profile.request_timeout_seconds,
            stream=True,
        )
        self._raise_for_status_with_details(response)

        import json
        for line in response.iter_lines():
            if line:
                chunk = json.loads(line)
                if "response" in chunk:
                    yield chunk["response"]

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        system_prompt: str | None = None,
    ) -> ModelChatResult:
        logger.debug(
            "Sending chat request to Ollama model {} with {} tool(s)",
            self.profile.model_name,
            len(tools or ()),
        )

        chat_messages = list(messages)
        if system_prompt:
            chat_messages = [{"role": "system", "content": system_prompt}] + chat_messages

        payload: dict[str, Any] = {
            "model": self.profile.model_name,
            "messages": chat_messages,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools

        response = self.session.post(
            f"{self.profile.base_url}/api/chat",
            json=payload,
            timeout=self.profile.request_timeout_seconds,
        )
        self._raise_for_status_with_details(response)
        raw = response.json()
        message = raw.get("message", {}) or {}

        tool_calls = tuple(
            self._parse_tool_call(raw_call)
            for raw_call in message.get("tool_calls", []) or []
        )

        return ModelChatResult(
            text=str(message.get("content", "") or "").strip(),
            model=raw.get("model", self.profile.model_name),
            provider=self.profile.provider,
            raw=raw,
            tool_calls=tool_calls,
        )

    def chat_stream(
        self,
        messages: list[dict[str, Any]],
        *,
        system_prompt: str | None = None,
    ) -> Iterator[str]:
        logger.debug("Streaming chat request to Ollama model {}", self.profile.model_name)
        chat_messages = list(messages)
        if system_prompt:
            chat_messages = [{"role": "system", "content": system_prompt}] + chat_messages

        payload: dict[str, Any] = {
            "model": self.profile.model_name,
            "messages": chat_messages,
            "stream": True,
        }

        response = self.session.post(
            f"{self.profile.base_url}/api/chat",
            json=payload,
            timeout=self.profile.request_timeout_seconds,
            stream=True,
        )
        self._raise_for_status_with_details(response)

        import json
        for line in response.iter_lines():
            if line:
                chunk = json.loads(line)
                message = chunk.get("message", {}) or {}
                if "content" in message:
                    yield message["content"]

    def describe_image(
        self,
        image_path: str,
        prompt: str,
        *,
        model: str | None = None,
    ) -> ModelResult:
        """Describe an image with a multimodal Ollama model.

        Resolves the vision model from (in order) the ``model`` override, the
        profile's ``vision_model``, then ``model_name``. Ollama accepts the
        image as a base64 string in the message's ``images`` array.
        """
        vision_model = model or self.profile.vision_model or self.profile.model_name
        try:
            encoded = _encode_image_base64(image_path)
        except OSError as error:
            return ModelResult(
                text=f"Could not read image at {image_path}: {error}",
                model=vision_model,
                provider=self.profile.provider,
                raw={"error": str(error)},
            )

        payload = {
            "model": vision_model,
            "messages": [
                {"role": "user", "content": prompt, "images": [encoded]},
            ],
            "stream": False,
        }
        response = self.session.post(
            f"{self.profile.base_url}/api/chat",
            json=payload,
            timeout=self.profile.request_timeout_seconds,
        )
        self._raise_for_status_with_details(response)
        raw = response.json()
        message = raw.get("message", {}) or {}
        return ModelResult(
            text=str(message.get("content", "") or "").strip(),
            model=raw.get("model", vision_model),
            provider=self.profile.provider,
            raw=raw,
        )

    def _parse_tool_call(self, raw_call: dict[str, Any]) -> ModelToolCall:
        function = raw_call.get("function", {}) or {}
        raw_arguments = function.get("arguments", {})
        if isinstance(raw_arguments, str):
            try:
                import json

                arguments = json.loads(raw_arguments)
            except (TypeError, ValueError):
                arguments = {}
        elif isinstance(raw_arguments, dict):
            arguments = raw_arguments
        else:
            arguments = {}

        return ModelToolCall(
            name=str(function.get("name", "") or ""),
            arguments=arguments,
            id=str(raw_call.get("id", "") or ""),
        )

    def _raise_for_status_with_details(self, response) -> None:
        try:
            response.raise_for_status()
        except requests.HTTPError as error:
            detail = self._response_error_detail(response)
            if detail:
                raise requests.HTTPError(
                    f"{error}. Ollama error: {detail}",
                    response=response,
                ) from error
            raise

    def _response_error_detail(self, response) -> str:
        try:
            payload = response.json()
        except (TypeError, ValueError):
            payload = None

        if isinstance(payload, dict):
            error = payload.get("error")
            if error:
                return str(error)

        text = str(getattr(response, "text", "") or "").strip()
        return text[:500]


def build_text_model_provider(profile: ModelProfile) -> TextModelProvider:
    """Construct the configured model provider."""


    provider = profile.provider.lower()
    if provider == "ollama":
        return OllamaTextModelProvider(profile)

    if provider == "openrouter":
        from src.aradhya.providers.openrouter import OpenRouterTextModelProvider
        return OpenRouterTextModelProvider(profile)

    if provider == "cloudflare":
        from src.aradhya.providers.cloudflare import CloudflareWorkersAITextModelProvider
        return CloudflareWorkersAITextModelProvider(profile)

    raise ValueError(
        f"Unsupported model provider '{profile.provider}'. "
        "Supported: ollama, openrouter, cloudflare."
    )
