# AI Handoff: Aradhya vs Context-Aware Desktop Mentor Vision — Technical Audit

> **Audience:** Downstream AI agents (Codex, Opus, Cursor Agent, etc.) tasked with
> implementing missing capabilities. **Not** written for end-user reading.
>
> **Generated:** 2026-06-08 (revised) · **Workspace:** `F:/ARADHYA` · **Audit scope:**
> `src/aradhya/`, `core/skills/`, `core/memory/`, `tests/`, `docs/`

---

## 0. Instructions for the Receiving AI

### 0.1 Your mission

Build a **general-purpose, context-aware desktop Operating Intelligence** on top of the
existing Aradhya platform. The user described their vision through **illustrative examples**
(coding lessons, job research, disk cleanup, LLM hardware coaching). Those examples are
**non-normative** — they demonstrate **capability classes** and an **interaction philosophy**,
not four fixed products to hardcode.

**Do:**
- Implement **reusable platform behaviors** (perceive → plan → do/teach → gate → summarize).
- Generalize patterns (e.g. Parasite GC dry-run) across maintenance, forms, file ops.
- Add tools and workflow machinery that support **many** tasks in each capability class.

**Do not:**
- Ship hardcoded verticals like `government-jobs` or `coding-tutor` as the primary architecture.
- Treat example triggers ("find government jobs", "SSD full") as the only acceptance tests.
- Rewrite the agent loop, safety stack, or session store unless a bug fix requires it.

### 0.2 Mandatory reading before coding

| Priority | File | Why |
|----------|------|-----|
| P0 | `AGENTS.md` | Safety rules — confirmation gates, dry-run default, audit logging |
| P0 | `SECURITY.md` | Dangerous tools list and policy |
| P0 | This document §2 | Product vision (capability classes, not examples) |
| P0 | This document §3–§7 | Gap analysis and platform backlog |
| P1 | `src/aradhya/assistant_core.py` | Orchestration, tool registry, plan confirmation |
| P1 | `src/aradhya/agent_loop.py` | ReAct loop, `DANGEROUS_TOOLS`, per-tool gates |
| P1 | `docs/OI_VISION.md` | Product thesis — aligns with mentor vision |
| P2 | `src/aradhya/tools/tool_registry.py` | How to register `@tool_definition` tools |
| P2 | `src/aradhya/skills/skill_loader.py` | Intent-based skill loading (exists but unwired) |
| P2 | `src/aradhya/parasite/pipeline.py` | `gc()` — reference for analyze → confirm → execute |

### 0.3 Status taxonomy (use consistently in your work)

| Status | Meaning |
|--------|---------|
| `IMPLEMENTED` | Code exists, registered, callable via agent loop |
| `PARTIAL` | Some code exists; capability-class requirement not fully met |
| `STUB` | Placeholder returns `ready=False` or IPC warning |
| `BROKEN` | Code exists but fails at runtime due to API mismatch |
| `MISSING` | No code; may be mentioned in docs/skills only |
| `DISABLED` | Code/skill exists but `enabled: false` or opt-in off |
| `DOC_DRIFT` | Documented but not implemented |

### 0.4 Safety constraints (never violate)

From `AGENTS.md`:

1. **Confirmation gate** required before: `run_command`, `write_file`, `delete_file`,
   `move_file`, `open_path`, `open_url`, `browser_click`, `browser_type`,
   `browser_submit`, `clipboard_write`, `schedule_task`.
2. **`allow_live_execution`** defaults `false` in preferences.
3. **Audit everything** — `~/.aradhya/audit/audit.jsonl` via event-sourcing.
4. **Trust boundaries** — never bypass CAPTCHAs, login protections, or security mechanisms;
   detect and hand off to human (not yet encoded; must add as platform policy).
5. **Local-first** — cloud via OpenRouter only through `CloudPrivacyGate`
   (`src/aradhya/cloud_safety.py`).
6. **New tools** → register in `assistant_core._build_tool_registry_from_policy()`.
7. **New skills** → `core/skills/<name>/SKILL.md` — prefer **general workflow skills**
   over per-example verticals (see §2.6).
8. **Tests** → `tests/unit/`, run: `pytest --override-ini="addopts="`.

### 0.5 Overall readiness (machine-parseable)

```yaml
readiness:
  core_oi_platform_percent: 70
  mentor_vision_coverage_percent: 15   # capability classes, not example verticals
  safety_stack_percent: 80
  product_ready: false
  product_goal: general_context_aware_desktop_mentor  # not four fixed verticals
  recommended_first_platform_slice: trust_boundary_workflow  # generalize Parasite GC pattern
```

---

## 1. Project Context (Architecture)

### 1.1 What Aradhya is

Local-first **Operating Intelligence (OI)** for Windows. Ollama default LLM;
OpenRouter fallback with privacy gate. Autonomous orchestrator for files, shell,
browser, vision (OCR), voice, scheduler, subagents, dynamic skills.

