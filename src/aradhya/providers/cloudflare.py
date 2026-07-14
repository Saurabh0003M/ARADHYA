"""Cloudflare Workers AI provider for optional cloud-safe inference.

The official Cloudflare Python SDK defaults to ``CLOUDFLARE_API_TOKEN``.
This provider uses direct REST calls to avoid making the SDK a required
dependency, while keeping the same environment variable convention.

Configuration lives in ``core/config/profile.local.json``::

    {
      "model": {
        "provider": "cloudflare",
        "model_name": "@cf/zai-org/glm-5.2",
        "account_id_env": "CLOUDFLARE_ACCOUNT_ID",
        "api_key_env": "CLOUDFLARE_API_TOKEN"
      }
    }
"""

from __future__ import annotations

import json
import time
from typing import Any, Iterator

from loguru import logger
import requests

from src.aradhya.cloud_safety import CloudPrivacyGate, CloudSafetyAssessment
from src.aradhya.model_provider import (
    ModelChatResult,
    ModelHealth,
    ModelResult,
    ModelToolCall,
)
from src.aradhya.runtime_profile import ModelProfile


DEFAULT_BASE_URL = "https://api.cloudflare.com/client/v4"
DEFAULT_MODEL = "@cf/zai-org/glm-5.2"


class CloudflareWorkersAITextModelProvider:
    """Cloudflare Workers AI provider using the account-scoped run endpoint."""

    _health_cache_ttl_seconds = 60.0

    def __init__(
        self,
        profile: ModelProfile,
        session: requests.Session | None = None,
    ) -> None:
        self.profile = profile
        self.session = session or requests.Session()
        self._cached_health: tuple[float, ModelHealth] | None = None
        self.privacy_gate = CloudPrivacyGate()

        self.api_key = getattr(profile, "api_key", "") or ""
        self.account_id = getattr(profile, "account_id", "") or ""
        self.base_url = (profile.base_url or DEFAULT_BASE_URL).rstrip("/")
        self.model_name = profile.model_name or DEFAULT_MODEL

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        self.session.headers.update(headers)

    def health_check(self) -> ModelHealth:
        now = time.monotonic()
        if self._cached_health is not None:
            cached_at, cached_health = self._cached_health
            if now - cached_at <= self._health_cache_ttl_seconds:
                return cached_health

        missing = self._missing_configuration()
        if missing:
            health = ModelHealth(
                reachable=False,
                ready=False,
                provider="cloudflare",
                configured_model=self.model_name,
                available_models=tuple(),
                message=f"Missing Cloudflare configuration: {', '.join(missing)}.",
            )
            self._cached_health = (now, health)
            return health

        try:
            response = self.session.get(
                f"{self.base_url}/accounts/{self.account_id}/ai/models/search",
                params={"search": self.model_name},
                timeout=10,
            )
            self._raise_for_status_with_details(response)
            raw = response.json()
            available_models = self._extract_model_ids(raw)
        except requests.RequestException as error:
            health = ModelHealth(
                reachable=False,
                ready=False,
                provider="cloudflare",
                configured_model=self.model_name,
                available_models=tuple(),
                message=f"Cloudflare Workers AI is not reachable: {error}",
            )
            self._cached_health = (now, health)
            return health

        ready = not available_models or self.model_name in available_models
        message = (
            f"Ready - {self.model_name}"
            if ready
            else f"Model {self.model_name} was not found in Cloudflare Workers AI."
        )
        health = ModelHealth(
            reachable=True,
            ready=ready,
            provider="cloudflare",
            configured_model=self.model_name,
            available_models=available_models[:20],
            message=message,
        )
        self._cached_health = (now, health)
        return health

    def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
    ) -> ModelResult:
        messages = []
        resolved_system = system_prompt or self.profile.system_prompt
        if resolved_system:
            messages.append({"role": "system", "content": resolved_system})
        messages.append({"role": "user", "content": prompt})

        result = self.chat(messages)
        return ModelResult(
            text=result.text,
            model=result.model,
            provider=result.provider,
            raw=result.raw,
        )

    def generate_stream(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
    ) -> Iterator[str]:
        result = self.generate(prompt, system_prompt=system_prompt)
        if result.text:
            yield result.text

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        system_prompt: str | None = None,
    ) -> ModelChatResult:
        logger.debug(
            "Cloudflare Workers AI chat: model={}, msgs={}, tools={}",
            self.model_name,
            len(messages),
            len(tools or []),
        )

        chat_messages = list(messages)
        if system_prompt:
            chat_messages = [{"role": "system", "content": system_prompt}] + chat_messages

        assessment = self.privacy_gate.assess_messages(
            chat_messages,
            source="Cloudflare Workers AI chat",
        )
        if not assessment.allowed:
            return self._blocked_chat_result(assessment)

        missing = self._missing_configuration()
        if missing:
            return ModelChatResult(
                text=(
                    "[Cloudflare Workers AI not configured: missing "
                    f"{', '.join(missing)}.]"
                ),
                model=self.model_name,
                provider="cloudflare",
                raw={"missing_configuration": missing},
            )

        payload: dict[str, Any] = {"messages": chat_messages}
        if tools:
            payload["tools"] = self._format_tools(tools)

        try:
            response = self.session.post(
                self._run_url(self.model_name),
                json=payload,
                timeout=self.profile.request_timeout_seconds,
            )
            self._raise_for_status_with_details(response)
            raw = response.json()
        except requests.RequestException as error:
            return ModelChatResult(
                text=f"[Cloudflare Workers AI error: {error}]",
                model=self.model_name,
                provider="cloudflare",
                raw={},
            )
        except (TypeError, ValueError) as error:
            return ModelChatResult(
                text=f"[Cloudflare Workers AI response parse error: {error}]",
                model=self.model_name,
                provider="cloudflare",
                raw={},
            )

        return ModelChatResult(
            text=self._message_text(raw),
            model=self._response_model(raw),
            provider="cloudflare",
            raw=raw,
            tool_calls=self._tool_calls(raw),
        )

    def chat_stream(
        self,
        messages: list[dict[str, Any]],
        *,
        system_prompt: str | None = None,
    ) -> Iterator[str]:
        result = self.chat(messages, system_prompt=system_prompt)
        if result.text:
            yield result.text

    def describe_image(
        self,
        image_path: str,
        prompt: str,
        *,
        model: str | None = None,
    ) -> ModelResult:
        del image_path, prompt, model
        return ModelResult(
            text=(
                "Image description is disabled for the cloud provider to keep "
                "screen content on this machine. Configure a local Ollama "
                "vision_model to use describe_screen."
            ),
            model=self.model_name,
            provider="cloudflare",
            raw={"vision": "disabled_cloud_local_first"},
        )

    def _missing_configuration(self) -> tuple[str, ...]:
        missing: list[str] = []
        if not self.account_id:
            missing.append(self.profile.account_id_env or "account_id")
        if not self.api_key:
            token_envs = [self.profile.api_key_env or "api_key"]
            token_envs.extend(self.profile.api_key_fallback_envs)
            missing.append(" or ".join(token_envs))
        return tuple(missing)

    def _run_url(self, model_name: str) -> str:
        if "{account_id}" in self.base_url or "{model}" in self.base_url:
            return self.base_url.format(account_id=self.account_id, model=model_name)
        if "/ai/run/" in self.base_url:
            return self.base_url
        if self.base_url.endswith("/ai/run"):
            return f"{self.base_url}/{model_name}"
        return f"{self.base_url}/accounts/{self.account_id}/ai/run/{model_name}"

    def _format_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        formatted: list[dict[str, Any]] = []
        for tool in tools:
            if tool.get("type") == "function" and isinstance(tool.get("function"), dict):
                formatted.append(tool)
                continue
            formatted.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.get("name", ""),
                        "description": tool.get("description", ""),
                        "parameters": tool.get("parameters", {}),
                    },
                }
            )
        return formatted

    def _message_text(self, raw: dict[str, Any]) -> str:
        result = raw.get("result", raw)
        if isinstance(result, str):
            return result.strip()
        if isinstance(result, dict):
            for key in ("response", "text", "output_text", "content"):
                value = result.get(key)
                if isinstance(value, str):
                    return value.strip()
            choice_content = self._choice_content(result)
            if choice_content:
                return choice_content
        return self._choice_content(raw)

    def _choice_content(self, raw: dict[str, Any]) -> str:
        choices = raw.get("choices")
        if not isinstance(choices, list) or not choices:
            return ""
        first = choices[0] if isinstance(choices[0], dict) else {}
        message = first.get("message", {}) if isinstance(first, dict) else {}
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str):
                return content.strip()
        text = first.get("text") if isinstance(first, dict) else ""
        return text.strip() if isinstance(text, str) else ""

    def _response_model(self, raw: dict[str, Any]) -> str:
        result = raw.get("result", {})
        if isinstance(result, dict):
            model = result.get("model")
            if isinstance(model, str) and model:
                return model
        model = raw.get("model")
        return model if isinstance(model, str) and model else self.model_name

    def _tool_calls(self, raw: dict[str, Any]) -> tuple[ModelToolCall, ...]:
        candidates: list[Any] = []
        result = raw.get("result", {})
        if isinstance(result, dict):
            result_calls = result.get("tool_calls")
            if isinstance(result_calls, list):
                candidates.extend(result_calls)
            choices = result.get("choices")
            if isinstance(choices, list):
                candidates.extend(self._tool_calls_from_choices(choices))
        choices = raw.get("choices")
        if isinstance(choices, list):
            candidates.extend(self._tool_calls_from_choices(choices))
        return tuple(
            self._parse_tool_call(raw_call)
            for raw_call in candidates
            if isinstance(raw_call, dict)
        )

    def _tool_calls_from_choices(self, choices: list[Any]) -> list[dict[str, Any]]:
        calls: list[dict[str, Any]] = []
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            message = choice.get("message")
            if not isinstance(message, dict):
                continue
            raw_calls = message.get("tool_calls")
            if isinstance(raw_calls, list):
                calls.extend(raw for raw in raw_calls if isinstance(raw, dict))
        return calls

    def _parse_tool_call(self, raw_call: dict[str, Any]) -> ModelToolCall:
        function = raw_call.get("function", {}) or {}
        raw_arguments = function.get("arguments", {})
        if isinstance(raw_arguments, str):
            try:
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

    def _blocked_chat_result(self, assessment: CloudSafetyAssessment) -> ModelChatResult:
        return ModelChatResult(
            text=self._privacy_block_message(assessment),
            model=self.model_name,
            provider="cloudflare",
            raw={
                "privacy_gate": {
                    "allowed": assessment.allowed,
                    "risk_level": assessment.risk_level,
                    "summary": assessment.summary,
                    "findings": [
                        {
                            "code": finding.code,
                            "severity": finding.severity,
                            "message": finding.message,
                        }
                        for finding in assessment.findings
                    ],
                }
            },
        )

    def _privacy_block_message(self, assessment: CloudSafetyAssessment) -> str:
        details = "; ".join(f.message for f in assessment.findings[:3])
        suffix = f" Findings: {details}" if details else ""
        return f"[Cloudflare blocked by privacy gate: {assessment.summary}{suffix}]"

    def _extract_model_ids(self, raw: Any) -> tuple[str, ...]:
        values: set[str] = set()

        def walk(value: Any) -> None:
            if isinstance(value, dict):
                for key in ("id", "name", "model"):
                    item = value.get(key)
                    if isinstance(item, str) and item:
                        values.add(item)
                for item in value.values():
                    walk(item)
            elif isinstance(value, list):
                for item in value:
                    walk(item)

        walk(raw)
        return tuple(sorted(values))

    def _raise_for_status_with_details(self, response: requests.Response) -> None:
        try:
            response.raise_for_status()
        except requests.HTTPError as error:
            detail = self._response_error_detail(response)
            if detail:
                raise requests.HTTPError(
                    f"{error}. Cloudflare error: {detail}",
                    response=response,
                ) from error
            raise

    def _response_error_detail(self, response: requests.Response) -> str:
        try:
            payload = response.json()
        except (TypeError, ValueError):
            payload = None

        if isinstance(payload, dict):
            errors = payload.get("errors")
            if isinstance(errors, list) and errors:
                messages = []
                for item in errors[:3]:
                    if isinstance(item, dict):
                        messages.append(str(item.get("message", item)))
                    else:
                        messages.append(str(item))
                return "; ".join(messages)
            error = payload.get("error")
            if error:
                return str(error)

        text = str(getattr(response, "text", "") or "").strip()
        return text[:500]
