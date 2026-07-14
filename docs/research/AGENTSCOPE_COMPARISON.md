# Aradhya Upgrade — AgentScope 2.0.4 + graphify 0.9.8 Comparison & Plan

> Scanned: `F:\ARADHYA` (src/aradhya, ~40 core modules) vs `F:\agentscope-2.0.4\agentscope-2.0.4`
> (src/agentscope, 20 packages) vs `F:\graphify-0.9.8\graphify-0.9.8` (the "brain" repo).
> Date: 2026-07-07. Goal: upgrade Aradhya for the hackathon demo — voice-first, self-evolving
> multi-agent OS for accessibility (blindfolded student, tree-brain memory, multiple virtual
> pointers per window, per-window terminals, Gemini multilingual voice + multimodal screen
> understanding).
>
> **Three donor repos, three roles:** AgentScope = the *engine-room* (async loop, streaming events,
> Gemini model, middleware, permissions — §3). graphify = the *deterministic tree-brain* (knowledge
> graph + BFS locate-and-expand + outcome-scored work memory — §5). HelixDB = the *durable
> graph+vector memory store* (persistent, ACID, live vector KNN + full-text — §6). See §7 for how the
> three fit together and which brain to use for the demo.

---

## 1. High-level identity of each project

| | Aradhya | AgentScope 2.0.4 |
|---|---|---|
| What it is | Windows Operating Intelligence layer — controls the actual desktop | General-purpose production agent **framework** (library + FastAPI service) |
| Execution model | **Synchronous**, thread-based (`AgentLoop.run`, `ThreadPoolExecutor` subagents) | **Asyncio-native**, async-generator event streaming end to end |
| Python | 3.10+ (venv has 3.10 & 3.12 pycache mixed) | **3.11+ required** |
| License | GPL-3.0 | Apache-2.0 (→ legally fine to vendor into GPLv3 with attribution) |
| Model providers | Ollama, OpenRouter, Cloudflare Workers AI | Anthropic, **Gemini**, OpenAI (chat+responses), Ollama, DashScope, DeepSeek, xAI, Moonshot — each with a dedicated message formatter |
| Unique strengths | Desktop control (UIA), vision/screen tools, browser automation, NVDA output, wake word/voice inbox, floating icon, Telegram, ConfirmationGate + HookEngine + PermissionEngine + audit JSONL, Parasite digestion, Learnings self-correction, SKILL.md skills | Event system, middleware onion (5 hooks), permission engine with persistable decisions, RAG + embeddings + 3 long-term-memory integrations, context compression w/ structured schema, model fallback config, task-ledger tools, multi-agent teams + message bus, OTel tracing, streaming TTS, Docker/E2B sandbox workspaces, hardened builtin tools (Bash w/ full command parser) |

**Bottom line:** they don't compete — AgentScope is the *engine-room* Aradhya hand-rolled, done more
rigorously; Aradhya's OS-control layer (the actual differentiator) doesn't exist in AgentScope at all.
Upgrade = keep Aradhya's body, transplant AgentScope's organs.

---

## 2. Module-by-module comparison

### 2.1 Agent loop
- **Aradhya** `agent_loop.py`: sync ReAct loop; returns after full model response; consecutive-timeout
  and repeated-tool-call guards; gates woven inline (`_apply_hook_gate` → `_apply_permission_engine` →
  `_apply_dangerous_tools_gate`). No mid-generation interruption; no streaming events to the UI layer.
- **AgentScope** `agent/_agent.py` (108 KB): async generator yielding ~25 typed events
  (`TextBlockDeltaEvent`, `ThinkingBlock*`, `ToolCall*`, `ToolResult*`, `RequireUserConfirmEvent`,
  `UserInterruptEvent`, `ExceedMaxItersEvent`, …). Human-in-the-loop is *resumable*: a reply can pause
  on `RequireUserConfirmEvent` and resume later with a `UserConfirmResultEvent`. Parallel tool-call
  batching (`_ToolCallBatch`). `ReActConfig` (max_iters, stop_on_reject, interruption handling),
  `ModelConfig` (retries + `fallback_model`).