### 1.2 Execution pipeline

```
User input (CLI / hotkey / Telegram / floating icon IPC)
  → main.py / daemon.py (slash commands)
  → assistant_core.handle_transcript() / handle_wake()
  → IntentPlanner (rules) OR LLMIntentPlanner (JSON classifier)
  → PlanAction (kind: AGENT_TASK | PLANNED_TASK | OPEN_PATH | …)
  → [if requires_confirmation] pending_plan → user says "yes proceed"
  → _execute_plan()
       → AGENT_TASK → AgentLoop (ReAct: prompt → model → tools)
       → PLANNED_TASK → planning_workflow sequential steps
  → state_store.py (SQLite sessions + audit)
```

Key symbols:

- `AradhyaAssistant` — `src/aradhya/assistant_core.py`
- `AgentLoop` — `src/aradhya/agent_loop.py`
- `LLMIntentPlanner._route_decision` — `src/aradhya/llm_planner.py:168-226`
- `IntentPlanner` — `src/aradhya/assistant_planner.py`
- `PlanKind` — `src/aradhya/assistant_models.py`

### 1.3 Tool registration point

```python
# src/aradhya/assistant_core.py:753-770
def _build_tool_registry_from_policy(self, policy):
    registry = ToolRegistry(policy=policy)
    for tool in (
        *ALL_FILE_TOOLS,      # file_tools.py
        *ALL_SHELL_TOOLS,      # shell_tools.py
        *ALL_SYSTEM_TOOLS,    # system_tools.py (open_path, open_url, clipboard_*)
        *ALL_SESSION_TOOLS,
        *ALL_WEB_TOOLS,       # web_tools.py (web_search, web_fetch)
        *ALL_POWER_TOOLS,
        *ALL_BROWSER_TOOLS,   # browser_tools.py
        *ALL_VISION_TOOLS,    # vision_tools.py
        *ALL_SKILL_INSTALLER_TOOLS,
        *ALL_LEARNINGS_TOOLS,
        *ALL_SCHEDULER_TOOLS,
        *ALL_SUBAGENT_TOOLS,
    ):
        registry.register_function(tool)
```

### 1.4 Skill injection (current vs intended)

**Current (token-expensive):** All enabled skills injected via
`skill_registry.active_instructions()` in `_build_agent_system_prompt()` at
`assistant_core.py:820-823`. Capped at `MAX_AGENT_CONTEXT_CHARS`.

**Intended but unwired:** `load_skills_for_intent()` in
`src/aradhya/skills/skill_loader.py:92` — scores user prompt against skill
`intents`, returns top-N skills. **Only used in tests**
(`tests/unit/test_intent_skill_loader.py`). **Wire this before adding many new skills.**

### 1.5 User context and memory (current)

| Store | Path | Schema | Role in mentor vision |
|-------|------|--------|------------------------|
| Rules | `core/memory/user_context/rules.md` | Freeform markdown | Tone, safety prefs, interaction mode |
| Notes | `core/memory/user_context/notes.md` | Freeform (name, role) | Light personalization |
| Commands | `core/memory/user_context/commands.json` | Empty `{}` | Custom slash commands |
| Preferences | `core/memory/preferences.json` | Model, roots, execution policy | Runtime policy |
| Profile | `core/memory/profile.json` | Model/voice config | Not user task context |

**Gap:** No **structured user context store** for assisted execution (forms, applications,
repeated personal fields). Needed for *any* "fill this for me from what you know" task class,
not only one example domain.

### 1.6 Confirmation and trust-boundary flow

**Layer A — Plan confirmation** (`assistant_core.py:423-438`):
- Plans with `requires_confirmation=True` stored in `state.pending_plan`.
- User must say phrase in `_confirmation_phrases` (e.g. `"yes proceed"`, `"confirm"`, `"y"`).

**Layer B — Per-tool dangerous gate** (`agent_loop.py:530-543`, `_execute_with_gate`):
- `DANGEROUS_TOOLS` frozenset triggers `CliConfirmationGate` / `TelegramConfirmationGate`
  per individual tool call **after** plan is confirmed.

**Layer C — Runtime policy** (`tools/runtime_policy.py`):
- `live_execution_enabled` (= `preferences.allow_live_execution`, default false)
- `mutation_granted` (= true after plan confirmation in `_execute_agent_task`)

**Missing Layer D — Trust-boundary workflow engine:**
- No generalized state machine for: **analyze → present plan → user selects actions →
  execute with dry-run default → mandatory checkpoint before irreversible/sensitive steps**
  (submit forms, delete files, change system settings).
- No `browser_submit` tool despite being in `DANGEROUS_TOOLS`.
- No platform CAPTCHA / security-handoff policy.

---

## 2. Product Vision (Capability Classes — Normative)

> **§2 is the acceptance target.** §2.5 lists examples only to show how classes apply.

### 2.1 One-sentence vision

