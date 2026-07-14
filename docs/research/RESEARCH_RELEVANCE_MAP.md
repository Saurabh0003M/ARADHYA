# Research Relevance Map — 6 Deep-Research Reports → ARADHYA

> Maps the six research reports (moved into `~/Downloads/research/`, 2026-07-03)
> to concrete parts of the ARADHYA codebase. For each report: what it is, how
> load-bearing it is, where it lands in `src/`, and what is already built vs.
> still aspirational.
>
> These are a **different track** from the existing `docs/research/*` prompts.
> Those compare *implemented* mechanisms to big-tech (index vs. scan, transcription
> modes). These six are **forward-looking architecture + biomimetic design theory**
> and two of them (`Local Windows AI Agent Architecture`, `Biomimetic OS
> Architecture Research`) name ARADHYA and its capability-integration engine directly.
>
> **Codename note:** the source `.docx` reports use the project's original codename
> **"Parasite OS."** The repo has since renamed that engine to **Symbiont**
> (`src/aradhya/symbiont/`). Report titles and quotes below are cited verbatim from
> the sources; the codename in our own code and docs is now Symbiont.

## Verdict at a glance

| # | Report | Track | Relevance | Primary code home |
|---|--------|-------|-----------|-------------------|
| 1 | Local Windows AI Agent Architecture | Architecture | **Core blueprint** — names ARADHYA + the exact target SoC | whole `src/aradhya/` |
| 2 | Passive Perception Layer – Windows 11 | Architecture | **Load-bearing** — implementation spec for a not-yet-built layer | *new* passive layer (gap) |
| 3 | Biological inspiration: capability absorption in sea slugs | Biomimetic | **Design DNA** — the "integrate = sandbox not copy" thesis | `symbiont/`, `skills/`, `workflows/trust_boundary.py` |
| 4 | Biomimetic OS Architecture Research | Biomimetic | **Design DNA (rigorous)** — the "Symbiont" manifesto | `symbiont/`, `hooks/`, `permission_rules.py`, `agents/` |
| 5 | Microbial Evolution Mechanisms (Part 1) | Biomimetic | **Supporting** — honest analogy matrix (flags weak metaphors) | `agents/`, `learnings/`, `federation/` |
| 6 | Microbial Evolution Software Design Patterns | Biomimetic | **Supporting (deeper)** — concrete evolutionary patterns | `agents/`, `learnings/`, `symbiont/`, `model_provider.py` |

The two tracks converge on the same architecture from two directions: the Windows
reports say *what to build*; the biology reports say *how to structure and gate it*.

---

## 1. Local Windows AI Agent Architecture — Core blueprint

This is effectively a written spec of ARADHYA. It names the product, the user
(voice-first, visually impaired, Hinglish, Indian demographic) and the exact
hardware (Intel Core Ultra 5 125H — CPU/Arc iGPU/NPU, 16–32 GB UMA, no dGPU).
Maps section-by-section onto existing modules:

