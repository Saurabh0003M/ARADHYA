# Smart API Model Router

This package implements a capability-aware model router for multi-LLM systems.
It is intentionally provider-agnostic: the router chooses the model, records
telemetry, and calls an injected async `ModelInvoker`. A minimal
OpenAI-compatible invoker is included for providers that expose
`/chat/completions`.

## What It Improves

The existing FreeLLMAPI router in this repo already has useful production
behavior: static fallback order, per-key round-robin, rate-limit cooldowns,
sticky sessions, and request logging. Its weak spot is that `auto` routing is
mostly catalog priority plus availability. It does not classify request intent,
route by capability group, or compute capability-specific model scores from
recent telemetry.

This router adds:

- Capability taxonomy: `reasoning`, `coding`, `summarization`,
  `creative_writing`, `vision`, `fast_response`, `long_context`
- Model capability profiles in `config.json`
- Keyword request classification with optional `task_hint`
- Selectable routing strategies
- Per-attempt SQLite telemetry in `model_calls`
- Adaptive scoring by capability group

## Reference Approaches

- LiteLLM Router: fallback, retry, cooldown, and load-balancing primitives.
  This implementation keeps those production basics but makes the first model
  choice capability-aware.
- RouteLLM: learns routing from preference data and routes by query complexity.
  This implementation uses a simpler deterministic classifier so it can run
  locally without training data.
- Portkey gateway: composable fallback behavior and retry triggers. This router
  uses per-attempt fallback on retryable provider errors.
- FloTorch-style complexity tiers: prompts are grouped by task/complexity before
  model choice. This router applies that idea through capability groups.

## Core Algorithm

1. Classify the request from `task_hint`, image payloads, keywords, and length.
2. Map `task_type -> capability_group`.
3. Filter enabled models that meet the capability group.
4. Rank candidates using the selected strategy.
5. Invoke the first candidate.
6. On retryable failure, log the failed attempt, degrade its availability score,
   and try the next candidate.
7. Log the successful attempt with request id, model, provider, task, tokens,
   and latency.

Latency is measured only around the provider call. It does not include local
classification, scoring, fallback setup, or any exposed provider thinking-time
metadata. For streaming integrations, record first-token latency; for
non-streaming integrations, record full-response latency.

## Strategies

- `adaptive_score`: highest live score first.
- `availability_first`: highest success rate in the last 24 hours.
- `latency_aware`: lowest average latency in the current hour, falling back to
  24-hour latency when needed.
- `fallback_chain`: static config priority order.
- `weighted_round_robin`: smooth weighted distribution inside the capability
  group.
- `cost_optimized`: cheapest model that meets the capability requirement.

Adaptive score:

```text
score = (success_rate_24h * 0.5)
      + (latency_score * 0.3)
      + (availability_now * 0.2)
```

`latency_score` is normalized as:

```text
1 / (1 + avg_latency_ms / latency_baseline_ms)
```

Repeated failures reduce `availability_now` and can put a model into a short
cooldown. Successes recover the score gradually.

Scores recalculate every `recalc_every_requests` requests or after
`recalc_interval_seconds`, whichever comes first.

## API Shape

Use `SmartModelRouter.handle_v1_chat(payload)` as the endpoint adapter for:

```text
POST /v1/chat
```

Example payload:

```json
{
  "messages": [{"role": "user", "content": "Debug this Python function"}],
  "task_hint": "coding",
  "routing_strategy": "adaptive_score"
}
```

The adapter returns:

```python
status_code, body, headers = await router.handle_v1_chat(payload)
```

Headers:

- `X-Model-Used`
- `X-Routing-Strategy`
- `X-Fallback-Count`

## How To Add A Model

Edit `config.json`:

1. Add a model entry to `models`.
2. Set `provider`, `model_id`, `base_url`, and `api_key_env`.
3. Fill `capabilities` with tier numbers. Tier `1` is strongest.
4. Add the model id to explicit `capability_groups` when you want strict
   grouping.
5. Set `priority`, `weight`, and estimated cost fields.

## Minimal Usage

```python
from pathlib import Path

from src.aradhya.smart_router import ChatRequest, SmartModelRouter

router = SmartModelRouter.from_config_file(
    Path("src/aradhya/smart_router/config.json"),
    Path("data/smart_router/model_calls.db"),
)
await router.initialize()

response = await router.chat(ChatRequest(
    messages=[{"role": "user", "content": "Summarize this in five bullets"}],
    task_hint="summarization",
))
print(response.headers["X-Model-Used"])
print(response.content)
```

For production, install `aiosqlite` so SQLite operations stay fully async.
Without it, the store falls back to `sqlite3` in a worker thread.