A **local, screen-aware, voice-capable desktop mentor** that **understands the user's real
context**, **does tedious work autonomously**, **teaches when asked**, and **keeps the user
in control of risky or irreversible actions** — across **many** task types, not a fixed set.

### 2.2 Universal interaction loop (every task class)

All high-level goals should follow this loop:

```
1. PERCEIVE   — screen, active window, files, system state, user memory
2. UNDERSTAND — clarify goal (1–2 questions if needed), infer skill level
3. PLAN       — numbered steps (3–7), small and reversible where possible
4. ACT        — execute OR teach (see §2.4 modes); prefer doing over describing
5. GATE       — pause before irreversible, sensitive, or security-boundary actions
6. SUMMARIZE  — what was done, what changed, what user should do next
```

**Acceptance:** Platform supports this loop generically via planner + agent + workflow
checkpoints — not via one-off scripts per user phrase.

### 2.3 Six capability classes (build these, not example apps)

| Class | What it means | Platform behaviors required |
|-------|---------------|----------------------------|
| **A. Perception & context** | Know what user sees and what's on the machine | Screen capture/OCR/vision, active window, filesystem index, hardware profile, user context injection |
| **B. Autonomous execution** | Act on desktop, browser, files, shell (gated) | Tool registry, browser multi-context, desktop input (future), file mutate with confirm |
| **C. Interactive teaching & coaching** | Learn-by-doing in user's environment | Tutor persona, pacing, in-context feedback, "teach me" vs "do it" modes |
| **D. Research & assisted completion** | Gather sources, compare, help with repetitive UI work | Multi-source research, summarization, form assist, **hard stop** at trust boundaries |
| **E. System diagnosis & safe maintenance** | Inspect, explain, recommend, act only after choice | Structured analysis reports, ranked safe actions, dry-run default, confirm-before-delete |
| **F. Reality-grounded technical guidance** | Advice matched to *this* machine and skill level | Hardware detection, feasible recommendations, optional click-by-click UI guidance |

A single user request may span multiple classes (e.g. "help me fine-tune a model" = F + D + C).

### 2.4 Interaction philosophy (normative)

| Principle | Requirement |
|-----------|-------------|
| **Autonomy** | Prefer executing over listing steps when tools allow |
| **Mentor tone** | Patient, encouraging, step-by-step plain language |
| **Two modes** | "Do it for me" vs "Teach me while you do it" (mode switch not implemented) |
| **Multimodal input** | Voice and text; user can override with mouse/keyboard anytime |
| **Transparency** | Explain what you're doing and why |
| **User sovereignty** | Assistant recommends; user approves risky actions |
| **Adaptive pacing** | Small next steps; don't jump difficulty |

Encode modes in `rules.md` / assistant state / system prompt — not in per-example skills.

### 2.5 Illustrative examples (NON-NORMATIVE)

These show how capability classes combine. **Do not treat them as the product scope.**

| User might say | Classes involved | Example only — same class applies to |
|----------------|------------------|--------------------------------------|
| "Help me learn Python in VS Code" | A, C, B | Learn Excel, Git, any editor-based skill |
| "Find government jobs for me" | D, B | Compare insurance, courses, products, any multi-source research + forms |
| "My SSD is almost full" | E, A | Clean dev caches, old projects, duplicate downloads, any maintenance |
| "Help me fine-tune an LLM" | F, D, C | Set up Docker, cloud GPU, any hardware-bound technical learning |

**Wrong approach:** `core/skills/government-jobs/`, `coding-tutor/` as primary architecture.

**Right approach:** Platform tools + workflow engine + 1–2 **general** skills (e.g.
`guided-workflows`, `safe-maintenance`) that teach the agent how to run the universal loop.

### 2.6 Skill strategy for receiving AI

| Approach | When |
|----------|------|
| **Platform tools** | Repeated machinery (disk analysis, tab management, hardware probe, trust gates) |
| **Workflow engine** | Analyze → plan → confirm → execute pattern shared across classes |
| **General skills** | Markdown instructions for loop + safety + class behaviors |
| **Domain skills** | Optional, user-installed extensions — not core deliverables |

Existing `web-search` skill is useful for class D but its rule *"never submit forms"*
must coexist with a **platform trust-boundary policy** for assisted form completion
(stop before submit/CAPTCHA), not be overridden by a job-specific skill.

### 2.7 Safety and privacy (normative, general)

- Local-first; reputable services when external access needed
- No exfiltration to unknown APIs
- No CAPTCHA/login/security bypass — detect and hand off
- Warn when sensitive data visible on screen (passwords, OTPs, IDs)
- No destructive system changes without informed consent
- Sensitive stored context only with user awareness

---

## 3. Capability-Class Audit (Current Codebase)

Audit organized by **§2.3 classes**, not by user examples. Technical file references preserved.

### 3.A Perception & context

