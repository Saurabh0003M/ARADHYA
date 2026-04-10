# Time-First Optimization Backlog

This backlog converts the research matrix into an implementation order.

Scope:

- No runtime changes are made in this phase.
- Scores are for prioritization only.
- Higher score is better on every axis.
- `implementation_risk_score` means "lower risk to land safely", so `5` is safer than `1`.

Current status note:

- The first P0 runtime pass has now landed:
  - `B1` exact-match fast index
  - `B2` negative cache for repeated misses
  - `B3` miss-refresh debounce
  - `B5` cheap string-based `.txt` suffix checks
- The next decision point is remeasurement, then `B6` and `B7` if warm-path
  invalidation is still the dominant bottleneck.
- The downloaded `optimized_indexer.py` and `integration_guide.py` remain
  reference sketches only and are not adopted repo code.

Weighted score formula:

`weighted_score = 0.6 * time_score + 0.2 * space_score + 0.1 * implementation_risk_score + 0.1 * windows_local_fit_score`

Tag legend:

- `quick_win`: small, local change with low coordination cost.
- `medium_refactor`: moderate internal change, still compatible with current architecture.
- `architecture_shift`: meaningful subsystem change with higher rollout and validation cost.

Acceptance scenario IDs:

- `S1`: cold scan over a large root still completes correctly.
- `S2`: warm refresh after a small file delta avoids a full rebuild.
- `S3`: repeated exact lookup stays fast across many queries.
- `S4`: typo or absent-path miss does not trigger repeated rescans.
- `S5`: prefix or partial lookup still returns expected user-facing paths.
- `S6`: `.txt` density, yesterday-project, and recent-game heuristics keep current behavior.
- `S7`: pending audio batch is processed correctly with transcript and archive outputs.
- `S8`: live voice capture still routes into the same transcript pipeline.
- `S9`: confirmation-required actions remain gated behind explicit confirmation.

## Existing Test Cross-Check

- Indexer coverage:
  - `tests/unit/test_assistant_indexer.py`
  - `tests/unit/test_cache_diagnostics.py`
- Planner and confirmation coverage:
  - `tests/unit/test_llm_planner.py`
  - `tests/unit/test_agent.py`
- Voice pipeline coverage:
  - `tests/unit/test_voice_pipeline.py`
  - `tests/unit/test_voice_activation.py`

## Prioritized Backlog

