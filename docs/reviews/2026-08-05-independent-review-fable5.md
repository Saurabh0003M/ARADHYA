# Independent review — 2026-08-05 (Claude Fable 5)

Commissioned as an adversarial second opinion against the Opus 5 strategic review of
2026-08-04 (`brain/aradhya/strategic-review-2026-08-04`). Method: 9 parallel reader
agents over the subsystems (~800k tokens of file reading), plus first-hand verification
of every load-bearing claim by the reviewing model. Verified vs inferred is marked
throughout.

## Numbers verified first-hand

| Claim | Measured | Verdict |
|---|---|---|
| 236 commits | 236 across all branches (216 on this branch, 210 on main) | ✔ (all-branch count) |
| 102 source files | 102 `.py` under `src/` | ✔ |
| 23,930 source lines | 28,216 raw (`wc -l`); 23,930 plausibly excludes blanks/comments | ✔ ~ |
| 605 tests | 605 collected (`pytest --collect-only`) | ✔ |
| 73 registered tools | **62** actually registered (`assistant_core.py:795-821`, 16 `ALL_*` lists); ~73 counts `@tool_definition` decorators incl. never-registered ones | ✘ overstated |
| 1 argparse flag | 1 `add_argument` (`main.py:1281`) | ✔ |
| `first_run` 0 times | 0 hits — **but a real interactive first-run model-setup flow exists** (`model_setup.py:196-350`, called `main.py:1143`) | string absent, capability present |
| 0 e2e tests | `tests/integration/` contains only an empty `__init__.py` | ✔ |

## The three facts that reframe everything

1. **The working voice assistant is not ARADHYA.** `lite/aradhya_lite.py` (333 lines)
   is the only end-to-end speak→act loop on this machine, and its brain is
   `ClaudeSDKClient` — the Claude Agent SDK — not the ARADHYA engine
   (`lite/aradhya_lite.py:37-42, 221-234`). It bypasses `assistant_core`, `agent_loop`,
   the confirmation gate, and the audit log entirely, with its own ad-hoc allowlist
   (`:225-227` excludes Bash "a mis-heard voice command must not run shell").
   The author's revealed preference: when he wanted JARVIS, 28k lines lost to a
   333-line wrapper around a rented frontier brain.

2. **The effectors are dead on the author's own machine.** `selenium` is imported by
   all 12 browser tools (`browser_tools.py:98`) but is declared in **no** requirements
   file and is **not installed** in `venv/` (verified: `ModuleNotFoundError`).
   `uiautomation` (all 5 desktop tools) is likewise not installed. The screen-control
   surface — the entire point of the stated goal — is 1,547 LOC (~5.5% of source) and
   currently cannot execute. 605 tests stay green because `tests/conftest.py:11-51`
   mocks `selenium`, `uiautomation`-adjacent, `sounddevice` etc. at the
   `sys.modules` level, so the suite is structurally incapable of noticing.

3. **The MCP client has never connected to anything.** Real stdio/JSON-RPC client
   (`mcp_client.py:15-76`), wired at `assistant_core.py:819`, `mcp` package IS
   importable in venv — but zero servers configured in `core/memory/profile.json` or
   `core/config/profile.json`, zero tests, 2 commits ever, last touch 2026-05-11.

## Q1 — Where Opus is wrong

- **(a) It reviewed the wrong assistant.** The strategic review never mentions
  `lite/`. Any keep/park/add list that doesn't start from "the author already
  replaced the engine with the Claude SDK" is analysis of a museum piece.
- **(b) "No first-run flow / `first_run` appears 0 times"** — the grep-for-a-name
  methodology its own verification pass warned about three times. Interactive
  onboarding exists (`model_setup.py`). The real reason the app is "big but
  unusable" is (2) above: the effectors don't run.
- **(c) "MCP client = most strategically valuable asset" is backwards.** As a
  client it feeds commodity tools to a weak local brain. The valuable direction is
  ARADHYA as an MCP **server**: expose the genuinely scarce assets (UIA desktop
  tools, policy/confinement/audit gate, user profile) to the strong rented brain
  already running in `lite/`.
