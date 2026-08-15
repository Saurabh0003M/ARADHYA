# ARADHYA — decision memo, 2026-08-07

Closes the three-round debate ([[strategic-review-2026-08-04]] → [[counter-review-2026-08-05]] →
[[debate-response-2026-08-05]]) against the 12 external deep-research reports in
`docs/research/fable research/md/`. Every code claim below was re-verified against the repo today.
Agreed ground (Stage 0 intent, tests, policy stack, human-only lines, credential rotation) is not
re-opened.

---

## The two sentences

**Front-end:** ARADHYA ships as an **MCP server** exposing its UIA/browser effectors behind the
existing `ToolRegistry` policy gate, and the voice shell is one thin client of that server — not a
second product.

**Framing:** *"An operator you brief" (who it's for) + "operable with the monitor off" (when it's
done)* — with accessibility demoted to a **build constraint only** and struck from every external
description of the project.

---

## 1. Front-end: server first, shell second — but they are the same product

The round-2 dilemma ("is the human talking to ARADHYA, or is a stronger agent talking to ARADHYA?")
dissolves once the tools sit behind MCP: the voice shell and any rented harness become
interchangeable clients of one server.

- **The standalone slot is genuinely empty.** Both models, independently and with sources:
  P1-gemini §*Feasibility Analysis* — "The definitive answer is no… this specific technological
  intersection is entirely unoccupied" (voice + general Windows + CPU-only + free);
  P1-chatgpt §*Gaps and Unmet Needs* — "no shipped product today offers all of (voice input + full
  desktop control + CPU-only + free)". **Strong evidence.**
- **But the scarce asset is the substrate, not the shell.** P1-gemini §*Unshipped Market Gaps* names
  its #1 opportunity as "**The UIAutomation (Accessibility Tree) Agent**" — an agent that bypasses
  pixel vision and reads the UIA tree — and #2 as a voice→MCP tool-call router at the edge. That is
  a description of ARADHYA's `desktop_control.py` + policy gate, not of a CLI.
- **A rented brain is cheap and reliable enough to be the reasoner (§2), but cannot be the voice
  front-end today.** P1-gemini §*Input Modalities and Pricing*: Anthropic "explicitly disabled
  Claude's native Voice Mode within both the Cowork and Claude Code desktop environments" — users
  bridge voice via third-party dictation. Copilot's voice path is cloud-gated on this hardware
  (§6). So the voice leg must stay ARADHYA's own; the reasoning leg is rented.