| id | priority | tag | target_component | change | benchmark_system | time_score | space_score | implementation_risk_score | windows_local_fit_score | weighted_score | acceptance_scenarios | existing_test_crosscheck |
| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| B1 | P0 | `quick_win` | `src/aradhya/assistant_indexer.py` | Add explicit exact-match fast index for normalized path keys so exact hits no longer rely on cross-shard gather plus substring fallback. | Windows Search catalog, `vscode-ripgrep` | 5 | 3 | 5 | 5 | 4.6 | `S1`, `S3`, `S5`, `S6` | `test_cached_lookup_results_match_feature_expectations`, `test_candidate_lists_are_capped_and_summary_stays_compact` |
| B2 | P0 | `quick_win` | `src/aradhya/assistant_indexer.py` | Add TTL-based negative cache for normalized misses and clear it on relevant refresh or invalidation. | VS Code watch deduplication, Watchman clock queries | 5 | 4 | 5 | 5 | 4.8 | `S3`, `S4`, `S6` | `test_named_path_lookup_triggers_targeted_rescan_on_cache_miss`, `test_cache_validation_exercises_cold_warm_and_targeted_paths` |
| B3 | P0 | `quick_win` | `src/aradhya/assistant_indexer.py` | Debounce or coalesce miss-driven refreshes so repeated absent-path queries cannot trigger refresh storms. | VS Code File Watcher Internals | 4 | 4 | 5 | 5 | 4.3 | `S2`, `S4`, `S6` | `test_refresh_if_stale_reuses_fresh_cache_without_rewriting_summary`, `test_cache_validation_exercises_cold_warm_and_targeted_paths` |
| B4 | P0 | `quick_win` | `src/aradhya/assistant_system_tools.py` | Replace brute-force `max(matches, key=score)` behavior with early-exit or pre-ranked exact-hit preference where safe, so strong matches do not pay full rescoring cost. | Function-calling executor separation and indexed search ranking patterns | 4 | 4 | 4 | 5 | 4.1 | `S3`, `S5`, `S9` | `test_llm_fallback_routes_to_open_path_and_keeps_confirmation_gate`, open-path coverage in `tests/unit/test_agent.py` |
| B5 | P0 | `quick_win` | `src/aradhya/assistant_indexer.py` | Replace `Path(filename).suffix.lower() == ".txt"` with string-suffix checks inside scans to reduce per-file overhead during refresh. | General low-level scan optimization | 2 | 4 | 5 | 5 | 2.9 | `S1`, `S6` | `test_cached_lookup_results_match_feature_expectations` |
| B6 | P1 | `medium_refactor` | `src/aradhya/assistant_indexer.py` | Introduce dirty-root or dirty-subtree invalidation state so warm refresh can touch only changed roots before a full watcher rollout exists. | Watchman `watch-project` plus query clocks | 5 | 3 | 3 | 5 | 4.4 | `S1`, `S2`, `S4`, `S6` | `test_refresh_creates_manifest_shards_and_summary_artifact`, `test_cache_validation_exercises_cold_warm_and_targeted_paths` |
| B7 | P1 | `architecture_shift` | `src/aradhya/assistant_indexer.py` | Add watcher-assisted invalidation for configured user roots, with fallback to polling or periodic reconciliation when native events are unavailable or unreliable. | VS Code File Watcher Internals, Watchman | 5 | 3 | 2 | 4 | 4.1 | `S1`, `S2`, `S4`, `S6` | Existing indexer tests plus new watcher-specific tests required |
| B8 | P1 | `medium_refactor` | `src/aradhya/assistant_indexer.py` | Split cached metadata into purpose-specific structures: exact path lookup, heuristic metadata, and summary-artifact generation. | Windows Search property cache, Apple indexed attributes | 4 | 4 | 3 | 4 | 3.9 | `S1`, `S3`, `S6` | `test_refresh_creates_manifest_shards_and_summary_artifact`, `test_cached_lookup_results_match_feature_expectations` |
| B9 | P2 | `medium_refactor` | `src/aradhya/voice_pipeline.py` | Add bounded concurrency for backlog file transcription while keeping collision-safe transcript naming and archive semantics intact. | Microsoft fast and batch transcription, Apple shared transcriber engines | 3 | 2 | 3 | 4 | 2.9 | `S7`, `S8` | `test_voice_inbox_uses_shared_pipeline_for_faster_whisper_results`, `test_voice_inbox_surfaces_transcriber_errors_without_archiving_audio` |
| B10 | P2 | `medium_refactor` | `src/aradhya/voice_activation.py`, `src/aradhya/voice_transcriber.py` | Add optional intermediate transcript surfacing for live mode only, without auto-executing actions from partial text. | Apple partial results, Microsoft real-time transcription | 3 | 2 | 2 | 4 | 2.8 | `S8`, `S9` | `test_voice_activation_routes_live_capture_into_assistant`, `test_voice_activation_does_not_rewake_when_assistant_is_already_awake` |
| B11 | P3 | `medium_refactor` | `src/aradhya/llm_planner.py` | Introduce provider-capability-aware strict schema or tool-calling path when the configured backend supports it, while retaining deterministic-first routing and current confirmation semantics. | OpenAI Structured Outputs, OpenAI Function Calling, Vertex AI Function Calling | 2 | 3 | 3 | 4 | 2.5 | `S9` | `test_llm_fallback_routes_to_open_path_and_keeps_confirmation_gate`, `test_llm_fallback_rejects_low_confidence_results`, `test_llm_fallback_handles_invalid_json_without_execution` |
| B12 | P3 | `medium_refactor` | `src/aradhya/assistant_indexer.py` | Consider prefix or fuzzy index only after exact-hit and miss-path latency have been measured again post-B1 to B7. | Indexed search systems and delegated search tools | 2 | 2 | 3 | 3 | 2.2 | `S3`, `S5` | New targeted tests required after exact-index and miss-control work lands |

## Recommended Execution Order

1. Re-measure cache validation, exact-hit lookup, and repeated-miss behavior.
   - Use `src/aradhya/cache_diagnostics.py` and the existing indexer tests as the baseline.
2. If warm behavior is still the bottleneck, move to `B6` and then `B7`.
   - This is the point where watcher-backed invalidation becomes worth the added complexity.
3. Only after the indexer path is materially improved should voice throughput (`B9`, `B10`) or planner transport hardening (`B11`) move up.

## Explicit Non-Priorities

- Do not start with trie or fuzzy indexing.
  - Current evidence points to miss-triggered rescans and exact-hit path behavior as the bigger time-cost issue.
- Do not redesign the confirmation gate.
  - Safety semantics are already correct and are not the current latency hotspot.
- Do not split the voice path into separate live and dropped-file pipelines.
  - The shared path is a correctness advantage and is already covered by tests.

## Evidence Summary

- The current cache already gives Aradhya a good structural base. The problem is not "no index"; it is "index freshness and miss behavior still trigger expensive work."
- Official Windows, VS Code, and Watchman material all support the same direction: consolidate watches, track change state, dedupe work, and do not blindly rescan after every negative lookup.
- Official OpenAI, Google, and Apple planner/tooling material supports stricter schema transport, but that is secondary to the current indexer hotspot.
- Official Apple and Microsoft speech material supports streaming, intermediate results, and multiple transcription modes, but those are throughput and UX improvements after the context engine is fixed.