| Behavior | Status | Implementation | Gap |
|----------|--------|----------------|-----|
| Desktop screenshot | `IMPLEMENTED` | `vision_tools.screen_capture` | — |
| OCR text | `IMPLEMENTED` | `vision_tools.screen_read_text` (4000 char cap) | — |
| Vision LLM / UI understanding | `MISSING` | `model_provider.py` no multimodal API | Class A core gap |
| Active window title | `PARTIAL` | `context_engine.py` | No file/cursor/deep UI state |
| Filesystem index | `IMPLEMENTED` | `assistant_indexer.py`, context engine | Not size-oriented |
| Hardware summary | `PARTIAL` | `topology.py` — CPU count, RAM, disk; GPU `"unknown"` | Class F depends on this |
| User rules/notes injection | `IMPLEMENTED` | `assistant_core._read_user_context()` | Unstructured only |
| Structured user task context | `MISSING` | — | Forms, repeated fields, any class D task |
| Continuous screen awareness | `STUB` | Floating icon; `main.py:982-987` not implemented | Proactive mentoring |

**Files:** `tools/vision_tools.py`, `context_engine.py`, `topology.py`, `assistant_indexer.py`

**Skill:** `screen-reader` — `enabled: false`; intents `SCREEN_CAPTURE`, `SCREEN_DESCRIBE`,
`SCREEN_GUIDE`. Closest to class A+C but disabled and instruction-only.

---

### 3.B Autonomous execution

| Behavior | Status | Implementation | Gap |
|----------|--------|----------------|-----|
| File read/write/search | `PARTIAL` | `file_tools.py` — no delete/move | Class E blocked |
| Shell commands | `IMPLEMENTED` | `shell_tools.run_command` (gated, 30s timeout) | Ad hoc vs structured |
| Browser automation | `PARTIAL` | Selenium single-tab `browser_tools.py` | No multi-tab/window |
| Desktop mouse/keyboard | `MISSING` | Docs claim PyAutoGUI; not in code | Class C, F UI guidance |
| UI overlay / highlight | `MISSING` | — | Click-by-click coaching |
| Open path/URL | `IMPLEMENTED` | `system_tools.py` (gated) | — |
| Subagent parallel work | `IMPLEMENTED` | `subagent_tools.py` | Read-only mutations |

**Browser tools** (`browser_tools.py`, Selenium, global `_active_driver`):

| Tool | Status | DANGEROUS_TOOLS |
|------|--------|-----------------|
| `browser_open`, `browser_navigate` | `IMPLEMENTED` | No (decorator confirm only) |
| `browser_click`, `browser_type`, `browser_execute_js` | `IMPLEMENTED` | Yes |
| `browser_read`, `browser_screenshot`, `browser_close` | `IMPLEMENTED` | No |
| `browser_submit` | `MISSING` | Listed but no handler |
| `browser_new_tab`, `browser_switch_tab`, `browser_list_tabs` | `MISSING` | — |

**Doc drift:** `tools/README.md` claims Playwright; code is Selenium.

**Web HTTP:** `web_search`, `web_fetch` in `web_tools.py` — class D building blocks.

---

### 3.C Interactive teaching & coaching

| Behavior | Status | Notes |
|----------|--------|-------|
| Tutor persona / mentor prompt | `MISSING` | Generic "Windows assistant" in `_build_agent_system_prompt` |
| Do-it vs teach-me mode | `MISSING` | No state toggle |
| In-context feedback loop | `MISSING` | No observe → user acts → evaluate → correct cycle |
| Adaptive difficulty / next task | `MISSING` | — |
| Progress tracking | `MISSING` | — |
| Screen-aware coaching | `PARTIAL` | Agent could call `screen_read_text`; no pedagogy machinery |
| Multi-step guided plans | `PARTIAL` | `planning_workflow.py` — generic, not tutor-specific |

**Related skills (instruction-only, not tutor platform):** `dev-assistant`, `agency-engineering-review`

**Gap summary:** Class C is almost entirely **prompt + workflow** work on existing agent loop,
not a separate "coding tutor" product.

---

### 3.D Research & assisted completion

| Behavior | Status | Notes |
|----------|--------|-------|
| Web search + fetch | `IMPLEMENTED` | `web_tools.py` |
| Multi-source open/compare | `PARTIAL` | Sequential fetch or single Selenium tab; no tab orchestration |
| Structured comparison output | `MISSING` | Model improvises; no schema |
| Form field assist | `PARTIAL` | `browser_type` per-field with per-call gates |
| Pre-submit checkpoint | `MISSING` | No `browser_submit`; `press_enter` can submit accidentally |
| CAPTCHA / security handoff | `MISSING` | No platform policy |
| Parallel research | `PARTIAL` | `spawn_subagent` |

**Skill note:** `web-search/SKILL.md` forbids form submit — correct for **unassisted** web tools.
Platform needs **trust-boundary layer** for *assisted* completion (class D), not a domain skill.