**Ships first:** the MCP server + repaired effectors (Stage 0–1). **Deferred, not funded:** first-run
flow, `/tools` discovery, CLI polish — the exact work round 2 flagged as wasted if a rented harness
is the front-end. Order justified because the substrate is the scarce asset (P1-gemini gap #1) while
brains are commodity and swappable (P4, §2 below).

> **Reverses this if:** measured round-trip for a rehearsed voice command through an external
> harness exceeds ~2 s consistently (P4-gemini §6 sets 1.5–2.0 s TTFT as the conversational floor).
> Then the loop must be local-first and the standalone shell has to ship first.

## 2. Brain: drop the Claude Agent SDK. OpenCode over a free-tier ladder. **₹0/month.**

Both reports agree Anthropic is untenable at this volume and both recommend a provider-agnostic
open-source harness over aggregated free tiers. **Strong evidence.**

| Option | Monthly | Source |
|---|---|---|
| Claude Pro | ₹1,680 — throttled, unusable | P4-gemini §2 table |
| Claude Max 5× | ₹8,400 | P4-gemini §2 table |
| Raw API, prompt caching | ₹3,408 | P4-gemini §2 table |
| Raw API, no caching | ₹7,938 | P4-gemini §2 table |
| Claude Max 20× (what 2,000 calls/day actually needs) | ≈₹16,600 | P4-chatgpt §*Pricing and Limits* |
| **OpenCode + free tiers** | **₹0** | P4-gemini §7; P4-chatgpt §*Recommendation* |

Harness: **OpenCode**, with **Goose** as the drop-in alternative. Both reports name the same two and
disagree only on ranking (Gemini: OpenCode primary; ChatGPT: Goose primary). OpenCode wins on the
one mechanism that is load-bearing here and only one report documented concretely: `baseURL`
override per provider/model to a local aggregating proxy, headless `--prompt` execution, and
automatic context compaction at 95% of the window (P4-gemini §3).

Ladder: local Ollama triage → Gemini Flash free tier → Groq 70B overflow → Groq 8B volume
(P4-gemini §7).

**Two disagreements, not averaged:**

- **Cerebras.** ChatGPT: 1M free tokens/day, no card (§*Free-Tier Model Reality*). Gemini: false —
  one-time $5 credit requiring a payment method, expiring in 30 days, citing Cerebras' own
  rate-limits docs (§*Debunking the Cerebras "Permanent" Free Tier*). **Weigh Gemini** (vendor
  primary source, and it specifically identifies the aggregator claim ChatGPT repeats). **Do not
  design Cerebras into the ladder** until Saurabh confirms in the console himself.
- **Gemini free-tier RPD.** ChatGPT: 250/day (2.5 Flash). Gemini: 1,500/day (2.0 Flash). Both agree
  the cap sits well below the ~2,000 requests/day a 200-turn loop generates. **Budget to the
  pessimistic 250–1,000**, which means Groq carries more of the load than P4-gemini's ladder assumes.

*Unverified, ChatGPT-only:* "the Agent SDK spawns a new process per `query()`, ~12 s latency."
Nothing in Gemini's report corroborates it and `lite/` demonstrably runs conversationally today. The
decision turns on cost, not this number — flagged, not relied on.

> **Reverses this if:** the free tiers close (Gemini or Groq require a card / drop below ~1,000
> RPD combined). Fallback is a ₹1,700/month paid tier, not a return to Max 20×.

## 3. Framing: accessibility gets **smaller** — a build constraint, never a market

Both models reach the same verdict with independent sourcing. **Strong evidence.**

- P2-gemini §*Verdict*: the hypothesis is "**(C) a mis-specified need**… compounded heavily by the
  fact that the viable augmentation features are **(B) already being absorbed by platform
  vendors**." Its demand table rates full voice control **"Very Low"** for able-bodied blind users.
- P2-chatgpt §*Verdict*: "a blind user 'talking to Windows via ChatGPT' appears mis-specified as a
  core need… no chorus demanding a standalone voice agent UI."
- Absorption is documented on both sides: NVDA's AI Content Describer (now with a *Computer Use*
  beta), JAWS Picture Smart AI / AI Labeler / FSCompanion, Narrator + Copilot image description.