- **(d) "Keep the architecture" needs an asterisk.** The gate/policy stack is
  genuinely good (verified: single registry construction `assistant_core.py:797`,
  fail-closed headless gating `agent_loop.py:753-769`). But the loop is engineered
  for models the hardware can't host: two LLM calls per turn (LLMIntentPlanner then
  AgentLoop), no streaming on any tool-bearing turn (`agent_loop.py:361-371`),
  Ollama "base"-class brains. "Slow, bulky" field reports are the predictable output.
- **(e) Subagents: right call, wrong reason.** Not a duplicate-of-Claude-Code
  problem — a physics problem. 1,398 LOC of thread-pooled parallel `AgentLoop`s
  (`agents/` + `subagent_tools.py`) multiplying a brain that doesn't fit in 15.5 GB.
- **(f) Telegram: agree** — always-deny gate hardcoded (`telegram.py:405`),
  `TelegramConfirmationGate` never instantiated in `src/`. Delete now, rebuild later
  as a phone confirm-surface when there's something to confirm remotely.

Where Opus is right (briefly): momentum numbers; architecture-moat-closed; tests are
an asset not bloat; policy layer is the crown jewel; e2e gap is the real test gap.

## Q2 — The user question

Accessibility-for-blind-users is a **different product** with harder requirements
(every output spoken-verifiable, no visual fallback ever, blind users in the loop,
AT-ecosystem integration). Building it without blind testers produces feel-good
vaporware. Saurabh is a sighted user who wants eyes-free/hands-free operation with
the option to glance.

**Third framing that fits: "an operator you brief, not an app you drive."**
Voice-first personal operator for his recurring workflows. The accessibility
substrate (UIA — "the same accessibility channel a screen reader uses",
`desktop_control.py` docstring) is the right substrate for BOTH users, so the
north star survives as direction and portfolio story; the acceptance tests are his
tasks, not a hypothetical blind user's.

## Q3 — What screen control is achievable on this hardware (2026)

Tiered targeting, in order:

1. **Browser DOM** — his listed tasks (gov portal, Google Forms, job listings) are
   ~80% browser tasks. Current state: Selenium (uninstalled), blind
   text-contains XPath, fixed `time.sleep`s, no `WebDriverWait`
   (`browser_tools.py:226,305,377,563`), and the model sees only `body.text`
   truncated to 4,000 chars (`browser_tools.py:421-422`) — it guesses selectors
   blind. Fix: attach to the real Edge/Chrome via CDP (keeps logins, evades
   webdriver detection), serialize a **form/element map** (roles, labels, ids) for
   the model, auto-wait + re-query on staleness. All CPU-trivial.
2. **UIA tree** for desktop apps — right substrate, already chosen. Needs: install
   the dep, scoped queries (full-tree walks of complex windows cost seconds in
   Python; scoped finds are tens of ms), retry/backoff (currently zero —
   single-shot lookups, `desktop_control.py:250-300`), event-driven waits, control
   cache. Works: Win32/WPF/UWP. Partial: Chromium/Electron (needs accessibility
   forced on). Never: games/custom canvas.
3. **OCR** — Windows.Media.Ocr is already implemented via PowerShell
   (`vision_tools.py:144-171`): free, ~100-300 ms, decent. Correct fallback tier.
4. **VLM** — local (Moondream-2B / Qwen2.5-VL-3B class) = 10-60 s per screen on
   this CPU/iGPU: fallback only, never a perception loop. Cloud VLM via freellmapi
   (Gemini Flash) 1-3 s for non-sensitive screens. Use VLM to *describe*, UIA/DOM
   to *act* — the current design accidentally gets this right (`describe_screen`
   returns text only, no coordinate bridge). The floating icon's "screen watch"
   stub as a continuous local loop is not viable on this hardware; park it.

Voice: solved at this hardware tier (faster-whisper base/small + Silero VAD +
openwakeword in `lite/`; Edge TTS / SAPI offline).

