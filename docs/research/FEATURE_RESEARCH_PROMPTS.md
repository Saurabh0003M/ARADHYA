# Feature Research Prompts for Deep-Search AIs

These prompts are designed to produce research that is usable inside this repo without exaggerating what big-tech systems have actually made public.

Use rules:

- Official sources first: official docs, official engineering blogs, official public repos, official sample code.
- If a mechanism is not public, say so directly.
- Distinguish `Source says` from `Inference`.
- Report time complexity before space complexity.
- Stay inside implemented Aradhya scope. Do not spend tokens on roadmap-only features such as browser operator or screen automation.
- Prefer mechanisms and code paths that map to `src/aradhya/assistant_indexer.py`, `src/aradhya/assistant_planner.py`, `src/aradhya/llm_planner.py`, `src/aradhya/voice_pipeline.py`, and `src/aradhya/voice_activation.py`.

## Output Contract

Ask the model to produce:

1. A short feature summary.
2. A markdown table with these exact columns:

   `feature`, `aradhya_component`, `current_mechanism`, `current_big_o`, `external_system`, `official_source`, `mechanism_summary`, `key_data_structures_or_apis`, `time_tradeoff`, `space_tradeoff`, `relevance_to_aradhya`, `adopt_decision`, `notes`

3. A final "Do not overclaim" section that lists any private or undocumented details the model refused to speculate about.

Required row rules:

- Every row must include at least one official source URL.
- Every external source must be tagged as `open implementation`, `official API only`, or `closed internal implementation`.
- Every row must end with one of: `adopt now`, `adapt later`, `watch`, `reject`.
- `notes` must contain both `Source says:` and `Inference:` labels.

## Master Prompt

```text
You are producing a repo-grounded research matrix for Aradhya, a local-first Windows assistant.

Goal:
- Compare implemented Aradhya mechanisms to how large official systems solve the same class of problem.
- Prioritize time complexity over space complexity.
- Do not propose runtime code changes directly. This is research output only.

Repo context:
- Local context engine: src/aradhya/assistant_indexer.py
- Planner boundary: src/aradhya/assistant_planner.py, src/aradhya/llm_planner.py
- Voice pipeline: src/aradhya/voice_pipeline.py, src/aradhya/voice_activation.py

Scope constraints:
- Include implemented features only.
- Exclude roadmap-only items such as browser operator and screen automation.
- Treat one-off executor heuristics such as opening security blogs as examples of execution boundaries, not standalone research targets.

Source policy:
- Use official sources first: official docs, official public repos, official sample code, official engineering wikis.
- If code is not public, label it as closed internal implementation.
- If only APIs are public, label it as official API only.
- If repo or wiki code is public, label it as open implementation.
- Do not cite forums, random blogs, or speculative articles unless explicitly asked.

Required comparison areas:
- Index vs scan
- Watcher vs crawl
- Exact-match hash vs prefix or delegated search
- Deduplication and event correlation
- On-device or private indexing
- Schema-constrained tool calls
- Explicit confirmation before action
- Batch vs streaming transcription
- Intermediate vs final transcript results

Required output:
1. A short feature summary.
2. A markdown table with these exact columns:
   feature | aradhya_component | current_mechanism | current_big_o | external_system | official_source | mechanism_summary | key_data_structures_or_apis | time_tradeoff | space_tradeoff | relevance_to_aradhya | adopt_decision | notes
3. A "Do not overclaim" section listing any implementation details that are not public.

Hard rules:
- Every row needs at least one official source URL.
- Every row must contain "Source says:" and "Inference:" inside notes.
- Time complexity discussion must appear before space complexity.
- If Aradhya already matches the external pattern, say that and mark the row as watch instead of inventing work.
- If a mechanism is not public, say "implementation not public" rather than guessing.
```

## Prompt Variant: Local Context Engine

```text
Focus only on Aradhya's implemented local context engine in src/aradhya/assistant_indexer.py.

Compare it against:
- Windows Search
- VS Code file watching and delegated search
- Meta Watchman
- Apple Spotlight and Core Spotlight APIs

Answer these questions:
- How do official systems avoid repeated full-tree scans?
- How do they represent searchable content or file metadata?
- How do they handle watch deduplication, overlapping roots, or project-root consolidation?
- How do they treat exact lookup versus broader text search?
- Which mechanisms are suitable for a local-first Windows Python app with current Aradhya constraints?

Required emphasis:
- P0 focus on full rescans, cache misses, named-path lookup, .txt density search, project heuristics, recent-game heuristics.
- Time complexity first, then space complexity.
- Strongly separate "adopt now" from "nice later".
```

## Prompt Variant: P0 Indexer Hotspot

```text
You are only allowed to analyze these Aradhya behaviors:
- refresh_if_stale
- _refresh_relevant_roots
- _lookup_named_paths
- _gather_name_candidates
- current .txt density counting

Compare those exact behaviors to official Windows Search, VS Code, and Watchman mechanisms.

Deliver:
- The 5 highest-confidence optimizations only
- For each, include:
  - current Aradhya behavior
  - official mechanism
  - why it reduces time complexity
  - why it is safe or unsafe
  - what should change first

Do not recommend tries, fuzzy indexes, or major architecture shifts unless you first prove why exact hits and miss amplification are not the main bottleneck.
```

## Prompt Variant: Planner and Safety Boundary

```text
Focus only on these Aradhya files:
- src/aradhya/assistant_planner.py
- src/aradhya/llm_planner.py
- src/aradhya/json_extractor.py
- src/aradhya/assistant_system_tools.py

Compare them against:
- OpenAI Structured Outputs
- OpenAI Function Calling
- Google Vertex AI Function Calling
- Apple App Intents confirmation flow

Questions to answer:
- How do official systems keep the model from directly executing side effects?
- How do strict schemas reduce malformed outputs?
- When should a system use deterministic routing before model fallback?
- What should remain explicit user confirmation even if structured tools are adopted?

Hard rule:
- Preserve Aradhya's current explicit confirmation semantics in every recommendation.
```

## Prompt Variant: Voice Pipeline

```text
Focus only on:
- src/aradhya/voice_pipeline.py
- src/aradhya/voice_activation.py
- src/aradhya/voice_transcriber.py

Compare them against:
- OpenAI Whisper
- Apple Speech / SpeechTranscriber
- Microsoft Speech SDK or Speech service

Questions to answer:
- How do official systems separate real-time, fast, and batch transcription modes?
- How do they expose intermediate versus final transcript results?
- How do they share underlying models or engines across multiple recognizers?
- Which ideas help Aradhya without violating its current local-first and confirmation-gated design?

Required output:
- Call out whether each official system supports on-device or local execution, server processing, or both.
- Separate throughput improvements from user-perceived latency improvements.
```

## Prompt Hygiene Checklist

Before sending any of the prompts above to a deep-search model, verify:

- The prompt includes the exact Aradhya files.
- The prompt asks for official URLs, not just brand names.
- The prompt requires `Source says:` and `Inference:`.
- The prompt asks for time complexity before space complexity.
- The prompt forbids guessing at private internal implementations.