- Both warn the same failure mode: building for this community without it. P2-gemini
  §*The Overlay Backlash* (NFB ban, FTC's $1M accessiBe fine); P2-chatgpt §*Pitfalls of "Build
  Without Users"*.

So: **"operable with the monitor off" survives unchanged**, because its justification was never the
market — it is a done-condition Saurabh can test alone tonight, and it mechanically produces the
spoken confirmations and discoverable capabilities five usability reports asked for. What dies is
any *claim* that ARADHYA is for blind users, in the README, the portfolio, or a pitch.

One live niche is recorded and parked, not pursued: blind **and** motor-impaired users, for whom
Voice Access and Talon fail because their disambiguation is a *visual* numbered grid (P2-gemini
§*The Real Unmet Need*). Entry condition: a co-design partner from that group. Not before.

> **Reverses this if:** such a partner appears and wants to co-design. Then accessibility becomes a
> market and the roadmap changes.

## 4. Screen-control stack: order confirmed, three amendments

Tiering (CDP-attach + element maps > scoped UIA + retries > Windows OCR > VLM describes, never
clicks) is **confirmed by both reports**. UIA-over-vision: P3-chatgpt — agents using the native UIA
tree "far outperformed vision-only agents"; P3-gemini mistake #3 is over-relying on pure vision.
Windows-native OCR first, RapidOCR fallback, Tesseract obsolete: both, explicitly. VLM-never-clicks
is now *mandatory*, not stylistic — P3-gemini §*Local Perception* measures Qwen2.5-VL-3B at ~14
tok/s on this NPU, i.e. **18–35 seconds per full-screen perception cycle**.

**Amendments:**

1. **Selenium is out of the plan entirely.** P3-gemini's protocol table rates it "**obsolete for
   agents**"; P3-chatgpt: "few new projects start with it." Repairing 12 browser tools *on selenium*
   is repairing the wrong stack. Re-point them at CDP-attach against the real logged-in profile —
   which also serves the anti-bot guidance both reports give (persistent authenticated profiles beat
   fingerprint randomisation; P3-gemini §*Evasion and Anti-Bot Realities*).
2. **UIA `CacheRequest` scoping is day-one, not an optimisation.** Two-model agreement with a ~100×
   effect: P3-gemini §*Implementing UIA CacheRequest Batching* — full-tree walk >8 s on a
   1,000-element app vs **<50 ms** cached-and-scoped; P3-chatgpt independently — "hundreds of
   elements in ≈tens of milliseconds." This is the single highest-leverage line in P3. Keep the
   `uiautomation` binding (already declared, already what `desktop_control.py` imports); if cache
   batching proves unreachable through it, FlaUI-via-`pythonnet` is the named upgrade
   (P3-gemini §*Desktop Automation Tier*).
3. **Add a tier above the perception tiers: recorded, parameterized skills.** Both converge that
   record-once-parameterize-replay beats zero-shot — P3-chatgpt §*Demonstration-based Automation*
   (AppAgent-Claw needs "no LLM at runtime"), P3-gemini §*Parameterized Record-and-Replay*
   (CUA-Skill, 76.4% trajectory execution). This is Fable's recipe library, promoted: **for a
   rehearsed flow, don't perceive — replay.**

**Success-rate targets.** Rehearsed flows: **≥80% first try, ≥95% with one scripted retry**, on 3
named apps (P3-chatgpt ">80%"; P3-gemini "75–85%" — agreement). Novel tasks: the two disagree
sharply (ChatGPT 10–20% from Navi 19.5% / OSWorld 12%; Gemini 45–55% from CUA-Skill 50.3%). Not
averaged: **plan to ChatGPT's 10–20%**, because Gemini's figures describe frontier cloud models,
not a 3B local one. **Novel tasks never go on an acceptance path.**

> **Reverses this if:** Stage 1 measures rehearsed-flow success below 80% even after retries — then
> the deterministic-replay premise fails and the tiering needs rebuilding around verification.

## 5. Cut list — verified line counts and real coupling

Fable's numbers are accurate. What Fable got wrong is that three of these are **not** `rm -rf`:

| Path | LOC | Verified | Ruling |
|---|---|---|---|
| `src/aradhya/parasite/` | 2,146 | ✅ exact | **DELETE** — plus the `/parasite` handlers in `main.py:688–880` and renderers in `ui/cli.py`. `paths.py` reads a `parasite.toml` config name → rename to `aradhya.toml`. `workflows/trust_boundary.py:4` is a **docstring mention only** — trust_boundary is safe to keep. |
| `src/aradhya/agents/` + `tools/subagent_tools.py` | 1,130 + 268 = **1,398** | ✅ exact | **DELETE** — but `assistant_core.py:60–61` imports `AgentRegistry, load_agents, SubagentRunner` at module level. De-wire first or the core breaks on import. |
| `src/aradhya/channels/telegram.py` | 513 | ✅ exact | **DELETE** + its `main.py` / `ui/cli.py` references. |
| `src/aradhya/federation/` | 165 | ✅ exact | **DELETE** — no live importer. |
| `src/aradhya/transcript.py` | 382 | orphan ✅ | **DELETE** — no module ever imports it (the `transcript` hits in `assistant_core.py` are a local variable and a `handle_transcript` method, unrelated). |
| `src/aradhya/workspace_manager.py` | 214 | orphan ✅ | **DELETE** with `tests/unit/test_workspace_manager.py` — its only caller is its own test. |
| `src/aradhya/smart_router/` | **0** | already empty | **DELETE the stale directory** — only `__pycache__` remains; the .py files are already gone. The cut-list entry was stale. |
| `src/aradhya/voice/wake_word.py` | 109 | ❌ **not an orphan** | **KEEP.** `main.py:74` imports `WakeWordListener` and `/wake on` wires it. It is also the entry point for "operable with the monitor off," and P6 shows a ₹0–3k far-field endpoint path (Android satellite; Waveshare ESP32-S3 ≈₹2.9k) that makes wake-word the front door, not a leftover. |

**Total removed: ~4,600 LOC**, roughly as Fable estimated, but the parasite and agents deletions each
carry a de-wiring step that must land in the same commit as the removal.

**Recorded so it is not re-litigated:** *the subagents-on-rented-brains pattern is sound.* Parallel
**local** LLM loops on 15.5 GB are theater and that is why `agents/` goes. Subagents against rented
brains are standard practice — P4-gemini §3 documents OpenCode's primary/subagent architecture with
parallel `explore`/`scout` workers as a shipped feature. When ARADHYA needs subagents again, they
come from the harness, not from `src/aradhya/agents/`.

## 6. Occupancy: nobody owns the square, but Microsoft owns the one next to it

No shipped product occupies voice + general Windows + CPU-only + free (§1). But **Microsoft Copilot
Actions** occupies three of four: voice ("Hey Copilot"), general Windows control, free with the OS.
Its limits on *this* machine, per P1-gemini §*Copilot Actions* and §*The Copilot+ NPU Barrier*:
Insider-preview-only, sandboxed into a separate "Agent User" account with file access limited to six
profile folders, documented instability (orphaned Intune profiles, blocks sleep/shutdown), and — on
a Core Ultra 5 125H at ~11.5 TOPS against a 40 TOPS bar — **local execution is disabled and it falls
back to cloud**. P1-chatgpt agrees basic Copilot is cloud-based and advanced local features need an
NPU.

**How stages 0–5 change:**

- **Stage 5 (hands-off sessions) is deprioritized.** That is the square Microsoft reaches first and
  will fund indefinitely. Do not race it.
- **Stages 0–3 are unaffected and get *more* valuable.** Copilot's file access is confined to six
  user-profile folders and its reasoning is cloud-only here; portal recipes on a local policy gate
  with a persistent authenticated profile is the thing it structurally cannot do.
- **One concrete opportunity, and it validates §1.** Copilot Actions "can only interact with Model
  Context Protocol (MCP) servers registered in the Windows On-Device Registry" (P1-gemini
  §*Copilot Actions and the Agent Workspace Sandbox*). An ARADHYA MCP server registered in the ODR
  is a distribution channel into Microsoft's own shell. Server-first buys optionality that
  standalone-first does not.

