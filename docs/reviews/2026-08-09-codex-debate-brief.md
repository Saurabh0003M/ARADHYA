# Debate brief for Codex — 2026-08-09

You are joining a design argument that has run three rounds between three Claude
models (Opus 5 → Fable 5 → Opus 5) plus 12 external deep-research reports. You are
the first non-Anthropic voice in it. **That is the entire reason you are here.**

Three models from one family agreeing with each other is not corroboration — it is
possibly correlated error. Your job is to find the place where all three of us are
wrong in the same direction, not to referee who won.

---

## Read in this order (stop when you have enough; do not read all 12 reports)

**Tier 1 — required (~30 min):**
1. `C:\Users\saura\OneDrive\Documents\Obsidian Vault\STATE.md` — the `aradhya` block only.
2. `docs/reviews/2026-08-07-decision-memo.md` — the ruling that closed the debate,
   with a Fable addendum at the end.
3. The brain note `aradhya/Guide-mode proposal — point, don't click (2026-08-09).md`
   — **the live, unconfirmed question. This is the main event.**

**Tier 2 — read if you dispute something in Tier 1:**
4. `docs/reviews/2026-08-05-independent-review-fable5.md` — the counter-review that
   forced the debate (code claims with file:line citations).
5. `docs/reviews/2026-08-07-stage0-measurements.md` — real numbers taken on this
   machine (CDP timings, UIA timings, the constraints the research missed).
6. `aradhya/debate-response-2026-08-05.md` (brain) — where Opus conceded.

**Tier 3 — only if a specific claim turns on it:**
7. `docs/research/fable research/md/` — 12 reports, `P1`–`P6` × ChatGPT and Gemini.
   `README.md` there maps prompt number → topic. Gemini's carry live hyperlinks;
   ChatGPT's carry unresolvable session markers, so spot-verify ChatGPT-only claims.

Project rules are in `AGENTS.md` + `CLAUDE.md` (Windows shell traps, test commands,
never `2>&1` on native commands). The venv is `./venv`.

---

## SETTLED — do not re-litigate unless you have new evidence

- Architecture is not a differentiator; five systems converged on the same primitives.
- The policy/confirmation/audit stack is the best code in the repo. Keep it.
- Accessibility is a **build constraint** ("operable with the monitor off"), not a
  market. Both P2 reports independently called the blind-user market mis-specified
  *and* vendor-absorbed.
- Brain is rented, not local: drop the Claude Agent SDK for an open-source harness
  over free tiers. A local frontier-parity model on 15.5 GB CPU-only is a category error.
- Cut list (~4,600 LOC: `parasite/`, `agents/`+`subagent_tools`, `telegram`,
  `federation`, orphans) — decided, **not yet executed**, and blocked until Stage 0 passes.
- Human-only lines: CAPTCHA, OTP, passwords, attestations, final submit. P5 found
  real IT-Act §43/§66 exposure, not merely policy.

## Verified ground truth (checked in code this week — trust but re-verify if it matters)

- Stage 0 items 1–5 are done on `feat/stage0-effectors-mcp`, not pushed. 690 tests.
- `tests/integration/` went from one empty `__init__.py` to 3 live test files
  (real Edge over CDP, real UIA, real MCP pipe). The 0-e2e gap is closed.
- Browser tools kept all 12 names + `requires_confirmation` flags; only the backend
  was swapped to CDP. `browser_read` now returns a real element map.
- MCP server exposes 62 tools and **fails closed**: a confirmation-gated tool called
  over MCP with no gate configured is denied (`mcp_server.py:354-374`).
- The working voice loop is `lite/aradhya_lite.py` (333 lines) — it currently
  bypasses the engine's gate entirely except through the new MCP path.

---

## OPEN — attack these

### A. Guide-mode as Stage 1 (**the main question**)

Saurabh's own idea: ARADHYA does not click. It **shows a dot** on the screen where
the human should click next, and the human clicks. "Trading site, user doesn't know
how to withdraw → dot on the profile icon, then transactions, then wallet." Also a
learning tool: guided use teaches faster than a tutorial.

Fable endorsed it as a better Stage 1 than the memo's "fill a Google Form", on four
claims. **Attack all four:**

1. *It deletes the hardest blocker.* The gate problem, the legal exposure, and
   page-change recovery vanish because the human performs every action.
2. *~90% already exists.* UIA gives bounding rects; the CDP element map gives
   coordinates; `ui/floating_icon.py` proves a transparent always-on-top Tkinter
   overlay works here. Only the overlay renderer is new.
3. *Pointing is control's acceptance test.* If the dot lands correctly ~95% of the
   time, control is "click where the dot is." If not, control would have clicked the
   wrong thing silently.
4. *Uncontested.* All four AI competitors take the task away from the user.

**Two weaknesses Fable is flagging in its own position — start here:**

