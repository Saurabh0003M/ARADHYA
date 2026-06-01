"""OpenRouter provider — gives ARADHYA access to 15+ free cloud models.

OpenRouter exposes an OpenAI-compatible API, so this provider uses
the standard ``/chat/completions`` endpoint.  Any model listed on
openrouter.ai/models works, including free-tier entries.

Configuration lives in ``core/config/profile.local.json`` for local
machine-only choices. Keep secrets in the environment whenever possible::

    {
      "model": {
        "provider": "openrouter",
        "model_name": "google/gemma-4-31b-it:free",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "ARADHYA_OPENROUTER_API_KEY",
        "request_timeout_seconds": 120
      }
    }
"""

from __future__ import annotations

import json
import time
from typing import Any, Iterator

from loguru import logger
import requests

from src.aradhya.model_provider import (
    ModelChatResult,
    ModelHealth,
    ModelResult,
    ModelToolCall,
)
from src.aradhya.cloud_safety import CloudPrivacyGate, CloudSafetyAssessment
from src.aradhya.runtime_profile import ModelProfile


# ── Free model catalogue ──────────────────────────────────────────────
# Sorted by recommended use.  All $0/M input+output as of May 2026.

FREE_MODELS: dict[str, dict[str, Any]] = {
    # ── Heavy reasoning (use for complex tasks, digestion)
    "deepseek/deepseek-v4-flash:free": {
        "context": 1_050_000,
        "label": "DeepSeek V4 Flash — fast coding & reasoning",
        "tier": "heavy",
    },
    "nvidia/nemotron-3-super-120b-a12b:free": {
        "context": 1_000_000,
        "label": "NVIDIA Nemotron 3 Super 120B — complex reasoning",
        "tier": "heavy",
    },
    "openai/gpt-oss-120b:free": {
        "context": 131_000,
        "label": "OpenAI gpt-oss-120b — general purpose MoE",
        "tier": "heavy",
    },
    "nousresearch/hermes-3-llama-3.1-405b:free": {
        "context": 128_000,
        "label": "Hermes 3 405B — uncensored, tool-capable",
        "tier": "heavy",
    },
    # ── Medium (good balance of speed + quality)
    "google/gemma-4-31b-it:free": {
        "context": 262_000,
        "label": "Google Gemma 4 31B — multimodal, 140+ languages",
        "tier": "medium",
    },
    "qwen/qwen3-coder:free": {
        "context": 262_000,
        "label": "Qwen 3 Coder — coding specialist",
        "tier": "medium",
    },
    "minimax/minimax-m2.5:free": {
        "context": 205_000,
        "label": "MiniMax M2.5 — SWE-bench 80.2%",
        "tier": "medium",
    },
    "poolside/laguna-m.1:free": {
        "context": 131_000,
        "label": "Poolside Laguna M.1 — coding agent",
        "tier": "medium",
    },
    "meta-llama/llama-3.3-70b-instruct:free": {
        "context": 128_000,
        "label": "Llama 3.3 70B — Meta's flagship open model",
        "tier": "medium",
    },
    "arcee-ai/trinity-large-thinking:free": {
        "context": 262_000,
        "label": "Arcee Trinity Large — chain-of-thought reasoning",
        "tier": "medium",
    },
    # ── Light (fast, good for simple queries)
    "nvidia/nemotron-3-nano-30b-a3b:free": {
        "context": 256_000,
        "label": "NVIDIA Nemotron 3 Nano 30B — efficient",
        "tier": "light",
    },
    "qwen/qwen3-next-80b-a3b-instruct:free": {
        "context": 128_000,
        "label": "Qwen 3 Next 80B — fast instruct",
        "tier": "light",
    },
    "openai/gpt-oss-20b:free": {
        "context": 131_000,
        "label": "OpenAI gpt-oss-20b — low-latency MoE",
        "tier": "light",
    },
    "nvidia/nemotron-nano-9b-v2:free": {
        "context": 128_000,
        "label": "NVIDIA Nemotron Nano 9B v2 — fastest",
        "tier": "light",
    },
}

DEFAULT_MODEL = "google/gemma-4-31b-it:free"

# How many fallback models to try before giving up.
_MAX_FALLBACK_ATTEMPTS = 4