- **Verdict:** biggest architectural gap. For a *voice-first* demo, streamed events + barge-in
  interruption are the difference between "speaks after 20 s of silence" and "speaks as it thinks,
  can be interrupted mid-sentence."

### 2.2 Models / providers
- Aradhya: `model_provider.py` protocol (generate/chat/stream/describe_image), Ollama primary,
  OpenRouter/Cloudflare behind `CloudPrivacyGate`. **No Gemini** (grep: zero hits) — yet the
  hackathon pitch is Gemini-powered.
- AgentScope: `model/_gemini` + `formatter/_gemini_formatter.py` (multimodal blocks incl. images),
  `embedding/_gemini` and `embedding/_ollama`. Also structured-output support (`StructuredResponse`).
- **Verdict:** port or depend on AgentScope's Gemini model+formatter. Multimodal screen understanding
  (screenshots → Gemini) comes almost free since Aradhya's vision tools already capture screenshots.

### 2.3 Memory / "tree-like brain"
- Aradhya: SQLite `state_store` (sessions/turns/tool_calls), `context_compressor` (plain LLM
  summarize), `learnings` (Markdown ledgers + rule promotion at 3 recurrences). **No embeddings, no
  vector search, no semantic retrieval anywhere.**
- AgentScope: `rag/` (chunker, parser, vdb), `embedding/` (Ollama = local-first option), three
  long-term-memory middlewares (`mem0`, `agentic_memory` (36 KB), `ReMe`) that inject retrieval into
  the loop via middleware.
- **Verdict:** the hackathon's "tree-like brain that locates the most relevant node and expands it"
  is exactly *hierarchical memory + semantic retrieval*. Build it on AgentScope's embedding+vdb
  primitives (Ollama embeddings keeps the local-first promise); the agentic-memory middleware is the
  best reference implementation to crib from.

### 2.4 Context management
- Aradhya: compressor summarizes old turns when too big.
- AgentScope: `ContextConfig` — trigger ratio (0.8 of window), reserve ratio, **structured
  `SummarySchema`** (task_overview / current_state / important_discoveries / next_steps /
  context_to_preserve), tool-result token cap (50 k), optional `Offloader` writes compressed context
  to workspace files.
- **Verdict:** adopt the schema-guided compaction — small effort, directly improves long voice
  sessions.

### 2.5 Hooks / middleware
- Aradhya: `HookEngine` (PreToolUse/PostToolUse/SessionStart from `hooks.json`) — config-driven.
- AgentScope: `MiddlewareBase` — 5 onion hooks (`on_reply`, `on_reasoning`, `on_acting`,
  `on_model_call`, `on_compress_context`) + `on_system_prompt` transformer + middleware-provided
  tools + per-middleware persisted state. RAG, TTS, budget, tracing, long-term memory are all just
  middlewares.
- **Verdict:** Aradhya's hook engine covers the safety use case already; the middleware pattern is
  worth adopting *if/when* the loop goes async, because it's how TTS/RAG/memory snap in cleanly.

### 2.6 Permissions & safety
- Aradhya: HookEngine → PermissionEngine → ConfirmationGate → DANGEROUS_TOOLS set; dry-run default;
  JSONL audit; `CloudPrivacyGate` (unique — AgentScope has nothing like it).
- AgentScope: `permission/` engine (27 KB) with rules, decisions, behaviors, persistable
  `permission_context` in agent state ("always allow X this session"), and a **Bash command parser**
  (27 KB) that decomposes compound shell commands so permission rules apply to each sub-command.
- **Verdict:** keep Aradhya's gates (they're the product's soul); steal two ideas —
  (1) persistable per-session "always allow" decisions, (2) the bash parser so `run_command` gating
  can't be bypassed with `safe_cmd && rm -rf`.

### 2.7 Multi-agent
- Aradhya: `SubagentRunner` (thread pool, spawn/kill/messenger), agent defs from YAML frontmatter.
- AgentScope app layer: `agent_create`, `agent_invite`, `team_create/say/delete` tools, message bus
  (in-memory + Redis), background task manager, wakeup dispatcher, cancel dispatcher, subagent
  human-in-the-loop projector, multi-tenant sessions.