- **Claim 4 is too strong.** Digital-adoption platforms (WalkMe, Pendo, Whatfix,
  Userpilot) have done "highlight the next click" for a decade. The honest
  difference is that theirs are *pre-authored per app by a vendor*, web-only, and
  enterprise-priced, whereas this is *generated live* from the accessibility tree
  for any app including desktop, for one person. Is that difference real enough to
  matter, or is it a worse version of a solved problem? Check whether any DAP has
  gone LLM-generated + desktop since early 2026.
- **It may contradict the memo's own front-end ruling.** The memo said MCP-server
  first, voice shell deferred, "first-run flow / CLI polish: deferred, not funded."
  But guide-mode *needs* ARADHYA's own always-on-top overlay window and its own
  voice — that is a standalone product surface. Either the server-first ruling
  needs amending, or guide-mode is not Stage 1. **Fable did not resolve this.
  Resolve it.**

Also worth attacking: does guide-mode actually serve the stated goal? Saurabh's goal
is *"I want to stop touching my laptop."* Guide-mode makes him touch it **more**.
Fable called that an acceptable ladder rung ("ARADHYA earns the right to click by
first proving it knows where to point"). Is that rationalisation?

### B. The spoken-confirmation problem (unsolved, blocks Stage 3)

A stdio MCP server's stdin **is** the protocol stream, so there is no interactive
prompt available. Today the only options are deny-everything or
`ARADHYA_MCP_GATE=unlocked` (approves everything for the process lifetime).
"Monitor off" and "the human confirms" only coexist if the confirmation is audible.
Fable's ruling: unlocked is fine for acceptance and local file work, **never** for
portal work. Design the third option, or argue the constraint is wrong.

### C. A performance diagnosis to verify (falsifiable — check it)

Saurabh measured: same model, same time — standalone Ollama 2 min, ARADHYA 9 min.
Fable's explanation, unverified by anyone else:
1. Two LLM calls per turn (`LLMIntentPlanner` classification, then `AgentLoop`).
2. 62 tool schemas + ~8000 chars of context on both calls.
3. No `keep_alive` in the Ollama payload (`model_provider.py:321-333`), so the
   9.6 GB model is evicted and reloaded from disk between calls.
4. Both processes competing for one Ollama server in 15.5 GB.
5. No streaming on any tool-bearing turn (`agent_loop.py:361-371`).
Proposed fix: switch to `llama3.2:3b`, set `keep_alive`, cap `num_ctx`, kill the
double call, stream tool turns. **Is this right? Is the ordering right?**

### D. Sequencing: dogfood before acceptance?

The memo's next step is two acceptance runs. Fable put a hands-on dogfood pass first
(`docs/reviews/2026-08-09-dogfood-session-guide.md`), arguing acceptance answers "do
the ten commands pass" while dogfooding answers "is it usable" — the question five
usability reports have asked since April and no human has ever answered. Agree?

---

## Rules of engagement

1. **Verify before you rule.** This arc has produced **six** confident-inference
   errors — all the same shape: an agent read a code path, or grepped for a name,
   and inferred a working system. Path traversal was a false positive *twice*.
   `mcp_manager` was called the most valuable asset while having zero configured
   servers. `wake_word.py` was called an orphan while `main.py:74` imports it. If
   you assert something about this code, open the file.
2. **Disagreement is the deliverable.** If you mostly agree, this was a waste of a
   turn. Find the thing three Claudes missed *because* we are three Claudes.
3. **Respect the hardware ceiling**: Intel Ultra 5 125H, no dGPU, 15.5 GB RAM,
   Windows 11, near-zero budget. Anything needing a dGPU or 32 GB is a non-starter.
4. **Do not edit code or start the cut list.** This is a design turn. Read, verify,
   argue. If you want a change made, specify it precisely enough to be executed.
5. **Cite `file:line`** for every code claim, and mark clearly what you verified vs
   what you inferred.

## Deliverable

Write your response to `docs/reviews/2026-08-09-codex-response.md` (so it survives
the session), and summarise in chat. Structure:

- **Where all three Claudes are wrong** — the headline. Be specific.
- **Ruling on A** (guide-mode as Stage 1): yes / no / yes-with-amendments, and
  resolve the server-vs-standalone contradiction either way.
- **B**: a concrete design for confirmation that is audible, or the argument that
  the framing is wrong.
- **C**: verified or corrected, with the fix ordered by measured impact.
- **D**: one line.
- **What you would build next week**, if it differs from Stage 0 → guide-mode.

Then update `STATE.md`'s `aradhya` block (`last:` must name you, `codex`) and write
your durable conclusions to the brain as a note in the `aradhya/` folder. If the
`basic-memory` MCP tools are unavailable to you, write the markdown file directly to
`C:\Users\saura\OneDrive\Documents\Obsidian Vault\aradhya\`.