class OpenRouterTextModelProvider:
    """OpenRouter-backed provider using the OpenAI-compatible chat API."""

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

        api_key = getattr(profile, "api_key", "") or ""
        self.api_key = api_key

        base_url = profile.base_url or "https://openrouter.ai/api/v1"
        self.base_url = base_url.rstrip("/")

        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/aradhya-ai/aradhya",
            "X-Title": "Aradhya OI",
        })

    # ── Health ─────────────────────────────────────────────────────────

    def health_check(self) -> ModelHealth:
        now = time.monotonic()
        if self._cached_health is not None:
            cached_at, cached_health = self._cached_health
            if now - cached_at <= self._health_cache_ttl_seconds:
                return cached_health

        if not self.api_key:
            health = ModelHealth(
                reachable=False,
                ready=False,
                provider="openrouter",
                configured_model=self.profile.model_name,
                available_models=tuple(),
                message=(
                    "No API key configured. Set ARADHYA_OPENROUTER_API_KEY "
                    "or an ignored profile.local.json model.api_key."
                ),
            )
            self._cached_health = (now, health)
            return health

        try:
            response = self.session.get(
                f"{self.base_url}/models",
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            model_ids = tuple(
                m.get("id", "") for m in data.get("data", [])
            )
            ready = self.profile.model_name in model_ids
            message = (
                f"Ready — {self.profile.model_name}"
                if ready
                else f"Model {self.profile.model_name} not found on OpenRouter."
            )
        except Exception as e:
            health = ModelHealth(
                reachable=False,
                ready=False,
                provider="openrouter",
                configured_model=self.profile.model_name,
                available_models=tuple(),
                message=f"OpenRouter unreachable: {e}",
            )
            self._cached_health = (now, health)
            return health

        health = ModelHealth(
            reachable=True,
            ready=ready,
            provider="openrouter",
            configured_model=self.profile.model_name,
            available_models=model_ids[:20],  # Only cache top 20
            message=message,
        )
        self._cached_health = (now, health)
        return health

    # ── Generate (text completion style) ───────────────────────────────

    def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
    ) -> ModelResult:
        messages = []
        if system_prompt or self.profile.system_prompt:
            messages.append({"role": "system", "content": system_prompt or self.profile.system_prompt})
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
        messages = []
        if system_prompt or self.profile.system_prompt:
            messages.append({"role": "system", "content": system_prompt or self.profile.system_prompt})
        messages.append({"role": "user", "content": prompt})
        yield from self.chat_stream(messages)

    # ── Chat (OpenAI-compatible) ───────────────────────────────────────

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        system_prompt: str | None = None,
    ) -> ModelChatResult:
        logger.debug(
            "OpenRouter chat: model={}, msgs={}, tools={}",
            self.profile.model_name,
            len(messages),
            len(tools or []),
        )

        chat_messages = list(messages)
        if system_prompt:
            chat_messages = [{"role": "system", "content": system_prompt}] + chat_messages

        assessment = self.privacy_gate.assess_messages(
            chat_messages,
            source="OpenRouter chat",
        )
        if not assessment.allowed:
            return self._blocked_chat_result(assessment)

        payload: dict[str, Any] = {
            "model": self.profile.model_name,
            "messages": chat_messages,
        }
        if tools:
            # Forward ARADHYA's OpenAI-style tool definitions unchanged when
            # possible; older callers may still pass flat tool dictionaries.
            openai_tools = []
            for tool in tools:
                if tool.get("type") == "function" and isinstance(tool.get("function"), dict):
                    openai_tools.append(tool)
                else:
                    openai_tools.append({
                        "type": "function",
                        "function": {
                            "name": tool.get("name", ""),
                            "description": tool.get("description", ""),
                            "parameters": tool.get("parameters", {}),
                        },
                    })
            payload["tools"] = openai_tools

        # Try primary model, then fallbacks on 429
        models_to_try = [payload["model"]] + self._get_fallback_models(payload["model"])

        last_error = ""
        for model_name in models_to_try[:1 + _MAX_FALLBACK_ATTEMPTS]:
            payload["model"] = model_name
            try:
                response = self.session.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    timeout=self.profile.request_timeout_seconds,
                )
                response.raise_for_status()
                break  # Success — exit retry loop
            except requests.HTTPError as e:
                status_code = getattr(response, "status_code", 0)
                error_detail = ""
                try:
                    error_detail = response.json().get("error", {}).get("message", "")
                except Exception:
                    pass
                last_error = error_detail or str(e)

                if status_code == 429 and model_name != models_to_try[-1]:
                    logger.warning(
                        "Model {} returned 429, trying next fallback...",
                        model_name,
                    )
                    continue  # Try next model

                logger.error("OpenRouter request failed: {}", e)
                return ModelChatResult(
                    text=f"[OpenRouter error: {last_error}]",
                    model=model_name,
                    provider="openrouter",
                    raw={},
                )
            except requests.RequestException as e:
                return ModelChatResult(
                    text=f"[OpenRouter unreachable: {e}]",
                    model=model_name,
                    provider="openrouter",
                    raw={},
                )
        else:
            # All models exhausted
            return ModelChatResult(
                text=(
                    f"[All free models are rate-limited right now. "
                    f"Last error: {last_error}. Try again in 30 seconds.]"
                ),
                model=self.profile.model_name,
                provider="openrouter",
                raw={},
            )

        raw = response.json()
        choice = (raw.get("choices") or [{}])[0]
        message = choice.get("message", {})

        # Parse tool calls if present
        raw_tool_calls = message.get("tool_calls") or []
        tool_calls = tuple(
            self._parse_tool_call(tc) for tc in raw_tool_calls
        )

        return ModelChatResult(
            text=str(message.get("content") or "").strip(),
            model=raw.get("model", self.profile.model_name),
            provider="openrouter",
            raw=raw,
            tool_calls=tool_calls,
        )

    def chat_stream(
        self,
        messages: list[dict[str, Any]],
        *,
        system_prompt: str | None = None,
    ) -> Iterator[str]:
        logger.debug("OpenRouter streaming chat: model={}", self.profile.model_name)

        chat_messages = list(messages)
        if system_prompt:
            chat_messages = [{"role": "system", "content": system_prompt}] + chat_messages

        assessment = self.privacy_gate.assess_messages(
            chat_messages,
            source="OpenRouter stream",
        )
        if not assessment.allowed:
            yield self._privacy_block_message(assessment)
            return

        payload: dict[str, Any] = {
            "model": self.profile.model_name,
            "messages": chat_messages,
            "stream": True,
        }

        # Try primary model, then fallbacks on 429
        models_to_try = [payload["model"]] + self._get_fallback_models(payload["model"])
        response = None
        used_model = payload["model"]

        for model_name in models_to_try[:1 + _MAX_FALLBACK_ATTEMPTS]:
            payload["model"] = model_name
            try:
                response = self.session.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    timeout=self.profile.request_timeout_seconds,
                    stream=True,
                )
                response.raise_for_status()
                used_model = model_name
                break
            except requests.HTTPError:
                status_code = getattr(response, "status_code", 0)
                if status_code == 429 and model_name != models_to_try[-1]:
                    logger.warning(
                        "Stream: {} returned 429, trying next fallback...",
                        model_name,
                    )
                    continue
                yield f"[OpenRouter stream error: {status_code} for {model_name}]"
                return
            except Exception as e:
                yield f"[OpenRouter stream error: {e}]"
                return
        else:
            yield "[All free models are rate-limited. Try again in 30 seconds.]"
            return

        if used_model != self.profile.model_name:
            yield f"[Routed to {used_model} - primary model was rate-limited]\n\n"

        # Stream with safety valve — truncate runaway/gibberish responses
        total_chars = 0
        max_stream_chars = 4000  # Prevent garbage floods from broken models

        for line in response.iter_lines():
            if not line:
                continue
            text = line.decode("utf-8", errors="replace")
            if text.startswith("data: "):
                text = text[6:]
            if text.strip() == "[DONE]":
                break
            try:
                chunk = json.loads(text)
                delta = (chunk.get("choices") or [{}])[0].get("delta", {})
                content = delta.get("content")
                if content:
                    total_chars += len(content)
                    if total_chars > max_stream_chars:
                        yield "\n\n[Response truncated — model exceeded safe length]"
                        logger.warning(
                            "Stream from {} truncated at {} chars (safety valve)",
                            used_model, total_chars,
                        )
                        break
                    yield content
            except (json.JSONDecodeError, IndexError):
                continue

    # ── Failover ────────────────────────────────────────────────────────

    def _get_fallback_models(self, primary: str) -> list[str]:
        """Return a list of free fallback models, excluding the primary."""
        return [
            model_id for model_id in FREE_MODELS
            if model_id != primary
        ]

    # ── Helpers ─────────────────────────────────────────────────────────

    def _parse_tool_call(self, raw_call: dict[str, Any]) -> ModelToolCall:
        function = raw_call.get("function", {})
        raw_args = function.get("arguments", "{}")
        if isinstance(raw_args, str):
            try:
                arguments = json.loads(raw_args)
            except (json.JSONDecodeError, TypeError):
                arguments = {}
        elif isinstance(raw_args, dict):
            arguments = raw_args
        else:
            arguments = {}

        return ModelToolCall(
            name=str(function.get("name", "")),
            arguments=arguments,
            id=str(raw_call.get("id", f"tc_{time.time_ns()}")),
        )

    def _blocked_chat_result(self, assessment: CloudSafetyAssessment) -> ModelChatResult:
        return ModelChatResult(
            text=self._privacy_block_message(assessment),
            model=self.profile.model_name,
            provider="openrouter",
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
        return f"[OpenRouter blocked by privacy gate: {assessment.summary}{suffix}]"

    def list_free_models(self) -> list[dict[str, str]]:
        """Return the curated list of free models for display."""
        return [
            {"id": model_id, **info}
            for model_id, info in FREE_MODELS.items()
        ]
