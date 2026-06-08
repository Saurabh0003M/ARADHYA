from __future__ import annotations

import sqlite3
from typing import Any

import pytest

from src.aradhya.smart_router.analytics import ModelCallTelemetry, SQLiteTelemetryStore
from src.aradhya.smart_router.router import (
    ChatRequest,
    ModelInvocationError,
    ModelInvocationResult,
    ModelProfile,
    RouterConfig,
    RoutingStrategy,
    SmartModelRouter,
)


class FakeInvoker:
    def __init__(self, failures: set[str] | None = None) -> None:
        self.failures = failures or set()
        self.calls: list[str] = []

    async def invoke(
        self,
        model: ModelProfile,
        messages: list[dict[str, Any]],
        parameters: dict[str, Any],
    ) -> ModelInvocationResult:
        self.calls.append(model.model_id)
        if model.model_id in self.failures:
            raise ModelInvocationError("rate limited", error_code="429", retryable=True)
        return ModelInvocationResult(
            content=f"ok:{model.model_id}",
            raw={"model": model.model_id},
            tokens_in=7,
            tokens_out=3,
            latency_ms=25,
        )


def build_config() -> RouterConfig:
    return RouterConfig.model_validate(
        {
            "max_fallbacks": 2,
            "recalc_every_requests": 2,
            "recalc_interval_seconds": 900,
            "latency_baseline_ms": 100,
            "task_map": {
                "reasoning": "reasoning_tier_1",
                "coding": "coding_tier_1",
                "summarization": "summarization_tier_1",
                "fast_response": "fast_response_tier_1",
                "creative_writing": "reasoning_tier_1",
                "vision": "reasoning_tier_1",
                "long_context": "reasoning_tier_1",
            },
            "keyword_map": {
                "coding": ["debug", "python", "function"],
                "summarization": ["summarize"],
                "fast_response": ["quick"],
            },
            "capability_groups": [
                {
                    "name": "coding_tier_1",
                    "capability": "coding",
                    "max_tier": 1,
                    "model_ids": ["slow-coder", "fast-coder"],
                },
                {
                    "name": "summarization_tier_1",
                    "capability": "summarization",
                    "max_tier": 1,
                    "model_ids": ["cheap-summary", "fast-coder"],
                },
                {
                    "name": "fast_response_tier_1",
                    "capability": "fast_response",
                    "max_tier": 1,
                    "model_ids": ["fast-coder", "cheap-summary"],
                },
                {
                    "name": "reasoning_tier_1",
                    "capability": "reasoning",
                    "max_tier": 1,
                    "model_ids": ["slow-coder"],
                },
            ],
            "models": [
                {
                    "model_id": "slow-coder",
                    "provider": "test",
                    "priority": 10,
                    "weight": 1,
                    "cost_per_1k_input": 0.03,
                    "cost_per_1k_output": 0.06,
                    "capabilities": {"coding": 1, "reasoning": 1, "summarization": 2},
                },
                {
                    "model_id": "fast-coder",
                    "provider": "test",
                    "priority": 20,
                    "weight": 3,
                    "cost_per_1k_input": 0.01,
                    "cost_per_1k_output": 0.02,
                    "capabilities": {"coding": 1, "summarization": 1, "fast_response": 1},
                },
                {
                    "model_id": "cheap-summary",
                    "provider": "test",
                    "priority": 30,
                    "weight": 2,
                    "cost_per_1k_input": 0.001,
                    "cost_per_1k_output": 0.002,
                    "capabilities": {"summarization": 1, "fast_response": 1},
                },
            ],
        }
    )


@pytest.mark.asyncio
async def test_coding_request_falls_back_and_records_attempts(tmp_path):
    store = SQLiteTelemetryStore(tmp_path / "router.db")
    router = SmartModelRouter(build_config(), store, FakeInvoker({"slow-coder"}))
    await router.initialize()

    response = await router.chat(
        ChatRequest(
            messages=[{"role": "user", "content": "Debug this Python function"}],
            routing_strategy=RoutingStrategy.FALLBACK_CHAIN,
        )
    )

    assert response.model_used == "fast-coder"
    assert response.fallback_count == 1
    assert response.headers["X-Model-Used"] == "fast-coder"
    assert response.headers["X-Fallback-Count"] == "1"

    with sqlite3.connect(tmp_path / "router.db") as connection:
        rows = connection.execute(
            """
            SELECT request_id, model_id, capability_group, task_type, success, error_code,
                   tokens_in, tokens_out
            FROM model_calls
            ORDER BY id
            """
        ).fetchall()

    assert [row[1] for row in rows] == ["slow-coder", "fast-coder"]
    assert rows[0][2] == "coding_tier_1"
    assert rows[0][3] == "coding"
    assert rows[0][4] == 0
    assert rows[0][5] == "429"
    assert rows[1][4] == 1
    assert rows[1][6:] == (7, 3)


@pytest.mark.asyncio
async def test_latency_aware_uses_current_hour_metrics(tmp_path):
    store = SQLiteTelemetryStore(tmp_path / "router.db")
    await store.init()
    await store.record_call(
        ModelCallTelemetry(
            request_id="r1",
            model_id="slow-coder",
            provider="test",
            capability_group="coding_tier_1",
            task_type="coding",
            latency_ms=800,
            success=True,
        )
    )
    await store.record_call(
        ModelCallTelemetry(
            request_id="r2",
            model_id="fast-coder",
            provider="test",
            capability_group="coding_tier_1",
            task_type="coding",
            latency_ms=100,
            success=True,
        )
    )
    router = SmartModelRouter(build_config(), store, FakeInvoker())

    decision = await router.decide(
        ChatRequest(
            messages=[{"role": "user", "content": "debug code"}],
            routing_strategy=RoutingStrategy.LATENCY_AWARE,
        )
    )

    assert [model.model_id for model in decision.candidates[:2]] == [
        "fast-coder",
        "slow-coder",
    ]


@pytest.mark.asyncio
async def test_cost_optimized_prefers_cheapest_capable_model(tmp_path):
    store = SQLiteTelemetryStore(tmp_path / "router.db")
    router = SmartModelRouter(build_config(), store, FakeInvoker())
    await router.initialize()

    response = await router.chat(
        ChatRequest(
            messages=[{"role": "user", "content": "summarize this document"}],
            routing_strategy=RoutingStrategy.COST_OPTIMIZED,
        )
    )

    assert response.model_used == "cheap-summary"
    assert response.task_type == "summarization"


@pytest.mark.asyncio
async def test_weighted_round_robin_distributes_by_weight(tmp_path):
    store = SQLiteTelemetryStore(tmp_path / "router.db")
    router = SmartModelRouter(build_config(), store, FakeInvoker())
    await router.initialize()

    selected = []
    for _ in range(4):
        decision = await router.decide(
            ChatRequest(
                messages=[{"role": "user", "content": "quick reply"}],
                routing_strategy=RoutingStrategy.WEIGHTED_ROUND_ROBIN,
            )
        )
        selected.append(decision.candidates[0].model_id)

    assert selected.count("fast-coder") > selected.count("cheap-summary")
