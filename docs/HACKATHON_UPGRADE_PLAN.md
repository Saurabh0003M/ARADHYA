# Aradhya Upgrade Plan — Voice-First Self-Evolving Multi-Agent OS

> Companion to `docs/research/AGENTSCOPE_COMPARISON.md` (the three-repo teardown).
> Date: 2026-07-07. This is the **execution plan**: what to build, in what order, with acceptance
> criteria tied to the hackathon demo beats.

## Demo target (what we are building toward)
A blindfolded user speaks; Aradhya:
1. understands multilingual voice and narrates the screen back (Gemini),
2. speaks *while it thinks* and can be interrupted mid-sentence (streaming voice),
3. saves each command into a tree-brain, locates the most relevant node and expands it (graphify),
4. drives multiple app windows, one agent-pointer per window, each with its own terminal,
5. gets better over time without retraining (outcome-scored memory).

## Donor repos (all now under `F:\repos\`)
| Repo | Role in the upgrade |
|---|---|
| `agentscope-2.0.4` | engine patterns: streaming loop, TTS-middleware, message bus, context-compression schema |
| `graphify-0.9.8` | deterministic tree-brain (graph + BFS locate/expand + `reflect.py` memory) |
| `helix-db` | durable graph+vector store (post-hackathon durability path) |
| `public-apis` | curated list of **free** public APIs → fed into Aradhya's existing `api_catalog.py` / Parasite as callable free-API tools |
| `pxpipe-0.7.1` | optional token-reduction proxy (renders bulky context as PNGs; Claude-oriented, Node/TS) — technique noted in P5 |
| `KittenTTS-0.8.1` | **neural TTS, CPU-only, <25MB, Apache-2.0** — natural voice output, stage-safe default for the demo (P2) |
| `chatterbox-0.1.2` | **neural TTS, GPU, MIT** — SoTA voice w/ emotion control + voice cloning; premium voice option if a GPU is present (P2) |

## Provider stance — free APIs only (per user)
No paid keys. The model layer is **swappable across free providers**, reusing Aradhya's existing
provider abstraction (`model_provider.TextModelProvider`, `providers/openrouter.py`,
`providers/cloudflare.py`):
- **Local Ollama** (default, fully free/offline) — text + vision (`llava`, `llama3.2-vision`,
  `qwen2-vl`).
- **OpenRouter free tier** — already implemented in Aradhya; add free multimodal model ids.
- **NVIDIA NIM** (`build.nvidia.com`, free tier, OpenAI-compatible) — new provider, small addition on
  top of the OpenRouter pattern; gives free hosted vision + strong text models.
- **Cloudflare Workers AI** — already implemented; free-tier vision available.
Any cloud call still passes `CloudPrivacyGate`. Gemini was only ever an example; it is out.

## Demo-beat → phase map
| Pitch beat | Delivered by | Phase |
|---|---|---|
| Multilingual voice + multimodal screen understanding | Free vision provider (Ollama/OpenRouter/NIM) + Aradhya vision | **P1** |
| Speaks as it thinks; interruptible (voice-first feel) | AgentScope streaming loop + TTS-middleware | **P2** |
| Commands in a tree-brain; locate + expand node | graphify graph + BFS + MCP | **P3** |
| Self-evolving memory | graphify `reflect.py` + Aradhya learnings | **P3** |
| Multiple virtual pointers, one per window | window-agent team + message bus | **P4** |
| Per-window terminal | tool groups equipped per window-agent | **P4** |
| Free-API superpowers (weather, translate, TTS, etc.) | `public-apis` → `api_catalog.py` / Parasite | **P3.5** |

## Guiding constraints (do not break)
- **Keep every safety gate**: ConfirmationGate, HookEngine, PermissionEngine, dry-run default, audit
  JSONL, CloudPrivacyGate. Gemini is cloud → every Gemini call routes through CloudPrivacyGate.
- **Local-first posture stays**: Ollama remains the default provider; Gemini is an opt-in profile.
- **Additive, not a rewrite**: wrap donor code behind Aradhya's existing protocols
  (`TextModelProvider`, `mcp_client`, `SubagentRunner`). No big-bang async migration.
- **Each phase ships a demoable increment** and gets committed before the next starts.

## Integration strategy (decided)
- **Reuse Aradhya's own provider layer** for models — no new paid dependency. Add NVIDIA NIM as a thin
  OpenAI-compatible provider next to the existing `openrouter.py`.
- **pip-install** the donor engines we consume unmodified: `agentscope` (streaming/TTS/bus patterns),
  `graphifyy` (brain).
- **Vendor (copy-in) only** the small pieces we must edit: the in-memory message-bus pattern. Keep
  Apache-2.0 / MIT headers + a `NOTICE` file (both are GPLv3-compatible).
