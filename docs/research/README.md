# Aradhya Research Pack

This folder is the repo-grounded research and optimization pack for implemented
Aradhya features only.

Current scope:

- local context engine and directory index
- planner and execution safety boundary
- voice inbox, live activation, and spoken replies

Source policy:

- official docs, official public repos, and official engineering wikis come first
- private or undocumented implementation details are not inferred as fact
- every recommendation should separate `Source says:` from `Inference:`

Working rules:

- treat downloaded deep-search outputs as candidate material, not ground truth
- do not copy `optimized_indexer.py` or `integration_guide.py` directly into the repo
- prefer measured repo behavior over generic benchmark claims such as `100x`

Current repo status:

- the first P0 indexer pass is implemented in runtime code:
  - cross-shard exact-match fast index
  - TTL-based negative cache for repeated misses
  - debounce for miss-triggered targeted refreshes
  - cheaper `.txt` suffix counting during scans
- `cache validate` now reports exact-hit and repeated-miss behavior in addition
  to cold, warm, and targeted positive refresh checks

Next refresh point:

- rerun the research matrix and backlog against the post-P0 code before treating
  old baseline rows as current-state truth
