"""Smart capability-aware router for multi-LLM chat requests."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timedelta
from enum import Enum
import json
from pathlib import Path
import time
from typing import Any, Protocol
from urllib import error as url_error
from urllib import request as url_request
import uuid

from pydantic import BaseModel, Field, field_validator, model_validator

from src.aradhya.smart_router.analytics import (
    ModelCallTelemetry,
    ModelMetricSnapshot,
    ModelScore,
    SQLiteTelemetryStore,
    utc_now,
)


class Capability(str, Enum):
    REASONING = "reasoning"
    CODING = "coding"
    SUMMARIZATION = "summarization"
    CREATIVE_WRITING = "creative_writing"
    VISION = "vision"
    FAST_RESPONSE = "fast_response"
    LONG_CONTEXT = "long_context"


class RoutingStrategy(str, Enum):
    ADAPTIVE_SCORE = "adaptive_score"
    AVAILABILITY_FIRST = "availability_first"
    LATENCY_AWARE = "latency_aware"
    FALLBACK_CHAIN = "fallback_chain"
    WEIGHTED_ROUND_ROBIN = "weighted_round_robin"
    COST_OPTIMIZED = "cost_optimized"


Message = dict[str, Any]


class ModelProfile(BaseModel):
    """Model metadata loaded from ``config.json``."""

    model_id: str
    provider: str
    display_name: str = ""
    base_url: str = ""
    api_key_env: str = ""
    enabled: bool = True
    priority: int = 100
    weight: float = Field(default=1.0, ge=0.0)
    cost_per_1k_input: float = Field(default=0.0, ge=0.0)
    cost_per_1k_output: float = Field(default=0.0, ge=0.0)
    context_window: int = Field(default=0, ge=0)
    capabilities: dict[Capability, int] = Field(default_factory=dict)
    groups: list[str] = Field(default_factory=list)
    notes: str = ""

    @field_validator("model_id", "provider")
    @classmethod
    def _required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must be non-empty")
        return stripped

    @model_validator(mode="after")
    def _normalize_display_name(self) -> "ModelProfile":
        if not self.display_name:
            self.display_name = self.model_id
        return self

    def cost_estimate(self, tokens_in: int = 1000, tokens_out: int = 1000) -> float:
        return (
            (tokens_in / 1000.0 * self.cost_per_1k_input)
            + (tokens_out / 1000.0 * self.cost_per_1k_output)
        )


class CapabilityGroupConfig(BaseModel):
    name: str
    capability: Capability
    max_tier: int = Field(default=2, ge=1)
    model_ids: list[str] = Field(default_factory=list)
    description: str = ""

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("capability group name must be non-empty")
        return stripped


class RouterConfig(BaseModel):
    """Validated smart router registry."""

    capabilities: list[Capability] = Field(
        default_factory=lambda: [
            Capability.REASONING,
            Capability.CODING,
            Capability.SUMMARIZATION,
            Capability.CREATIVE_WRITING,
            Capability.VISION,
            Capability.FAST_RESPONSE,
            Capability.LONG_CONTEXT,
        ]
    )
    capability_groups: list[CapabilityGroupConfig]
    task_map: dict[str, str]
    keyword_map: dict[str, list[str]] = Field(default_factory=dict)
    models: list[ModelProfile]
    max_fallbacks: int = Field(default=4, ge=0)
    recalc_every_requests: int = Field(default=25, ge=1)
    recalc_interval_seconds: int = Field(default=900, ge=1)
    latency_baseline_ms: int = Field(default=4000, ge=1)

    @model_validator(mode="after")
    def _validate_references(self) -> "RouterConfig":
        group_names = {group.name for group in self.capability_groups}
        unknown_groups = set(self.task_map.values()) - group_names
        if unknown_groups:
            raise ValueError(f"task_map references unknown groups: {sorted(unknown_groups)}")

        model_ids = {model.model_id for model in self.models}
        for group in self.capability_groups:
            unknown_models = set(group.model_ids) - model_ids
            if unknown_models:
                raise ValueError(
                    f"group {group.name} references unknown models: {sorted(unknown_models)}"
                )
        return self

    @classmethod
    def load(cls, path: str | Path) -> "RouterConfig":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.model_validate(payload)


class ChatRequest(BaseModel):
    messages: list[Message]
    task_hint: str | None = None
    routing_strategy: RoutingStrategy = RoutingStrategy.ADAPTIVE_SCORE
    request_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    parameters: dict[str, Any] = Field(default_factory=dict)

    @field_validator("messages")
    @classmethod
    def _has_messages(cls, value: list[Message]) -> list[Message]:
        if not value:
            raise ValueError("messages must contain at least one message")
        return value


class ModelInvocationResult(BaseModel):
    content: str = ""
    raw: dict[str, Any] = Field(default_factory=dict)
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int | None = None


class RoutedChatResponse(BaseModel):
    request_id: str
    content: str
    raw: dict[str, Any] = Field(default_factory=dict)
    model_used: str
    provider: str
    capability_group: str
    task_type: str
    routing_strategy: RoutingStrategy
    fallback_count: int
    headers: dict[str, str]


class ClassifiedTask(BaseModel):
    task_type: str
    capability_group: str


class RoutingDecision(BaseModel):
    request_id: str
    task_type: str
    capability_group: str
    strategy: RoutingStrategy
    candidates: list[ModelProfile]


class ModelInvocationError(Exception):
    """Provider call failed."""

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "provider_error",
        retryable: bool = True,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.retryable = retryable


class RoutingError(Exception):
    """No eligible model could satisfy the request."""


class ModelInvoker(Protocol):
    async def invoke(
        self,
        model: ModelProfile,
        messages: list[Message],
        parameters: dict[str, Any],
    ) -> ModelInvocationResult:
        """Call one provider/model pair."""


class OpenAICompatibleInvoker:
    """Minimal OpenAI-compatible HTTP invoker.

    This keeps the router usable without adding ``httpx`` as a hard dependency.
    The call is async at the router boundary and uses a worker thread for the
    blocking stdlib HTTP request.
    """

    def __init__(self, api_keys: dict[str, str] | None = None, timeout_seconds: int = 60) -> None:
        self.api_keys = api_keys or {}
        self.timeout_seconds = timeout_seconds

    async def invoke(
        self,
        model: ModelProfile,
        messages: list[Message],
        parameters: dict[str, Any],
    ) -> ModelInvocationResult:
        return await asyncio.to_thread(self._invoke_sync, model, messages, parameters)

    def _invoke_sync(
        self,
        model: ModelProfile,
        messages: list[Message],
        parameters: dict[str, Any],
    ) -> ModelInvocationResult:
        if not model.base_url:
            raise ModelInvocationError(
                f"Model {model.model_id} has no base_url configured.",
                error_code="missing_base_url",
                retryable=False,
            )

        api_key = self._resolve_api_key(model)
        if not api_key:
            raise ModelInvocationError(
                f"Missing API key for provider {model.provider}.",
                error_code="missing_api_key",
                retryable=False,
            )

        payload = {
            "model": model.model_id,
            "messages": messages,
            **parameters,
        }
        body = json.dumps(payload).encode("utf-8")
        endpoint = f"{model.base_url.rstrip('/')}/chat/completions"
        request = url_request.Request(
            endpoint,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )

        start = time.perf_counter()
        try:
            with url_request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = json.loads(response.read().decode("utf-8"))
        except url_error.HTTPError as error:
            retryable = error.code in {408, 409, 413, 429, 500, 502, 503, 504}
            raise ModelInvocationError(
                f"HTTP {error.code} from {model.provider}/{model.model_id}",
                error_code=str(error.code),
                retryable=retryable,
            ) from error
        except (OSError, TimeoutError, json.JSONDecodeError) as error:
            raise ModelInvocationError(
                str(error),
                error_code="transport_error",
                retryable=True,
            ) from error

        latency_ms = int((time.perf_counter() - start) * 1000)
        choice = (raw.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        usage = raw.get("usage") or {}
        return ModelInvocationResult(
            content=str(message.get("content") or ""),
            raw=raw,
            tokens_in=int(usage.get("prompt_tokens") or 0),
            tokens_out=int(usage.get("completion_tokens") or 0),
            latency_ms=latency_ms,
        )

    def _resolve_api_key(self, model: ModelProfile) -> str:
        if model.provider in self.api_keys:
            return self.api_keys[model.provider]
        if model.api_key_env:
            import os

            return os.environ.get(model.api_key_env, "")
        return ""


class ModelRegistry:
    """Indexed access to validated model config."""

    def __init__(self, config: RouterConfig) -> None:
        self.config = config
        self.models_by_id = {model.model_id: model for model in config.models}
        self.groups_by_name = {group.name: group for group in config.capability_groups}

    def enabled_models(self) -> list[ModelProfile]:
        return [model for model in self.config.models if model.enabled]

    def group(self, name: str) -> CapabilityGroupConfig:
        try:
            return self.groups_by_name[name]
        except KeyError as error:
            raise RoutingError(f"Unknown capability group: {name}") from error


class CapabilityGrouper:
    """Find eligible models for a required capability group."""

    def __init__(self, registry: ModelRegistry) -> None:
        self.registry = registry

    def eligible_models(self, capability_group: str) -> list[ModelProfile]:
        group = self.registry.group(capability_group)
        explicitly_allowed = set(group.model_ids)
        models: list[ModelProfile] = []
        for model in self.registry.enabled_models():
            if explicitly_allowed and model.model_id not in explicitly_allowed:
                continue
            if capability_group in model.groups:
                models.append(model)
                continue
            tier = model.capabilities.get(group.capability)
            if tier is not None and tier <= group.max_tier:
                models.append(model)

        return sorted(models, key=lambda item: (item.priority, item.provider, item.model_id))


class RequestClassifier:
    """Lightweight keyword classifier for task-to-capability routing."""

    def __init__(self, config: RouterConfig) -> None:
        self.config = config

    def classify(self, messages: list[Message], task_hint: str | None = None) -> ClassifiedTask:
        hinted = self._normalize_task(task_hint)
        if hinted:
            return self._classified(hinted)

        if self._has_vision_payload(messages):
            return self._classified(Capability.VISION.value)

        text = self._messages_text(messages)
        lowered = text.lower()
        keyword_scores: dict[str, int] = {}
        for task_type, keywords in self.config.keyword_map.items():
            keyword_scores[task_type] = sum(1 for keyword in keywords if keyword.lower() in lowered)

        if keyword_scores:
            task_type, score = max(keyword_scores.items(), key=lambda item: item[1])
            if score > 0:
                return self._classified(task_type)

        if len(text) > 12000:
            return self._classified(Capability.LONG_CONTEXT.value)

        return self._classified(Capability.REASONING.value)

    def _classified(self, task_type: str) -> ClassifiedTask:
        normalized = self._normalize_task(task_type) or Capability.REASONING.value
        group = self.config.task_map.get(normalized)
        if group is None and normalized in self.config.task_map.values():
            group = normalized
        if group is None:
            group = self.config.task_map[Capability.REASONING.value]
            normalized = Capability.REASONING.value
        return ClassifiedTask(task_type=normalized, capability_group=group)

    def _normalize_task(self, value: str | None) -> str | None:
        if not value:
            return None
        normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
        if normalized in self.config.task_map:
            return normalized
        if normalized in self.config.task_map.values():
            return normalized
        return None

    def _messages_text(self, messages: list[Message]) -> str:
        chunks: list[str] = []
        for message in messages:
            content = message.get("content", "")
            if isinstance(content, str):
                chunks.append(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        text = block.get("text")
                        if isinstance(text, str):
                            chunks.append(text)
        return "\n".join(chunks)

    def _has_vision_payload(self, messages: list[Message]) -> bool:
        for message in messages:
            content = message.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                block_type = str(block.get("type", "")).lower()
                if "image" in block_type or "vision" in block_type:
                    return True
                if "image_url" in block or "input_image" in block:
                    return True
        return False


class ScoringEngine:
    """Adaptive score cache and in-memory availability degradation."""

    def __init__(self, config: RouterConfig, telemetry: SQLiteTelemetryStore) -> None:
        self.config = config
        self.telemetry = telemetry
        self._cache: dict[str, tuple[datetime, dict[str, ModelScore]]] = {}
        self._request_counter = 0
        self._failure_counts: dict[str, int] = defaultdict(int)
        self._cooldowns: dict[str, datetime] = {}

    def note_request(self) -> None:
        self._request_counter += 1

    async def scores_for(
        self,
        capability_group: str,
        models: list[ModelProfile],
        *,
        force: bool = False,
    ) -> dict[str, ModelScore]:
        model_ids = [model.model_id for model in models]
        cached = self._cache.get(capability_group)
        now = utc_now()
        if cached and not force:
            calculated_at, scores = cached
            still_fresh = (
                (now - calculated_at).total_seconds() < self.config.recalc_interval_seconds
            )
            request_gate = self._request_counter % self.config.recalc_every_requests != 0
            if still_fresh and request_gate and set(scores) >= set(model_ids):
                return {model_id: scores[model_id] for model_id in model_ids}

        availability = {
            model.model_id: self.availability_now(model.model_id, now=now)
            for model in models
        }
        scores = await self.telemetry.recalculate_scores(
            model_ids,
            capability_group,
            availability_now=availability,
            latency_baseline_ms=self.config.latency_baseline_ms,
            now=now,
        )
        self._cache[capability_group] = (now, scores)
        return scores

    def availability_now(self, model_id: str, *, now: datetime | None = None) -> float:
        stamp = now or utc_now()
        cooldown_until = self._cooldowns.get(model_id)
        if cooldown_until and stamp < cooldown_until:
            return 0.0
        failures = self._failure_counts.get(model_id, 0)
        return max(0.05, 1.0 - (failures * 0.2))

    def record_failure(self, model_id: str) -> None:
        failures = self._failure_counts[model_id] + 1
        self._failure_counts[model_id] = failures
        if failures >= 3:
            self._cooldowns[model_id] = utc_now() + timedelta(minutes=min(failures, 10))

    def record_success(self, model_id: str) -> None:
        failures = self._failure_counts.get(model_id, 0)
        if failures <= 1:
            self._failure_counts.pop(model_id, None)
            self._cooldowns.pop(model_id, None)
            return
        self._failure_counts[model_id] = failures - 1


class SmartModelRouter:
    """Classify requests, choose models, execute fallback, and log telemetry."""

    def __init__(
        self,
        config: RouterConfig,
        telemetry: SQLiteTelemetryStore,
        invoker: ModelInvoker | None = None,
    ) -> None:
        self.config = config
        self.registry = ModelRegistry(config)
        self.grouper = CapabilityGrouper(self.registry)
        self.classifier = RequestClassifier(config)
        self.telemetry = telemetry
        self.scoring = ScoringEngine(config, telemetry)
        self.invoker = invoker or OpenAICompatibleInvoker()
        self._weighted_state: dict[str, dict[str, float]] = defaultdict(dict)

    @classmethod
    def from_config_file(
        cls,
        config_path: str | Path,
        telemetry_db_path: str | Path,
        invoker: ModelInvoker | None = None,
    ) -> "SmartModelRouter":
        return cls(
            RouterConfig.load(config_path),
            SQLiteTelemetryStore(telemetry_db_path),
            invoker=invoker,
        )

    async def initialize(self) -> None:
        await self.telemetry.init()

    async def decide(self, request: ChatRequest) -> RoutingDecision:
        classified = self.classifier.classify(request.messages, request.task_hint)
        candidates = self.grouper.eligible_models(classified.capability_group)
        if not candidates:
            raise RoutingError(f"No enabled models for capability group {classified.capability_group}.")

        ordered = await self._ordered_candidates(
            request.routing_strategy,
            classified.capability_group,
            candidates,
        )
        return RoutingDecision(
            request_id=request.request_id,
            task_type=classified.task_type,
            capability_group=classified.capability_group,
            strategy=request.routing_strategy,
            candidates=ordered,
        )

    async def chat(self, request: ChatRequest) -> RoutedChatResponse:
        self.scoring.note_request()
        decision = await self.decide(request)
        attempts = decision.candidates[: self.config.max_fallbacks + 1]
        last_error: ModelInvocationError | None = None

        for fallback_count, model in enumerate(attempts):
            start = time.perf_counter()
            try:
                result = await self.invoker.invoke(model, request.messages, request.parameters)
                latency_ms = result.latency_ms
                if latency_ms is None:
                    latency_ms = int((time.perf_counter() - start) * 1000)
                await self._record_attempt(
                    request=request,
                    decision=decision,
                    model=model,
                    latency_ms=latency_ms,
                    success=True,
                    error_code=None,
                    tokens_in=result.tokens_in,
                    tokens_out=result.tokens_out,
                )
                self.scoring.record_success(model.model_id)
                headers = {
                    "X-Model-Used": model.model_id,
                    "X-Routing-Strategy": request.routing_strategy.value,
                    "X-Fallback-Count": str(fallback_count),
                }
                return RoutedChatResponse(
                    request_id=request.request_id,
                    content=result.content,
                    raw=result.raw,
                    model_used=model.model_id,
                    provider=model.provider,
                    capability_group=decision.capability_group,
                    task_type=decision.task_type,
                    routing_strategy=request.routing_strategy,
                    fallback_count=fallback_count,
                    headers=headers,
                )
            except ModelInvocationError as error:
                last_error = error
                latency_ms = int((time.perf_counter() - start) * 1000)
                await self._record_attempt(
                    request=request,
                    decision=decision,
                    model=model,
                    latency_ms=latency_ms,
                    success=False,
                    error_code=error.error_code,
                    tokens_in=0,
                    tokens_out=0,
                )
                self.scoring.record_failure(model.model_id)
                if not error.retryable:
                    break

        raise RoutingError(
            f"All eligible models failed for {decision.capability_group}. "
            f"Last error: {last_error.error_code if last_error else 'none'}"
        )

    async def handle_v1_chat(
        self,
        payload: dict[str, Any],
    ) -> tuple[int, dict[str, Any], dict[str, str]]:
        """Endpoint adapter for ``POST /v1/chat``.

        A web framework can call this method directly and return the tuple as
        ``status_code, JSON body, response headers``.
        """
        request = ChatRequest.model_validate(payload)
        try:
            response = await self.chat(request)
        except RoutingError as error:
            return 503, {"error": {"message": str(error), "type": "routing_error"}}, {}

        return (
            200,
            {
                "request_id": response.request_id,
                "model": response.model_used,
                "provider": response.provider,
                "capability_group": response.capability_group,
                "task_type": response.task_type,
                "content": response.content,
                "raw": response.raw,
            },
            response.headers,
        )

    async def _ordered_candidates(
        self,
        strategy: RoutingStrategy,
        capability_group: str,
        candidates: list[ModelProfile],
    ) -> list[ModelProfile]:
        if strategy == RoutingStrategy.FALLBACK_CHAIN:
            return list(candidates)

        if strategy == RoutingStrategy.WEIGHTED_ROUND_ROBIN:
            return self._weighted_round_robin_order(capability_group, candidates)

        if strategy == RoutingStrategy.COST_OPTIMIZED:
            return sorted(
                candidates,
                key=lambda model: (model.cost_estimate(), model.priority, model.model_id),
            )

        model_ids = [model.model_id for model in candidates]
        snapshots = await self.telemetry.metric_snapshots(model_ids, capability_group)

        if strategy == RoutingStrategy.AVAILABILITY_FIRST:
            return sorted(
                candidates,
                key=lambda model: (
                    -snapshots[model.model_id].success_rate_24h,
                    model.priority,
                    model.model_id,
                ),
            )

        if strategy == RoutingStrategy.LATENCY_AWARE:
            return sorted(
                candidates,
                key=lambda model: (
                    self._latency_sort_key(snapshots[model.model_id]),
                    model.priority,
                    model.model_id,
                ),
            )

        scores = await self.scoring.scores_for(capability_group, candidates)
        return sorted(
            candidates,
            key=lambda model: (-scores[model.model_id].score, model.priority, model.model_id),
        )

    def _weighted_round_robin_order(
        self,
        capability_group: str,
        candidates: list[ModelProfile],
    ) -> list[ModelProfile]:
        state = self._weighted_state[capability_group]
        total_weight = sum(max(model.weight, 0.0) for model in candidates) or 1.0
        by_id = {model.model_id: model for model in candidates}

        for model in candidates:
            state.setdefault(model.model_id, 0.0)
            state[model.model_id] += max(model.weight, 0.0)

        selected = max(candidates, key=lambda model: (state[model.model_id], -model.priority))
        state[selected.model_id] -= total_weight
        rest = [
            model for model in candidates
            if model.model_id != selected.model_id and model.model_id in by_id
        ]
        return [selected, *rest]

    @staticmethod
    def _latency_sort_key(snapshot: ModelMetricSnapshot) -> float:
        if snapshot.avg_latency_ms_current_hour is not None:
            return snapshot.avg_latency_ms_current_hour
        if snapshot.avg_latency_ms_24h is not None:
            return snapshot.avg_latency_ms_24h
        return float("inf")

    async def _record_attempt(
        self,
        *,
        request: ChatRequest,
        decision: RoutingDecision,
        model: ModelProfile,
        latency_ms: int,
        success: bool,
        error_code: str | None,
        tokens_in: int,
        tokens_out: int,
    ) -> None:
        await self.telemetry.record_call(
            ModelCallTelemetry(
                request_id=request.request_id,
                model_id=model.model_id,
                provider=model.provider,
                capability_group=decision.capability_group,
                task_type=decision.task_type,
                latency_ms=latency_ms,
                success=success,
                error_code=error_code,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
            )
        )