**Agent budget:** `max_iterations=10` (`assistant_core.py:562`) may be tight for research + assist flows.

---

### 3.E System diagnosis & safe maintenance

| Behavior | Status | Notes |
|----------|--------|-------|
| Shallow directory listing | `IMPLEMENTED` | `list_directory` — single level |
| Recursive size tree | `MISSING` | — |
| Ranked cleanup recommendations | `MISSING` | `file-finder` skill → ad hoc PowerShell |
| Duplicate / stale artifact detection | `MISSING` | — |
| Structured analysis report | `PARTIAL` | **Parasite `gc()`** has right schema — wrong scope |
| Safe delete/move tools | `MISSING` | In `DANGEROUS_TOOLS` but not registered |
| User picks actions → execute | `PARTIAL` | Parasite GC + plan confirm; not generalized |

**Reference pattern — Parasite GC** (`parasite/pipeline.py:422`):
```python
def gc(..., dry_run=True) -> dict:
    # { dry_run, results[], errors[], freed_bytes, actions_planned, actions_taken }
    # Per-item: { target, action, path, freed_bytes, status }
```
CLI: `/parasite gc --apply` + `CliConfirmationGate`. Scope: `Hosts/` repo only.

**This pattern is the template for class E for ANY maintenance task** (disk, caches, downloads),
not only a `disk-cleanup` skill.

---

### 3.F Reality-grounded technical guidance

| Behavior | Status | Notes |
|----------|--------|-------|
| CPU model name | `MISSING` | `topology.py` — core count only |
| RAM, disk | `IMPLEMENTED` | `topology.py` |
| GPU / VRAM | `STUB` | `"gpu": "unknown"` hardcoded |
| Hardware → recommendation mapping | `MISSING` | `model_setup.py` static catalog only |
| Click-by-click external UI guide | `PARTIAL` | Browser tools exist; no overlay |
| Explain in plain language | `PARTIAL` | Model-dependent; no coach persona |

**Static catalog** (`model_setup.py`): `gemma3:4b`, `phi4-mini`, `qwen2.5-coder:7b` —
not derived from detected hardware.

---

### 3.G Workflow orchestration & voice (cross-cutting)

#### Voice

| Behavior | Status | File |
|----------|--------|------|
| Audio inbox + STT | `IMPLEMENTED` | `voice/pipeline.py` |
| Push-to-talk + hotkey | `IMPLEMENTED` | `voice/activation.py` |
| TTS | `IMPLEMENTED` `DISABLED` | `voice/synthesizer.py`; default off |
| Wake-word | `BROKEN` | `voice/wake_word.py:69` — see §5.1 |
| Daemon voice | `MISSING` | `daemon.py` |

#### Desktop shell

| Component | Status | Notes |
|-----------|--------|-------|
| Floating icon | `PARTIAL` | Mic/debate wired; screen/browser stubs |
| Daemon tray | `IMPLEMENTED` | Disconnected from floating icon / IPC |
| IPC | `PARTIAL` | Dual protocols `.aradhya_ipc` + `_queue` |

#### Planner / skills

**Routed intents** (`llm_planner._route_decision:174-216`): `OPEN_PATH`, `OPEN_SECURITY_BLOGS`,
`LOCATE_TXT_DENSE_FOLDER`, `OPEN_YESTERDAYS_PROJECT`, `OPEN_RECENT_GAME`, `SCREEN_CONTROL`,
`EXTERNAL_DOCUMENT_HANDOFF`, `DEBATE_RESEARCH`, `TOGGLE_DEBATE`, `GENERAL_CHAT`

**All skill intents → `UNKNOWN`** (lines 218-226). Skills only help if flow reaches `AGENT_TASK`
with instructions injected.

**Stub executors** (`assistant_system_tools.py`): `plan_screen_control`, `plan_document_handoff`,
`plan_debate_research` — all `ready=False`.

**Fix for receiving AI:** Route skill intents → `AGENT_TASK` + `load_skills_for_intent()`.

---

## 4. Complete Tool Inventory

### 4.1 File tools (`file_tools.py`)

| Tool | Registered | Notes |
|------|------------|-------|
| `read_file` | Yes | max_lines default 200 |
| `list_directory` | Yes | Single level |
| `search_files` | Yes | Glob |
| `write_file` | Yes | DANGEROUS_TOOLS |
| `delete_file` | **No** | In DANGEROUS_TOOLS — not implemented |
| `move_file` | **No** | Same |

`ALL_FILE_TOOLS` line 180: `[read_file, list_directory, search_files, write_file]`

### 4.2–4.6

See §3.B for vision, browser, web, system, shell tools. Full list in original registry at
`assistant_core.py:753-770`.

---

## 5. Known Bugs (Fix Before Feature Work)

### 5.1 Wake-word transcriber API (`P0`)

- **File:** `src/aradhya/voice/wake_word.py:69`
- **Bug:** `self.voice_manager.transcriber` does not exist
- **Fix:** Use `_get_transcriber().transcribe(audio_path, dest)` → `FileTranscription.transcript_text`