**Ceiling, honestly:** rehearsed flows on known sites/apps with recipes + retries +
confirm gates: 90-95% task success. Novel arbitrary GUIs, no rehearsal: frontier
agents sat ~40-70% on OSWorld/WebArena-class benchmarks as of early 2026; a local
brain will not beat that, a rented brain over CDP approaches it for browser tasks.
Design for rehearsed reliability, not open-world generality. (Confidence: high on
mechanisms, medium on the benchmark numbers — knowledge cutoff Jan 2026.)

## Q4 — Roadmap (each stage shippable, hardware-fits, verifiable)

- **Stage 0 — Repair the effectors, collapse the split brain (≈1 week).**
  Declare+install selenium/uiautomation; make `lite/` the front door; expose
  ARADHYA's desktop/browser/profile tools to the lite Claude-SDK session (MCP
  server or SDK custom tools) **through the existing ToolRegistry policy gate**.
  Done when: "open X / click Y / read this window" work by voice 10/10 on 3 apps.
- **Stage 1 — One browser task bulletproof.** Google Form fill by voice from
  `user_profile.py` data; review read back; submit only on confirm. Done when: 10
  consecutive successes on 3 unseen forms, submit always human-confirmed.
- **Stage 2 — Daily driver for files and drafts.** Voice search over own folders
  (indexer exists); dictated client-reply drafts to clipboard — never auto-send.
  Done when: 7 consecutive days of real use, audit log as proof.
- **Stage 3 — Recipes for portals.** Recipe format (steps: intent + selector +
  fallback + confirm points) executed by the trust-boundary engine (its
  ANALYZE→PLAN→SELECT→DRY_RUN→CONFIRM→EXECUTE shape is exactly this,
  `trust_boundary.py:240-427` — currently dead code); a recorder that turns one
  human demonstration into a draft recipe; 5 recurring portals, incl. one
  government flow with CAPTCHA/OTP/final-submit human-only. Ship a default
  `permissions.json` (engine exists, ships empty) with origin rules for gov/bank
  domains. Done when: one real government task end-to-end with him touching only
  CAPTCHA/OTP/submit.
- **Stage 4 — Desktop reach + recovery.** UIA retries/waits/cache; benchmark of 20
  scripted desktop tasks across 3 apps; OCR fallback. Done when: ≥18/20 twice in a
  row from cold start.
- **Stage 5 — Hands-off sessions.** Chained tasks via daemon scheduler; action
  receipts ("what I did while you were away"); phone as remote confirm surface
  (rebuild Telegram small, wired to a real interactive gate). Done when: he leaves
  the laptop, assigns 3 tasks by phone, returns to receipts.

## Q5 — Delete outright (~4,600 LOC ≈ 18% of source, plus ~2.6 GB)

| Target | Size | Evidence |
|---|---|---|
| `src/aradhya/parasite/` + `/parasite` commands + 4 test files | 2,146 LOC + tests | copies host source (`pipeline.py:601,609`) against own research; rename never merged; classifier friction; zero delivered value |
| `src/aradhya/agents/` + `tools/subagent_tools.py` + 2 test files | 1,398 LOC + ~518 test LOC | parallel local-LLM loops on 15.5 GB/no-dGPU is capability theater |
| `channels/telegram.py` + `TelegramConfirmationGate` | 513 + ~70 LOC | gate hardcoded always-deny (`telegram.py:405`); interactive gate never instantiated |
| `federation/` + `/topology`, `/federation`, `/model workers` | 165 LOC + command surface | no second machine with meaningful compute exists |
| `transcript.py`, `workspace_manager.py` (+test), empty `smart_router/`, `voice/wake_word.py` | ~350 LOC | orphans (zero src importers); wake_word is whisper-substring matching superseded by lite's openwakeword |
| `.tmp/` (1.0 GB); one of `lite/.venv`/`lite/wakeword_env` (~1.7 GB); move 16.5 GB wakeword training `.npy` off-tree after training | disk | measured |
| `Hosts/` (1.6 GB) | archive off-tree, don't destroy — possibly last local copies; remotes listed in brain | |