> **Reverses §1 and §6 if:** Microsoft ships Copilot Actions to general availability *with* a
> working voice path on non-Copilot+ hardware. The remaining defensible ground would then be the
> policy gate and the recipe library, not desktop control.

---

## Stage 0 — week one, amended

Agreed baseline, with the selenium change from §4 and the dependency reality from the repo:

1. **Declare and install the effectors — but not selenium.** `uiautomation>=2.0.18` *is* declared
   (`requirements-windows.txt:5`) and simply is not installed — install it. **Selenium is declared
   nowhere and stays that way**; the 12 tools in `tools/browser_tools.py` get re-pointed at a
   CDP-attach driver against the real profile (§4, amendment 1). Scope for week one: the driver plus
   *one* browser tool, not all twelve.
2. **Stop `tests/conftest.py` hiding missing dependencies at `sys.modules` level.** Confirmed:
   `conftest.py:11–41` installs `MagicMock()` for `loguru`, `rich.*`, `requests`, `mcp.*` and the
   effectors. Replace the effector mocks with a real import check that **skips and reports**, so the
   suite can never again be green while the product cannot act.
3. **Wire the working voice loop to ARADHYA's tools through the `ToolRegistry` policy gate.**
   Verified present and correct: `tools/tool_registry.py:54` takes a `ToolRuntimePolicy`, `:85–97`
   checks it and propagates `requires_confirmation`. Expose the registry over MCP (§1) and point the
   `lite/` loop at it. This is where the brain swap (§2) lands too — retarget `lite/` off
   `ClaudeSDKClient`.