### 5.2 Phantom dangerous tools (`P0`)

- **Bug:** `delete_file`, `move_file`, `browser_submit` in safety sets, no handlers
- **Fix:** Implement and register OR remove from `DANGEROUS_TOOLS` and docs

### 5.3 Skill loader not wired (`P0`)

- **File:** `assistant_core.py:820-823`
- **Fix:** Use `load_skills_for_intent()` instead of `active_instructions()` for agent tasks

### 5.4 Skill intents don't route (`P0`)

- **File:** `llm_planner.py:218-226`
- **Fix:** Map skill intents → `AGENT_TASK`

### 5.5 Documentation drift (`P0`)

| Document | False claim |
|----------|-------------|
| `tools/README.md` | PyAutoGUI, Playwright, delete_file in file_tools |
| `OI_ROADMAP.md` | browser submit, wake-word, intent-skills "completed" |
| `skills/README.md` | Intent injection in production |

---

## 6. Bundled Skills Registry

| Skill | enabled | Class relevance | Notes |
|-------|---------|-----------------|-------|
| `screen-reader` | **false** | A, C | Enable + platform perception work |
| `web-search` | true | D | Read-only; pair with trust-boundary policy |
| `file-finder` | true | E (weak) | Ad hoc shell recipes |
| `dev-assistant` | true | C (weak) | Dev context, not general tutor |
| `voice-notes` | true | G | Voice pipeline |
| `daily-briefing` | true | A, E (weak) | |
| `app-launcher`, `system-tools` | true | B | |
| `agency-engineering-review`, `sprint_factory` | true | — | Orthogonal to mentor vision |

### Recommended new skills (general, not example-vertical)

```
core/skills/guided-workflows/SKILL.md    # Universal loop §2.2, class D assist rules
core/skills/safe-maintenance/SKILL.md    # Class E: analyze → rank → confirm → execute
```

Optional thin skills can extend via `skill_installer` — do not hardcode example domains in core.

---

## 7. Implementation Backlog (Platform Capabilities)

Prioritized by **dependency order** and **reuse across classes**, not by user examples.

### P0 — Correctness and wiring (do first)

| ID | Task | Acceptance |
|----|------|------------|
| P0-1 | Fix `wake_word.py` | Wake word triggers without exception; add test |
| P0-2 | Resolve phantom tools | Every `DANGEROUS_TOOLS` name has handler or is removed |
| P0-3 | Wire `load_skills_for_intent` | ≤5 matched skills in agent prompt |
| P0-4 | Route skill intents → `AGENT_TASK` | e.g. `WEB_SEARCH` executes, not "unsupported" |
| P0-5 | Align docs with code | No false completion claims |

---

### P1 — Platform capabilities (core mentor vision)

#### P1-1: Trust-boundary workflow engine (highest leverage)

**Classes:** D, E, B (all gated execution)

**What:** Generalize Parasite GC + plan confirmation into reusable workflow machinery:
- States: `ANALYZE` → `PLAN` → `USER_SELECTS` → `DRY_RUN` → `CONFIRM` → `EXECUTE` → `SUMMARIZE`
- Mandatory checkpoints before: submit, delete, system mutation, security UI
- CAPTCHA detection hook (DOM heuristics + optional OCR)

**Files to add/modify:**
- `src/aradhya/workflows/trust_boundary.py` (or extend `planning_workflow.py`)
- `src/aradhya/hooks/` — PreToolUse rules for submit-like actions
- `browser_tools.py` — `browser_submit` with forced checkpoint
- Tests: `tests/unit/test_trust_boundary_workflow.py`

**Acceptance:**
- Any form-assist flow stops before submit with standard handoff message
- Any maintenance flow presents structured plan before delete
- Works for arbitrary domains — no job-specific code

**Reference:** `parasite/pipeline.py:422`, `tests/unit/test_parasite_gc.py`

---

#### P1-2: Structured analysis + action tools (class E pattern)

**What:** Tools that produce **JSON reports** consumable by workflow engine:
- `analyze_disk_usage(roots, depth)` → size tree, candidates
- `build_maintenance_plan(analysis_json)` → ranked actions with safety scores
- `execute_maintenance_plan(plan_json, dry_run)` → per-item results

**Also:** Implement `delete_file`, `move_file` with path policy + trust-boundary integration.

**Files:** `src/aradhya/tools/maintenance_tools.py` (prefer general name over `disk_tools.py`)

**Skill:** `core/skills/safe-maintenance/SKILL.md` — teaches class E loop, not "SSD only"

**Acceptance:** "My disk is full" *and* "clean old caches in this project" both work via same machinery.

---

#### P1-3: Enhanced perception (class A)

**What:**
- Multimodal path in `model_provider.py` (screenshot → vision model)
- Enable/fix `screen-reader` skill
- Optional: screen watch IPC wiring (`main.py` stub)