| Report section | Codebase status |
|----------------|-----------------|
| Passive Perception Layer (UIA, clipboard, FS, toasts, WMI) | **Gap** — no event-driven monitors yet (see report #2) |
| Obsidian-style Markdown "brain" (temporal, YAML frontmatter, decay) | **Partial** — `context_engine.py`, `core/memory/*`, `.learnings/`; no decay/temporal graph |
| Always-on voice pipeline (wake-word → VAD → STT → TTS) | **Built** — `voice/{wake_word,activation,transcriber,synthesizer,pipeline}.py` |
| Hinglish STT + NPU/OpenVINO offload (Moonshine, Whisper-Hinglish) | **Partial** — `voice/transcriber.py` exists; model choice + NPU quantization is a decision point |
| Piper TTS + NVDA injection (`nvdaController_speakSsml`) | **Built** — `voice/synthesizer.py`, `voice/nvda_output.py` |
| UIA-first active control + PiP/RDP virtualization | **Gap** — `desktop_control.py` exists but no sandboxed virtual-desktop execution |
| Capability-based tiered routing (local NPU → iGPU → cloud MCP) | **Built** — `model_provider.py`, `model_workers.py`, `providers/`, `mcp_client.py`, `cloud_safety.py` |
| LAN device pooling (Exo / llama.cpp RPC, asymmetric workloads) | **Partial** — `federation/manager.py`, `topology.py`; report's "don't split one model, split whole workloads" is a design guardrail worth adopting |

**Action value:** highest. It is the closest thing to a north-star architecture
doc. The single most actionable, not-yet-built piece it specifies is the passive
perception layer (report #2). Its memory-decay recommendation (CortexGraph +
Rowboat: mutate YAML `use_count`/`decay_rate` instead of appending) is a concrete
upgrade to the current memory store.

## 2. Passive Perception Layer – Windows 11 — Load-bearing (build spec)

A focused implementation guide for the one big gap above. Per-signal it names the
native API, the Python wrapper, the CPU/battery cost, and the privacy caveat:

- **UI focus / tree** — `SetWinEventHook(EVENT_SYSTEM_FOREGROUND)` + UIA event handlers (not screenshots+OCR). `<0.1%` idle.
- **Clipboard** — `AddClipboardFormatListener` + `WM_CLIPBOARDUPDATE` on a message-only window. `~0%` (kernel sleep). Must regex-drop passwords/keys.
- **Filesystem** — `watchdog` (wraps `ReadDirectoryChangesW`) with debouncing, scoped to Downloads/Documents.
- **Notifications** — `UserNotificationListener` (WinRT); requires explicit user consent.
- **System state** — `psutil` + `WM_POWERBROADCAST` for power-aware model routing.

**Relevance:** this is a ready-to-implement design for a new
`src/aradhya/perception/` package. It fits the existing philosophy exactly:
event-driven, local-first, privacy-gated. It also feeds the "power-aware model
routing" that `runtime_profile.py` / `hardware_profile.py` already gesture at
(degrade to cloud when battery low). **Ties into #3/#4:** this layer *is* the
"rhinophore ganglion / distributed sensing" the biology reports call for — edge
daemons that filter before waking the central agent, protecting the LLM context
window.

## 3. Biological inspiration: capability absorption in sea slugs — Design DNA

The conceptual origin of the "Symbiont" identity. Kleptocnidy (acquire a
defensive cell), kleptoplasty (acquire an organelle), cerata (multifunction detachable
modules), aposematism (honest warning colors), decentralized ganglia. Its
software mapping table is the design rationale behind existing modules:

| Biology | Report's software mapping | Where it lives now |
|---------|---------------------------|--------------------|
| Kleptocnidy (module ingestion) | object-capability / plugin integration | `symbiont/pipeline.py` (ACQUIRE→…→INTEGRATE), `skills/skill_installer.py` |
| Cerata (multifunction + autotomy) | hot-swappable, fault-tolerant modules | `skills/`, `agents/subagent_*`, `symbiont/checkpoint.py` |
| Distributed sensing (naked gill) | event-driven watchers, no polling | passive layer (gap, #2) |
| Decentralized ganglia | multi-agent / actor model | `agents/subagent_runner.py`, `subagent_registry.py` |
| Aposematism (honest signal) | explicit trust/permission, provenance | `permission_rules.py`, `confirmation_gates.py`, `hooks/` |
| Regeneration / endosymbiosis | forkable, revocable skills | `skills/skill_loader.py`, `symbiont/ledger.py` |

**Most important single idea (and it's already in memory):** the *"integrate =
sandbox-not-copy"* correction. The report stresses that a nudibranch keeps
acquired organelles working **without merging their genes into its own DNA**. That
directly validates ARADHYA's rule (AGENTS.md safety rule): ingested host code
must **never** be merged into the core or run with ambient authority — it's
isolated in `Hosts/` and gated. Report #4 makes this rigorous.

## 4. Biomimetic OS Architecture Research — Design DNA (rigorous)

The heavyweight, citation-dense version of #3, written explicitly for "the
Architects of Parasite OS" (its term). It upgrades the metaphors into named CS mechanisms
with maturity ratings, and gives the 7-point design manifesto ARADHYA's symbiont
engine implements:

| Manifesto principle | ARADHYA mechanism | Status |
|---------------------|-------------------|--------|
| I. Ingest, don't execute (kleptocnidy) | AST parse → strip ambient calls → sandbox | `symbiont/analyzer.py`, `pipeline.py` — **partial** (report pushes WASM/WASI compilation; current is checkpoint-based isolation) |
| II. OS is an intent filter, not a resource manager | manifest-only / least-privilege runtime | `permission_rules.py`, `tools/runtime_policy.py`, `confirmation_gates.py` |
| III. Radical modularity + autotomy ("let it crash") | supervised isolated nano-processes | `agents/subagent_runner.py`, `symbiont/checkpoint.py` |
| IV. Peripheral perception (rhinophore) | edge daemons filter before central LLM | passive layer (gap, #2) |
| V. Hierarchical peripheral execution (octopus) | brain issues intent; periphery computes | `agents/`, `assistant_planner.py` |
| VI. Cryptographic honest signaling (aposematism) | verifiable capability attestation | `symbiont/ledger.py`, `audit_logger.py` — **partial** (no crypto attestation yet) |
| VII. Evolutionary routing (Physarum) | route flux through competing modules, starve losers | **Gap** — no competitive module selection |

**The "where the metaphor breaks down" section is the most valuable part for an
implementer:** it warns that software needs *stricter* boundaries than biology
(Turing-complete code has no physical bounds → sandboxing must be mathematically
enforced), that dormant code costs ~0 (so ARADHYA can hoard far more capabilities
than an organism), and that software has no natural decay (so it needs
*synthetic* garbage collection). These are direct guardrails on the symbiont
engine and the memory decay design.

**Notable external reference:** it cites AgenticOS (arXiv 2606.21129) — an
"intent-oriented OS" — as the closest published analogue. Worth a look for the
Manifest/Ghost-Kernel routing model.

## 5 & 6. Microbial Evolution (Mechanisms + Software Design Patterns) — Supporting

A matched pair: #5 is the mechanism survey + honest analogy matrix; #6 is the
deeper, pattern-by-pattern translation with an "Intellectual Honesty Matrix."
Their chief virtue is **calibration** — they explicitly grade each metaphor
(load-bearing / moderate / superficial / decorative / dangerous), which stops the
biology from being over-applied. The load-bearing ones that map to real ARADHYA
work:

| Mechanism | Pattern | ARADHYA hook | Verdict from reports |
|-----------|---------|--------------|----------------------|
| Quasispecies / mutant swarm | ensemble of agent/prompt variants; keep the diverse population | `agents/subagent_*`, `model_workers.py` | **Load-bearing** |
| Error threshold / error catastrophe | cap self-modification; a strong remote model "proofreads" local prompt mutations (ExoN analog) | `llm_planner.py`, `cloud_safety.py`, tiered routing | **Load-bearing** |
| Horizontal gene transfer | runtime skill/plugin sharing between peers (WASM "plasmids") | `federation/manager.py`, `skills/skill_installer.py` | **Load-bearing** |
| SOS / stress-induced mutagenesis | raise temperature/exploration on repeated failure, then settle | `agent_loop.py`, `model_provider.py` | **Load-bearing** |
| Survival of the flattest | prefer fuzzy NL/embedding interfaces over brittle strict schemas | `json_extractor.py`, planner boundary | **Load-bearing** — tension with strict-schema tool calls; worth a conscious tradeoff |
| CRISPR-Cas adaptive immunity | append-only audit log of past threats → vector-match to pre-empt repeats | `learnings/learnings_engine.py`, `audit_logger.py`, `.learnings/ERRORS.md` | **Moderate–strong** |
| Haploidy / diploidy masking | just "test before commit" | — | **Superficial** (flagged as such) |
| Natural selection = objective function | **dangerous** — agents "evolve" toward reward-hacking / min-energy, not user utility | safety layer | **Superficial + warning** |

**Relevance:** these are less "build this" and more "here are the load-bearing
vs. decorative framings so the symbiont/evolution language in the codebase stays
honest." The CRISPR→audit-log mapping most directly matches an existing module
(`learnings/`). The "survival of the flattest" point is a genuine open design
tension: ARADHYA's planner leans on strict schemas (robust against LLM garbage),
but the reports argue fuzzy interfaces survive environment drift better — a
tradeoff worth naming explicitly rather than defaulting.

---

## Synthesis — how to use this

1. **#1 + #2 are the actionable pair.** The biggest *buildable* gap they expose
   is the **event-driven passive perception layer** (`src/aradhya/perception/`),
   which is also what the biology reports call the rhinophore/distributed-sensing
   tier. Highest-value next feature grounded in this research.

2. **#3 + #4 are the "why," not the "what."** They justify and stress-test the
   existing `symbiont/` engine and the safety model. The single most important
   validated decision: **integrate by sandboxing, never by merging into core** —
   already recorded in project memory and enforced in AGENTS.md. #4's
   "metaphor-breaks-down" section is the guardrail list; #4's manifest/attestation
   and Physarum "competitive routing" are the two genuine *new* asks (crypto
   attestation on integrated modules; competitive module selection).

3. **#5 + #6 keep the metaphors honest.** Use their honesty matrices before
   adding any more biological naming to the codebase — several mappings (haploidy,
   "natural selection = reward") are explicitly flagged as superficial or
   dangerous. The load-bearing four (quasispecies→ensembles, error-threshold→
   bounded self-mod, HGT→runtime skill sharing, SOS→adaptive exploration) each
   attach to a real module.

4. **Contradiction to watch:** "survival of the flattest" (favor fuzzy interfaces)
   vs. ARADHYA's current strict-schema planner. Not a bug — a deliberate tradeoff
   the reports surface. Decide per-boundary rather than globally.

**Suggested repo homes if adopting:** move/copy these six into `docs/research/`
alongside this map so they're versioned with the code that cites them (currently
they live only in `~/Downloads/research/`, outside the repo).