- **Verdict:** for "multiple virtual pointers operating each opened window individually", the design
  you need is *one agent per window handle + a shared message bus + a coordinator*. Aradhya's
  SubagentMessenger is a primitive version; AgentScope's team/message-bus is the blueprint. An
  in-memory bus port is enough for the demo.

### 2.8 Voice / TTS
- Aradhya: full *input* pipeline (wake word, mic, faster-whisper, voice inbox, NVDA output) — far
  ahead of AgentScope, which has **no STT at all**. Output synthesis is minimal (3 KB synthesizer).
- AgentScope: `tts/` streaming TTS base + realtime models, and `_tts_middleware` that segments
  streamed text into sentences and feeds TTS *while the model is still generating*.
- **Verdict:** keep Aradhya's STT stack; adopt the **TTS-middleware pattern** (sentence-chunked
  speak-while-streaming). Combined with event streaming (2.1) this is the single biggest demo-feel
  upgrade for a blind user.

### 2.9 Tools
- Aradhya: 17 tool modules incl. browser, desktop (UIA), vision, power, maintenance — OS breadth
  AgentScope lacks entirely.
- AgentScope: fewer but hardened builtins (Bash/Read/Write/Edit/Grep/Glob ~160 KB combined), tool
  groups with a meta-tool the model calls to equip/unequip groups (context-window hygiene), MCP
  registration into the same toolkit, skills as tools.
- **Verdict:** adopt **tool groups + meta-tool** — Aradhya's registry ships everything at once, and
  with 17 modules the tool schema alone eats context. Per-window terminal = a tool group equipped
  per window-agent.

### 2.10 Skills, MCP, tracing, sandboxing
- Skills: both load SKILL.md-style folders; Aradhya's (installer + intents + parasite generation) is
  richer. Keep.
- MCP: both have stdio MCP clients; parity for demo purposes.
- Tracing: AgentScope has OTel spans for reply/reasoning/acting/model-call. Nice-to-have; Aradhya's
  audit JSONL suffices for the demo.
- Workspaces (Docker/E2B/MCP-gateway): low relevance — Aradhya *intentionally* operates the real
  desktop. Skip.

---

## 3. Prioritized upgrade plan (hackathon-oriented)

Strategy: **cherry-pick, don't rewrite.** Apache-2.0 → GPLv3 vendoring is legal (keep file headers +
NOTICE). Taking `agentscope` as a pip dependency is also viable for the model/embedding layer only,
but it forces Python ≥3.11 — standardize the venv on 3.12 first.

### P0 — demo-critical
1. **Gemini provider** — port `model/_gemini` + `formatter/_gemini_formatter.py` (or
   `pip install agentscope` and wrap `GeminiChatModel` behind Aradhya's `TextModelProvider`
   protocol). Wire `describe_image` to Gemini multimodal → continuous screen narration.
   ~1 day.
2. **Brain tree (semantic memory)** — new `src/aradhya/brain/`: node store (SQLite table:
   id, parent_id, summary, embedding blob) + Ollama embeddings (port `embedding/_ollama`) +
   cosine top-k "locate node" + expand-children on activation. Feed from existing session
   summaries and learnings ledgers. ~2 days.
3. **Speak-while-streaming voice output** — add a minimal event emitter to `AgentLoop`
   (`on_text_delta`, `on_tool_start`, `on_confirm_required`) and a sentence-segmenting TTS consumer
   (pattern from AgentScope `_tts_middleware`) feeding SAPI/NVDA. Add barge-in: mic activity sets an
   interrupt flag checked between deltas (AgentScope `UserInterruptEvent` semantics). ~2 days.

### P1 — architecture of the pitch
4. **Window-bound agent team** — per-window subagent (UIA window handle pinned in its context) +
   in-memory message bus (port pattern from `app/message_bus/_in_memory_message_bus.py`) +
   coordinator dispatching voice commands to the right window-agent. Builds on existing
   SubagentRunner/Messenger. ~2–3 days.
5. **Per-window terminal** — expose the existing shell tools as a *tool group* equipped per
   window-agent (AgentScope toolkit group + meta-tool pattern), cwd/context scoped to that app.
6. **Structured context compression** — swap `context_compressor` prompt for the
   `SummarySchema` 5-field structured summary + 0.8 trigger ratio.