**Acceptance:** Agent can describe UI beyond OCR text; screen guidance skill active.

---

#### P1-4: Structured user context store (class D, general)

**What:**
- `core/memory/user_context/structured_profile.json` + schema
- CLI `/profile` or wizard to edit fields user opts in to store
- `assistant_core` injection separate from freeform notes
- Agent flags unknown fields during assist

**Acceptance:** Form assist works for **any** multi-field web form, not one portal.

---

#### P1-5: Multi-context browser tools (class D)

**What:** `browser_new_tab`, `browser_switch_tab`, `browser_list_tabs`

**Acceptance:** Agent opens N sources, reads each, compares — domain-agnostic.

---

#### P1-6: Hardware profile + reality-grounded recommendations (class F)

**What:**
- `src/aradhya/utils/hardware_profile.py` — CPU model, GPU, VRAM via WMI/DXGI/nvidia-smi
- Wire into `topology.detect_local_node` (replace GPU `"unknown"`)
- `model_setup.py` — map profile → feasible local models / cloud suggestion **logic**

**Acceptance:** "What can I run on this machine?" answered from detected hardware for **any**
technical learning task (LLM, video editing, local AI, etc.).

---

#### P1-7: Mentor mode (class C — prompt + state, not vertical app)

**What:**
- `AssistantState` fields: `mentor_mode: do | teach`, optional `skill_level`
- System prompt variants in `_build_agent_system_prompt`
- Pedagogy instructions in `rules.md` template + `guided-workflows` skill

**Acceptance:** Same task (e.g. learn a concept) behaves differently in do vs teach mode.

---

#### P1-8: Desktop interaction tools (class B, C, F — later within P1)

**What:** `desktop_tools.py` — mouse/keyboard or UI Automation, overlay for highlights

**Acceptance:** Click-by-click guidance for **any** desktop app, not hardcoded flows.

---

### P2 — Integration polish

| ID | Task | Classes |
|----|------|---------|
| P2-1 | Unify floating icon + daemon + voice | G |
| P2-2 | TTS default on when voice session active | G |
| P2-3 | Raise `max_iterations` or dynamic budget for multi-step class D flows | D |
| P2-4 | Progress/session tracking for teaching loops | C |
| P2-5 | Proactive context (watcher, error detection) | A, C |

### P3 — Product completeness

| ID | Task |
|----|------|
| P3-1 | Production packaging (`PARASITE_OS_PROGRESS.md`) |
| P3-2 | Federation / external handoff (separate roadmap) |

---

## 8. Reference Patterns to Reuse

### 8.1 Analyze → confirm → execute (generalize Parasite GC)

```
analyze_tool(dry_run=True) → structured JSON report
→ present to user → user selects actions
→ trust_boundary.confirm() → execute(dry_run=False) → audit log → summarize
```

**Applies to:** class E (maintenance), class D (before submit), class B (destructive file ops)

### 8.2 Plan confirmation — `assistant_core.py:378-438`

### 8.3 Per-tool dangerous gate — `agent_loop.py:545+`

### 8.4 Skill authoring — general workflow skills, not domain verticals

### 8.5 Tool authoring — `@tool_definition` + register in `assistant_core`

---

## 9. Tests Coverage Gaps

| Area | Existing | Missing |
|------|----------|---------|
| Voice | pipeline, activation, transcriber | `test_wake_word.py` |
| Vision | — | `test_vision_tools.py` |
| Browser | — | `test_browser_tools.py` |
| Maintenance tools | — | `test_maintenance_tools.py` |
| Trust boundary workflow | `test_parasite_gc.py` (reference) | `test_trust_boundary_workflow.py` |
| Skills loader | `test_intent_skill_loader.py` | integration with `assistant_core` |

Run: `pytest --override-ini="addopts=" tests/unit/`

---

## 10. Roadmap Items Already Tracked (Do Not Duplicate)

From `docs/OI_ROADMAP.md`: Context Engine Phase 2, External Handoff, Debate AI, Federation.

From `docs/PARASITE_OS_PROGRESS.md`: Drive migration, packaging, watcher index.

These are **orthogonal** to mentor vision unless they directly enable a capability class.

---

## 11. Dependencies

- Vision: `mss`, `pytesseract` (optional; fallbacks exist)
- Voice: `faster_whisper` or `whisper_command`, `sounddevice`, `pyttsx3`
- Browser: Selenium + Chrome/Edge WebDriver
- Models: Ollama default; no vision API in `model_provider.py` today

---

## 12. Architecture Gap (by Capability Class)

