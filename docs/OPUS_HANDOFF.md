# Opus Handoff Notes

These notes are for the parallel Opus model working on Parasite OS alongside
Codex.

## Current Direction

- The first implementation slice is LAN-only federation foundation.
- Keep the laptop as the primary reasoning node.
- Treat every other device as a capability-reporting companion until proven
  reliable enough for more work.
- Do not hard-code Saurabh's current devices. Every user can have different
  hardware, so routing must use topology capability manifests.

## Safety Rules

- Do not write API keys into tracked files.
- Use `ARADHYA_OPENROUTER_API_KEY` for OpenRouter.
- Keep `allow_live_execution` false by default.
- Do not bypass the confirmation gate for file writes, shell commands, browser
  actions, launches, or clipboard writes.
- Federation secrets live under `core/memory/federation/`, which is ignored.
- Cloud model calls must pass through the privacy gate in
  `src/aradhya/cloud_safety.py`.
- The separate Opus key should stay in `OPUS_OPENROUTER_API_KEY`; Aradhya's key
  stays in `ARADHYA_OPENROUTER_API_KEY`.

## Requests For Opus

- When editing federation code, keep transport, trust, and task routing in
  separate modules.
- Before adding internet federation, finish LAN pairing, signed envelopes,
  redaction preview, peer health, and audit.
- Prefer normal-user acceptance tests over impressive but fragile demos.
- Leave short comments where assumptions affect future agents.
- Use `/model workers` and `/model workers assess <text>` to verify cloud
  worker visibility and prompt safety before sending public-context work to an
  OpenRouter model.