### P2 — robustness
7. **Bash-parser-backed gating** — port `tool/_builtin/_bash_parser.py` so compound commands are
   decomposed before ConfirmationGate/PermissionEngine evaluate them.
8. **Persistable permission decisions** — "always allow for this session" stored in state
   (AgentScope `permission_context` pattern) to cut confirmation fatigue during live demos.
9. **Model fallback config** — formalize Ollama→OpenRouter→Cloudflare chain as declarative
   `ModelConfig` with retries.
10. **Task-ledger tools** — port `tool/_task/*` (create/update/list task) so the plan is visible
    state the model maintains — pairs well with `planning_workflow.py`.

### Housekeeping found during scan
- `src/aradhya/smart_router/` contains **only `__pycache__`** — source was removed in commit
  `25b963c` but bytecode remains; delete the folder (and ensure `__pycache__` is gitignored).
- Root is littered with pytest temp dirs (`.pytest_tmp*`, `pytest_tmp*`, `pytest-cache-files-*`,
  `htmlcov`) — worth a cleanup + .gitignore pass.
- Fun alignment: AgentScope is an ideal **Parasite host** — clone it into `Hosts/` and run the
  digestion pipeline on it; the ledger scoring already awards `agent_framework` +12.

---

## 5. graphify 0.9.8 as the "tree-like brain" (the repo you pointed at)