```
CAPABILITY CLASS          PLATFORM TODAY              MISSING PLATFORM LAYER
────────────────────────────────────────────────────────────────────────────
A Perception              OCR, context engine,        Vision LLM, structured profile,
                          basic topology              screen watch, rich hardware

B Execution               files, shell, browser,      delete/move, multi-tab, desktop
                          gated tools                 input, overlay

C Teaching                generic agent + plans       mentor mode, pedagogy loop,
                                                      do/teach toggle

D Research & assist       web_search, browser_type    multi-source tabs, comparison
                                                      schema, trust-boundary engine

E Safe maintenance        ad hoc shell, Parasite GC   generalized analyze/plan/
                          (Hosts scope only)          execute tools + safe-maintenance skill

F Reality-grounded        topology partial            hardware_profile, recommendation
guidance                                              mapping, UI walkthrough tools

G Orchestration           agent loop, plan confirm    skill routing, workflow engine,
                          voice push-to-talk          wake-word fix, unified shell
```

---

## 13. Suggested Implementation Order

1. **P0** — bugs, skill wiring, docs (foundation for everything)
2. **P1-1** — trust-boundary workflow engine (unblocks D and E generically)
3. **P1-2** — maintenance analysis tools (proves E pattern on disk — one instance, not the product)
4. **P1-3 + P1-6** — perception + hardware (unblocks A and F)
5. **P1-4 + P1-5** — user context + multi-tab browser (unblocks D generically)
6. **P1-7** — mentor mode (unblocks C on existing agent)
7. **P1-8, P2** — desktop tools, polish

**Do not** prioritize a `government-jobs` or `coding-tutor` vertical before P1-1 and P1-7.

---

## 14. Files Index

```
src/aradhya/
  assistant_core.py          Orchestrator ★
  agent_loop.py              ReAct + DANGEROUS_TOOLS ★
  llm_planner.py             Intent routing (skill gap) ★
  planning_workflow.py       Multi-step plans (extend for trust boundaries)
  context_engine.py          Machine context
  topology.py                Hardware manifest (GPU unknown)
  model_provider.py          No vision yet
  model_setup.py             Static model catalog
  tools/
    vision_tools.py          screen_capture, screen_read_text
    browser_tools.py         Selenium single-tab
    web_tools.py             web_search, web_fetch
    file_tools.py            no delete/move
  voice/wake_word.py         BROKEN ★
  skills/skill_loader.py     load_skills_for_intent unwired ★
  parasite/pipeline.py       gc() pattern ★ — generalize, don't only copy for disk
core/skills/                 10 skills; screen-reader disabled
core/memory/user_context/    rules.md, notes.md — unstructured
docs/OI_VISION.md            Aligns with mentor vision
AGENTS.md                    Safety ★
```

---

## 15. Final Verdict (Machine Summary)

```json
{
  "project": "Aradhya",
  "role": "local-first Windows Operating Intelligence",
  "product_goal": "general_context_aware_desktop_mentor",
  "product_goal_not": "four_fixed_verticals_from_user_examples",
  "vision_implemented": false,
  "platform_maturity": "high",
  "product_maturity": "low",
  "capability_classes": {
    "A_perception_context": "partial",
    "B_autonomous_execution": "partial",
    "C_interactive_teaching": "missing",
    "D_research_assisted_completion": "partial",
    "E_safe_maintenance": "partial",
    "F_reality_grounded_guidance": "partial",
    "G_workflow_orchestration": "partial"
  },
  "blockers": [
    "No universal trust-boundary workflow engine",
    "No mentor mode (do vs teach) or pedagogy loop",
    "Skill system partially wired",
    "Phantom dangerous tools",
    "Broken wake-word",
    "OCR-only vision, no desktop UI control",
    "Single-tab browser, no submit/CAPTCHA policy",
    "No structured user context for assisted tasks",
    "GPU detection stub",
    "Maintenance pattern exists only for Parasite Hosts scope"
  ],
  "reuse_patterns": [
    "AgentLoop + tool registry",
    "Plan confirmation + DANGEROUS_TOOLS gates",
    "Parasite GC dry-run report schema → generalize to all class E and D checkpoints",
    "Skill framework with intent loading",
    "ContextEngine + SQLite sessions"
  ],
  "first_recommended_task": "P0 fixes then P1-1 trust_boundary workflow engine",
  "example_verticals_are": "non_normative_illustrations_only"
}
```

---

## 16. Handoff Prompt (copy to another AI)

```
Read F:/ARADHYA/docs/AI_HANDOFF_TUTOR_SPEC_AUDIT.md and AGENTS.md.

The user's examples (coding tutor, jobs, disk, LLM coach) illustrate CAPABILITY CLASSES
(§2.3), not fixed products. Build platform behaviors: universal loop (§2.2), trust-boundary
workflow (P1-1), and class-specific tools — not hardcoded vertical skills.

Implement P0 first, then P1-1 (trust-boundary workflow engine). Follow acceptance criteria
in §7. Never violate §0.4 safety constraints.
```

---

*End of handoff document. Normative product definition: §2 capability classes + §2.2 loop.
Technical audit: §3–§6. Implementation plan: §7. Examples in §2.5 are illustrative only.*