- **`public-apis`**: run it through Aradhya's existing Parasite `analyze_public_apis_readme` /
  `api_catalog.py` to generate a catalog of free APIs the agent can call as tools (weather, dict,
  translate, free TTS/STT, etc.). This is already half-built — the parser exists.
- **HelixDB is deferred to post-hackathon** (§P5) — it needs a running Rust instance; graphify covers
  the brain for the demo with zero container risk.
- **Python bump**: AgentScope needs 3.11+. Standardize the venv on **3.12** (P0).
- **Paths:** all donor repos live under `F:\repos\` (agentscope-2.0.4, graphify-0.9.8, helix-db,
  public-apis, pxpipe-0.7.1).

---

## Phase 0 — Foundation (~0.5 day) — *prerequisite*
**Goal:** clean base that can import all donors.
- [ ] Recreate venv on **Python 3.12**; reinstall `requirements*.txt`.
- [ ] Add `requirements-upgrade.txt`: `agentscope`, `graphifyy`, `google-genai` (Gemini SDK).
- [ ] Delete orphaned `src/aradhya/smart_router/` (only stale `__pycache__` remains; source removed in
      `25b963c`). Add `__pycache__/`, `.pytest_tmp*`, `htmlcov/`, `pytest-cache-files-*` to
      `.gitignore` if not already ignored.
- [ ] Smoke test: `python -c "import agentscope, graphify"` inside the venv.
- [ ] Branch: `feat/hackathon-upgrade`.

**Acceptance:** venv is 3.12, all three importable, full `pytest tests/unit` still green.

---

## Phase 1 — Free multimodal provider layer (~1 day) — *demo beat: multilingual + multimodal*
**Goal:** Aradhya narrates the screen in the user's language using a **free** vision model, with the
provider swappable and local Ollama as the always-free offline default.
- [ ] `src/aradhya/providers/nvidia_nim.py`: thin provider implementing the existing
      `model_provider.TextModelProvider` protocol, reusing the OpenAI-compatible request shape from
      `providers/openrouter.py` (NIM's endpoint is OpenAI-compatible). Register `"nvidia"` in
      `build_text_model_provider()`.
- [ ] Add **free vision model ids** to the OpenRouter + NIM + Ollama configs
      (e.g. Ollama `llama3.2-vision` / `llava` / `qwen2-vl` local; OpenRouter/NIM free vision tiers).
      `describe_image` already exists on the provider protocol — point it at whichever is active.
- [ ] Connect `describe_image` → `tools/vision_tools.py` screenshot capture so a screen frame → spoken
      description. Add a `/watch` narration loop (reuse the existing screen-watch toggle) that
      periodically captures + describes the foreground window.
- [ ] Multilingual: pass the user's detected language into the prompt so replies + narration come back
      in that language (works with any capable model; no provider lock-in).
- [ ] **Every cloud call still passes `CloudPrivacyGate`** (mirror the OpenRouter path in
      `cloud_safety.py` / `model_workers.py`). Free keys via `.env`
      (`OPENROUTER_API_KEY`, `NVIDIA_API_KEY`), length-checked only, never printed.
- [ ] Profiles: `provider="ollama"` (offline default) and `provider="nvidia"`/`"openrouter"` (free
      hosted vision), switchable via `/status`-adjacent command.

**Acceptance:** `/status` shows the active free provider; a screenshot yields a spoken description; ask
in Hindi → answer in Hindi; switching provider needs no code change. CloudPrivacyGate blocks a screen
frame containing a visible `.env`/secret before it leaves the machine. **Fully offline path works** via
local Ollama vision (no network at all).

**Risk:** free hosted tiers rate-limit. Mitigation: local Ollama vision is the zero-dependency fallback
and is the stage-safe default; hosted free providers are the "bigger brain" opt-in.

---

## Phase 2 — Voice-first streaming output + neural voice (~1.5 days) — *demo beat: speaks while thinking, interruptible*
**Goal:** the single biggest "feels alive" upgrade for a blind user — natural-sounding voice that
speaks as the model generates and can be cut off mid-sentence.
- [ ] **Neural TTS backend** `src/aradhya/voice/neural_tts.py` with a small strategy interface
      (`speak(text) -> wav`), three backends behind it:
  - **KittenTTS (default, stage-safe):** CPU-only, <25 MB, ONNX, real-time, 8 voices, needs Python
    3.12 (matches P0). `pip install` the release wheel. This is the demo default — works on any
    laptop, no GPU.
  - **Chatterbox (premium, if GPU):** MIT, 0.5B, emotion/exaggeration control + voice cloning — gives
    Aradhya a warm, distinctive voice; English only, wants a GPU.
  - **pyttsx3/SAPI (fallback):** the current path, kept as last resort if neither model loads.
- [ ] Add a lightweight **event emitter** to `AgentLoop` (callback shim, *not* a full async rewrite):
      `on_text_delta`, `on_tool_start`, `on_confirm_required`, `on_final`. Emit from `_call_model`
      streaming path and the gate methods.
- [ ] `src/aradhya/voice/streaming_tts.py`: sentence-segmenting consumer (pattern from AgentScope
      `middleware/_tts_middleware.py`) that buffers deltas, splits on sentence boundaries, and feeds
      each sentence to the neural TTS backend → audio out while generation continues. Keep the NVDA
      screen-reader output path in parallel (some blind users prefer their own SR voice — make it a
      toggle: neural voice vs NVDA passthrough).
- [ ] **Barge-in:** mic-activity (existing `voice/activation.py`) sets an interrupt flag the loop
      checks between deltas; on trip, stop TTS playback immediately, flush the queue, and treat the new
      utterance as the next turn (AgentScope `UserInterruptEvent` semantics).
- [ ] Confirmation gate spoken aloud: `on_confirm_required` → TTS reads the pending action and waits
      for a spoken "yes proceed".

**Acceptance:** assistant speaks sentence-by-sentence in a natural neural voice during a long answer;
saying "stop" cuts it off mid-sentence within ~1s; risky action is spoken and waits for spoken
approval; runs on a **CPU-only laptop** via KittenTTS with no GPU.

**Risk:** neural-TTS latency for the first sentence; model load time. Mitigation: warm the model at
startup; single TTS worker thread with a queue; drop-and-flush on interrupt; KittenTTS is tiny so load
is fast. Chatterbox only used when a GPU is detected.

---

## Phase 3 — Tree-brain + self-evolving memory (~1.5 days) — *demo beat: locate + expand, self-improve*
**Goal:** commands live in a graph that grows as the user speaks and self-corrects.
- [ ] `pip install graphifyy`.
- [ ] `src/aradhya/brain/corpus_writer.py`: mirror Aradhya knowledge into a corpus dir graphify can
      graph — session transcripts, `SKILL.md` skills, tool docstrings, learnings ledgers, and the
      app/window registry (from P4; stub until then).
- [ ] `src/aradhya/brain/graph_brain.py`: run graphify's pipeline over the corpus; wire graphify's
      **MCP stdio server** into `mcp_client.py` (`query_graph`, `get_node`, `get_neighbors`,
      `god_nodes`, `shortest_path`, `graph_stats`).
- [ ] Per-command recall: before planning, `query_graph(user_utterance)` → seed node → BFS expand →
      inject the token-budgeted subgraph into the system prompt as "relevant memory."
- [ ] Self-evolving: after each command resolves, emit a graphify `save-result` outcome
      (`useful` / `dead_end` / `corrected`); run `reflect.py` so the brain promotes/penalizes nodes
      deterministically. Bridge to existing `learnings/` so both ledgers agree.
- [ ] `/brain` command: `rebuild`, `query <q>`, `stats`, `why <a> <b>` (shortest_path narration).

**Acceptance:** speak a command → Aradhya names the located node and narrates its expansion; repeat a
task → brain shows the node promoted to "preferred"; a wrong answer marked corrected stops recurring.
Brain node count visibly grows across the session.

**Risk:** corpus rebuild latency. Mitigation: incremental corpus writes + graphify `watch`; rebuild
off the hot path.

---

## Phase 3.5 — Free-API superpowers (~0.5 day) — *capability breadth, near-zero cost*
**Goal:** give the agent a large catalog of **free** public APIs to call as tools — the
`public-apis` repo is a curated list, and Aradhya already ships a parser for exactly this format.
- [ ] Run `F:\repos\public-apis\README.md` through the existing Parasite
      `analyze_public_apis_readme` → generates the structured JSON catalog `api_catalog.py` consumes.
- [ ] Curate an allowlist of no-auth / free-key APIs useful for the demo: weather, dictionary,
      translation (multilingual!), free TTS/STT, geocoding, Wikipedia.
- [ ] Expose `/apis search <query>` (already exists) + let the agent auto-select a free API tool when a
      spoken request matches (e.g. "what's the weather" → open-meteo).
- [ ] All calls go through the ConfirmationGate + CloudPrivacyGate like any network tool.

**Acceptance:** "translate this to Marathi" or "what's the weather in Pune" resolves via a free public
API with no paid key. Ties the free-API theme into a live spoken capability.

**Risk:** low. Purely additive; the parser and catalog command already exist.

---

## Phase 4 — Window-agent team (~2–3 days) — *demo beat: multiple pointers per window + per-window terminals*
**Goal:** the multi-agent OS story — one agent-pointer per window, each independently operable.
- [ ] `src/aradhya/agents/window_agent.py`: a subagent pinned to a UIA window handle (builds on
      `SubagentRunner` + `desktop_control.py`); its context carries only that window's element tree.
- [ ] `src/aradhya/agents/message_bus.py`: vendor + adapt AgentScope
      `app/message_bus/_in_memory_message_bus.py` (in-memory only for the demo).
- [ ] `src/aradhya/agents/coordinator.py`: routes a spoken command to the right window-agent
      (by app name / "the browser" / "Notepad"), fans out, collects results, narrates back.
- [ ] **Per-window terminal**: expose `tools/shell_tools.py` as a **tool group** (AgentScope toolkit
      group + meta-tool pattern) equipped per window-agent, cwd/context scoped to that app.
- [ ] Virtual pointer visualization: reuse `ui/floating_icon.py` to render one marker per active
      window-agent (nice-to-have for the visual story).

**Acceptance:** two apps open (e.g., Notepad + browser); "in Notepad write X, in the browser search Y"
routes to two agents that act concurrently; each window has an addressable terminal; every action still
passes the ConfirmationGate.

**Risk:** highest-complexity phase. Mitigation: this is the **stretch** beat — if time is short, demo
two window-agents sequentially rather than concurrently; keep P0–P3 as the guaranteed demo.

---

## Phase 5 — Hardening & durability (post-MVP / if time)
- [ ] Structured context compression: swap `context_compressor` for AgentScope `SummarySchema`
      (5-field) + 0.8 trigger ratio.
- [ ] Bash-parser-backed gating: port `agentscope tool/_builtin/_bash_parser.py` so compound commands
      (`safe && rm -rf`) are decomposed before the ConfirmationGate/PermissionEngine see them.
- [ ] Persistable "always allow this session" permission decisions (AgentScope `permission_context`).
- [ ] Declarative model fallback: `ModelConfig` Gemini→Ollama→OpenRouter chain with retries.
- [ ] **HelixDB durable brain (product path)**: stand up a local Helix instance (`helix start dev
      --disk`), define node/edge labels + vector index, and back `graph_brain.py` with HelixDB for
      live per-command writes + vector-KNN recall. Replaces graphify's batch-rebuild with a durable
      store once the concept is proven. See comparison §6–7.
- [ ] **pxpipe token-reduction (optional):** `F:\repos\pxpipe-0.7.1` renders bulky context (system
      prompt, tool docs, older history) into compact PNGs to cut input tokens ~60%. It is Node/TS and
      Claude-request-oriented, so it doesn't drop straight into Aradhya's Ollama/OpenRouter path. Two
      ways it could still pay off: (a) as-is proxy if/when a Claude-family free tier is used; (b) adopt
      the *technique* — when running a vision model (P1), render the static system-prompt + tool-schema
      block as one image instead of thousands of text tokens. Evaluate only if context-window pressure
      becomes real; not needed for the core demo.

---

## Sequencing & the MVP cut line
```
P0 ──> P1 ──> P2 ──> P3 ──> P3.5 ──> [P4 stretch] ──> [P5 polish]
0.5d   1d     1.5d   1.5d   0.5d      2–3d            time-boxed
└──────────── MVP DEMO (P0–P3.5, ~5 days) ────────────┘
```
- **Minimum viable demo = P0–P3**: Gemini multilingual + screen narration, speak-while-thinking with
  barge-in, and the self-evolving tree-brain. That alone demonstrates 4 of the 6 pitch beats and is
  low-risk (no Rust container, no async rewrite).
- **P4 is the ambitious differentiator** (multi-pointer OS). Attempt only after P0–P3 are committed
  and green.
- **P5 is polish/product-hardening**, including the HelixDB durability upgrade.

## Milestones / commit points
1. Green venv + donors importable (end P0).
2. Gemini answers in Hindi + narrates a screenshot (end P1).
3. Live speak-while-streaming with barge-in (end P2).
4. `/brain` locates + expands + self-corrects (end P3) → **this is the recordable demo**.
5. Two window-agents routed from one voice command (end P4).

## Open decisions for the user
- **Hackathon length** sets how far past the P0–P3 MVP to push. Plan is length-agnostic; MVP cut line
  is marked.
- **Stage default provider**: recommend **local Ollama vision** as the demo default (zero network
  risk, fully free, offline), with a free hosted provider (NVIDIA NIM / OpenRouter free tier) as the
  "bigger brain" opt-in for when wifi is reliable. Both are free; the only question is offline-safe vs
  larger-model.