### 5.1 What graphify actually is
A **deterministic knowledge-graph engine**, MIT-licensed, Python 3.10+ (so it drops straight into
Aradhya's current venv — no 3.11 bump needed to use it standalone). Pipeline:
`detect → extract → build_graph → cluster → analyze → report → export`. It parses ~40 languages plus
docs/PDFs/images via tree-sitter AST into a NetworkX graph, detects communities (Leiden), finds
"god nodes" (most-connected concepts), and **builds the graph with zero LLM credits** — pure local
AST + a local embedder. Deps are light: `networkx`, `numpy`, `rapidfuzz`, `tree-sitter-*`.

### 5.2 Why it is a near-perfect match for the pitch
The hackathon brief says: *"commands saved in a tree-like brain structure that locates the most
relevant node and expands it."* graphify's `serve.py` already **is** that mechanism:
- `_score_nodes` (trigram index + IDF + exact/substring bonuses) ranks nodes against a query.
- `_pick_seeds` selects the most-relevant seed node(s), guarding against noise-term hijack.
- `_bfs` / `_dfs` then **expand outward from that node** to a token-budgeted subgraph.
- `query_graph`, `get_node`, `get_neighbors`, `get_community`, `god_nodes`, `shortest_path`,
  `graph_stats` are exposed as an **MCP stdio server** — meaning Aradhya's existing `mcp_client.py`
  can consume the entire brain with essentially zero glue code.
- `reflect.py` is a **deterministic work-memory layer**: it scores nodes by outcome signals
  (`useful` / `dead_end` / `corrected`) with a 30-day half-life, promotes corroborated nodes to
  "preferred", records "known dead ends" and "corrections", and writes a `.graphify_learning.json`
  sidecar overlay merged into query results at display time. This is a stronger, graph-native
  version of Aradhya's own `learnings/` module — same "self-evolving" narrative, but retrieval-aware.

### 5.3 How this changes the earlier plan
This **replaces P0 item #2 (build a semantic brain on AgentScope embeddings)**. Do not hand-roll a
vector store — graphify is a purpose-built, deterministic, zero-token, local-first brain that already
ships the locate-and-expand traversal AND an MCP surface AND an outcome-scored memory layer. It is
also a better story for a blind-accessibility demo: every edge is *explained* (`EXTRACTED` vs
`INFERRED`), so the assistant can narrate *why* two things connect, not just assert a similarity score.

### 5.4 The one real gap to bridge
graphify graphs a **corpus of files** (code/docs), not a live stream of spoken commands. To make it
Aradhya's *command* brain you supply the corpus it graphs. Two options:
1. **Corpus-feeder (fastest):** have Aradhya continuously emit its knowledge as files graphify already
   understands — session transcripts, `SKILL.md` skills, tool docstrings, the app/window registry,
   the learnings ledgers — into a folder, then run graphify's pipeline over it and serve the graph.
   Reuses graphify unmodified; the brain literally grows as the user talks.
2. **Engine-reuse (most control):** import `graphify.serve` (`_score_nodes`, `_pick_seeds`, `_bfs`)
   and `graphify.build` directly, and build the graph from Aradhya's own node types
   (command → skill → tool → app → window) instead of tree-sitter output. More code, but the graph
   models the OS instead of a codebase.
Recommendation for the demo: **option 1** — it's the shortest path to a live "brain grows as you
speak" moment, and keeps graphify as an unmodified dependency (clean MIT attribution).

### 5.5 Concrete P0 revision
- **P0-2 (was "build brain"): Mount graphify as the brain.** `pip install graphifyy` (or vendor it),
  wire its MCP server into `mcp_client.py`, add a `brain/corpus_writer.py` that mirrors sessions +
  skills + tool docs + window registry into a corpus dir, and a `/brain` command that rebuilds and
  queries. On each user command: `query_graph` → seed node → BFS expand → feed the subgraph into the
  system prompt as "relevant memory." ~1.5 days, most of it the corpus-writer.
- Pair it with `reflect.py`: after a command succeeds/fails, call graphify's `save-result` outcome
  signal so the brain self-corrects — this is your "self-evolving" demo beat, and it's deterministic
  (no flaky LLM judgment on stage).

### 5.6 graphify vs the AgentScope memory options — which to use
- **Use graphify** for the *structural* brain: the tree of commands/skills/apps and the
  locate-and-expand traversal that the pitch describes literally. It is deterministic and demoable.
- **Use AgentScope's Ollama embeddings** only if you additionally want fuzzy semantic recall over raw
  conversational text that has no clean graph structure. For the hackathon, graphify alone covers the
  headline feature; treat embeddings as optional P2.
- Skip mem0/ReMe/agentic-memory for now — heavier, and graphify + reflect already tells the
  self-improving-memory story with zero extra model spend.

---

## 6. HelixDB as the durable graph+vector memory store (the 3rd repo)

### 6.1 What HelixDB is
A **graph + vector database built from scratch in Rust**, Apache-2.0, purpose-built for "knowledge
graphs and AI memory." One store unifies graph, vector, KV, document, and relational models. Runs as
a **local background instance on port 6969** (via `helix start dev`; default in-memory, `--disk` to
persist). Queried through a **dependency-free Python SDK** that POSTs a JSON AST to `/v1/query` — the
SDK has graph traversal (`out` / `in_` / `out_e` / `in_e`), **vector search**
(`vector_search_nodes` / `vector_search_edges`, `create_vector_index_nodes`), full-text/BM25, and
ACID transactions. There is also a `helix chef` one-shot bootstrapper and a docs MCP.

### 6.2 The gap it fills that the other two can't
| Capability | graphify | AgentScope | **HelixDB** |
|---|---|---|---|
| Persistent, durable store | ✗ (rebuilds NetworkX from files each run) | partial (SQLite/Redis app layer) | ✓ ACID, disk-backed |
| **Live incremental writes** ("save each command as it's spoken") | ✗ batch rebuild | ✓ | ✓ single-writer, per-write |
| True vector KNN recall | ✗ (trigram/IDF lexical) | ✓ (embeddings + vdb) | ✓ native HNSW-style + graph in one |
| Graph traversal from a hit | ✓ BFS/DFS | ✗ | ✓ `out`/`in_`/`out_e`/`in_e` |
| Zero-token build | ✓ | n/a | needs an embedder for vectors |
| Operational weight | pure Python | pure Python | **Rust instance / container** |

HelixDB is the only one of the three that is a **real live memory substrate**: writes land durably as
they happen, and recall is vector-KNN *followed by* graph expansion in a single query — which is the
"save the command → locate the most relevant node → expand it" loop expressed literally and
persistently, surviving restarts.

### 6.3 The catch for a hackathon demo
It requires a **running Rust DB instance** (container on :6969). That's a heavier, less local-first
dependency than graphify (pure Python) or AgentScope (pip). On a Windows demo machine it means Docker
or the installed Helix binary must be up before the demo, and the default in-memory mode wipes on stop
(use `--disk`). Reliability-on-stage cost is real. It's also a *database*, not an auto-extractor: you
author the schema (node/edge labels, vector indexes) and the write/read queries yourself — there's no
"point it at a folder and get a graph" like graphify.

---

## 7. Putting all three together — the recommended architecture

```
                 voice in  ─────────────┐
 (Aradhya STT: wake word, whisper, mic) │
                                        v
                       ┌───────────────────────────────────┐
                       │  Aradhya OS body (KEEP AS-IS)      │
                       │  desktop UIA · vision · browser ·  │
                       │  NVDA out · ConfirmationGate ·     │
                       │  HookEngine · PermissionEngine ·   │
                       │  audit · CloudPrivacyGate          │
                       └───────────────┬───────────────────┘
                                       │
   ┌───────────────────────────────────┼───────────────────────────────────┐
   │ ENGINE  (from AgentScope)         │ BRAIN                              │
   │ async streaming ReAct loop ·      │  ┌─ graphify: bootstrap + explain ─┐│
   │ Gemini model+formatter ·          │  │  build graph from corpus,       ││
   │ speak-while-streaming TTS ·       │  │  locate+expand (BFS), reflect   ││
   │ barge-in interruption ·           │  └─────────────┬───────────────────┘│
   │ window-agent message bus          │  ┌─ HelixDB: durable live memory ──┐│
   │                                   │  │  write each command/outcome,    ││
   │                                   │  │  vector-KNN + graph recall      ││
   │                                   │  └─────────────────────────────────┘│
   └───────────────────────────────────┴───────────────────────────────────┘
                                       │
                          voice out (Gemini multilingual → TTS → NVDA/SAPI)
```

**Roles, non-overlapping:**
- **AgentScope → the engine.** Async streaming loop, Gemini (Aradhya has none), TTS-while-streaming,
  barge-in, window-agent bus. This is what makes the demo *feel* voice-first.
- **graphify → the brain's bootstrap + explainability.** Turn Aradhya's corpus (sessions, skills,
  tool docs, window registry) into an explainable graph; do natural-language locate-and-expand; run
  `reflect.py` for outcome-scored self-correction. Deterministic, zero-token, stage-safe.
- **HelixDB → the brain's durable substrate (optional for demo, right for product).** Persist each
  spoken command + outcome as it happens; recall by vector-KNN then graph expansion; survives
  restarts and scales.

### 7.1 Which brain for the demo — decision
The two brains **overlap** on "locate node + expand," so you don't strictly need both on stage.

- **Recommended for the hackathon: graphify alone.** Pure Python, no container, deterministic on
  stage, already ships locate-and-expand + explainable edges + outcome-scored memory. Lowest risk,
  fastest to a working "brain grows as you speak" beat (corpus-writer + rebuild).
- **HelixDB as the P1/post-hackathon durable backend.** Once the graphify brain proves the concept,
  HelixDB becomes the live, persistent memory that graphify's batch-rebuild model isn't — writes per
  command, real vector recall, ACID durability. Best "real product" answer; adds the Rust-instance
  dependency.
- **If you want the stronger pitch and can babysit a container:** run **HelixDB as the live store**
  and use **graphify's read-side heuristics** (`_score_nodes`/`_pick_seeds`/`_bfs` ideas) over
  Helix's graph for the locate-and-expand narration. More moving parts; only do this if the demo
  machine reliably runs the Helix instance.

**Net:** graphify first (demo), HelixDB second (durability), AgentScope throughout (engine). Don't
try to wire all three the night before — the safe demo is Aradhya body + AgentScope engine + graphify
brain.

---

## 8. What NOT to change
- ConfirmationGate / HookEngine / dry-run defaults / audit trail — the safety story is the judge-able
  differentiator; AgentScope has no CloudPrivacyGate equivalent.
- Desktop control, vision tools, browser automation, NVDA integration, wake-word/voice-inbox STT —
  none exist in AgentScope; this *is* Aradhya.
- Parasite + Learnings — the "self-evolving" narrative; AgentScope offers nothing comparable.
- Local-first Ollama posture — AgentScope's Ollama chat + embedding support actually reinforces it.