4. **Acceptance, unchanged:** *"open X / click Y / read this window"* by voice, **10/10 on 3 apps**,
   with the monitor off. Consistent with the ≥80%-first-try target in §4; 10/10 on rehearsed flows on
   known apps is the right week-one bar.

**Do not** start the cut list until Stage 0 passes. Deleting 4,600 lines while the product cannot
act produces a smaller product that still cannot act.

---

## Reversal conditions, collected

| Decision | Single piece of evidence that reverses it |
|---|---|
| MCP server first | Rehearsed voice command round-trip through an external harness consistently >2 s |
| Framing unchanged | A blind + motor-impaired co-design partner willing to work with him |
| Accessibility as constraint only | Same as above — it is the only thing that makes it a market |
| OpenCode + free tiers, ₹0 | Gemini or Groq free tiers requiring a card or dropping below ~1,000 RPD combined |
| Tiered screen stack | Stage 1 measures rehearsed-flow success <80% after retries |
| Selenium out | A CDP-attach driver failing on a target that selenium handles |
| Cut list | A caller appearing for `transcript.py` or `workspace_manager.py` — neither has one today |
| Stage 5 deprioritized | Copilot Actions reaching GA with voice working on non-Copilot+ hardware |

*Standing, unchanged from the debate: rotate the infostealer-exposed credentials and move
`profile.json` to `*.local.json` before any portal session. Human-only lines (CAPTCHA, OTP,
passwords, attestations, final submit) are confirmed by P5-chatgpt §NEVER as legal exposure under
IT Act §43/§66, not merely as policy.*

---

## Addendum — Fable 5 review of the memo (2026-08-07)

Independently verified before endorsing: `main.py:74` does import `WakeWordListener` and
`/wake-word on` instantiates it (`main.py:404-409`, command table `:949-950`) — the memo's
correction of my cut list is right, and the "orphan" label was my error (sixth
confident-inference error of the arc; I endorsed a reader's hedged inference unchecked).
`assistant_core.py:60-61` module-level agent imports also confirmed — the de-wire-in-same-commit
warning is real.

**Ruling on the deferred question: the selenium amendment STANDS.** Three reasons:
1. CDP-attach + element maps was already the counter-review's browser-tier fix before the
   reports existed; P3×2 confirmed it rather than introduced it.
2. "Repairing" the selenium tools is a false economy — installing the package fixes the
   ImportError but leaves blind text-XPath, fixed sleeps, and no element map. The reliability
   rewrite was coming either way; doing it once on CDP is cheaper than twice.
3. Risk is contained: week-one scope is driver + one tool, and the reversal condition (CDP
   failing where selenium succeeds) is concrete and cheap to observe.

**Two execution caveats, binding on Stage 0:**

1. **Keep the browser tool NAMES and `requires_confirmation` flags; swap only the backend.**
   The safety architecture is keyed on tool names: the approved-rules allowlist persists per
   (tool, args), audit.jsonl records by name, `DANGEROUS_TOOLS` lists `browser_click`/`browser_type`/
   `browser_execute_js`, and the test suite references these names. Re-point `browser_open`,
   `browser_read`, `browser_click`… onto the CDP driver; do not grow a fresh tool surface or the
   gating semantics silently orphan. (Driver suggestion, mine not the reports': Playwright
   `connect_over_cdp` against the real Edge/Chrome started with `--remote-debugging-port` — a
   mature API over the raw socket; drop to `pychrome` only if Playwright's install weight offends.)

2. **Sequence the brain swap AFTER MCP acceptance, inside week one.** Stage 0 as written lands
   two moving parts together (ToolRegistry-over-MCP + retargeting `lite/` off `ClaudeSDKClient`).
   If 10/10 fails you cannot tell whether tools or brain failed. Order: (a) wire the MCP server,
   keep the known-good Claude SDK brain, pass 10/10; (b) swap to OpenCode and re-run the same 10
   commands. The acceptance list doubles as the permanent brain-swap regression harness at zero
   extra cost.

Minor note, no ruling change: keeping `voice/wake_word.py` keeps the *tool*, not the
implementation — its whisper-substring detection is superseded the moment a P6 endpoint or
lite's openwakeword becomes the audio front door. Revisit at Stage 2, not now.