Keep: policy/gate/audit stack (1,444 LOC — the crown jewels), `trust_boundary.py`
(reborn as the recipe engine), tests (minus deleted subsystems), desktop/browser/
vision tools (repair them), indexer, profile, `lite/`.

## Q6 — Government portals, clients, jobs: design constraints

- **Human-only, by policy not habit:** CAPTCHA, OTP, password entry, legal
  attestations ("I certify…"), final submit. Encode as permission rules (engine
  ships empty today) so the model *can't* be talked into them.
- **Credentials never enter ARADHYA.** Typed by the human, session-only. Note:
  `core/memory/profile.json` and `core/config/profile.json` are git-tracked
  personal data today — move to `*.local.json`, scrub history if sensitive.
- **Prerequisite hygiene:** STATE.md carries an unconfirmed credential rotation
  after the 2026-07-05 infostealer plus 3 API keys in plaintext transcripts. An
  assistant holding gov-portal sessions on a machine with unrotated creds is a
  liability multiplier. Rotate first.
- **Browser profile scoping:** driving the real logged-in Chrome profile
  (`browser_tools.py:65-75,107-110`) is power and risk; use a dedicated automation
  profile with explicit login handoff except where logged-in state is the point;
  deny `browser_execute_js` on gov/bank origins via permission rules.
- **Authorship & consent:** drafts are labeled drafts; the human sends client
  messages and job applications. Most portals' ToS prohibit automated access —
  semi-automation where the human triggers each legally significant step is
  defensible; full autonomy is not. Mass auto-applying also gets accounts banned
  and degrades his own signal.
- **Auditability:** audit.jsonl exists — add per-session action receipts and
  per-field provenance (which value came from profile vs typed) for anything
  submitted anywhere. DPDP Act 2023 applies to client data; don't scrape leads
  into dossiers.

## Q7 — The 10-year picture, split honestly

**Engineering (persistence wins):** hands-free operation of his known workflows;
recipe library compounding; personal memory/context; wake word; remote confirm;
*supervised* self-extension — the assistant drafts new recipes from watching him
demonstrate once, he reviews and approves. That is the honest version of "builds
its own automations," and it is reachable.

**Category errors (no amount of work reaches them):**
1. *Local frontier-parity brain.* The consumer/datacenter gap is widening. The
   JARVIS cortex stays rented for the foreseeable future; what he owns is the
   harness, effectors, policy, data, and trust. (His own lite/ already concedes
   this.) Local models remain the privacy/offline tier, not the brain.
2. *Unsupervised self-improving automation.* A security anti-goal — the
   confirmation-gate philosophy must scale UP with autonomy (scoped grants,
   receipts), not dissolve. JARVIS-without-asking isn't blocked by engineering;
   the trust boundary IS the product.
3. *Outcompeting the OS vendor on its own OS.* Windows will keep absorbing
   assistant capability. The defensible asset is personal: nobody ships HIS
   profile, recipes, and trust policies. ARADHYA's durable identity is the
   **sovereignty layer** — the part of the stack he owns no matter which model or
   OS assistant wins.

**Verdict: narrow substantially.** Keep ~30% of the code (policy stack, effectors,
profile, indexer, trust-boundary-as-recipe-engine, tests), delete ~18%, demote the
rest from "product" to "parts bin." The product is the lite loop + ARADHYA's
effectors behind ARADHYA's gate — an operator you brief, with hands (UIA/DOM),
a spine (policy), and a rented cortex.

## Confidence

- Code facts: high (9 readers + first-hand spot-checks; corrections applied where a
  reader erred, e.g. `mcp` IS importable in venv).
- Hardware/latency numbers for VLM/OCR/UIA: medium-high (knowledge, not measured here).
- Benchmark figures and competitive landscape: medium — knowledge cutoff Jan 2026,
  external landscape unverified; same caveat as Opus, same recommended external
  research pass before betting the roadmap on any competitive claim.
