# Deep-research prompt pack — 2026-08-07

Six self-contained prompts for external deep-research models, plus the handover
prompt for Opus 5. Purpose: resolve the disagreements between
`brain/aradhya/strategic-review-2026-08-04` (Opus 5) and
`brain/aradhya/counter-review-2026-08-05` (Fable 5) with post-cutoff evidence.

Run P1–P5 for the ARADHYA decision. P6 is the room-project voice endpoint
(optional, separate budget). One prompt per research session; save each report as
a file; hand all reports + the handover prompt to Opus 5.

---

## P1 — Competitive landscape: voice-operated Windows control

```
Research task: map every SHIPPED product (not demo, not announcement) that lets a
non-developer operate a Windows PC by voice or natural language, as of August 2026.

My context: I am a solo developer building a local-first, voice-operated assistant
for Windows 11 — I speak, it operates the screen (web forms, desktop apps) with
confirmation gates before risky actions. Hardware: CPU-only laptop (Intel Core
Ultra 5 125H, integrated Arc graphics, 15.5 GB RAM, no discrete GPU). I need to
know whether this space is already occupied before committing a year to it.

Cover, with current shipped status:
1. Microsoft: Copilot Voice and Copilot Vision on Windows 11, Recall, agentic
   features in Windows, and whether the UFO/LAM research line (Windows agents via
   UI Automation) has been productized. What requires Copilot+ NPU hardware vs
   runs on any PC?
2. OpenAI: Operator / ChatGPT agent mode — does it operate the user's LOCAL
   Windows applications, or only a cloud-hosted browser? Price tier required.
3. Anthropic: computer use — any consumer-facing surface, or still API/dev-only?
4. Google: Project Mariner, Gemini-in-Chrome on Windows — what ships, what it
   controls, price.
5. Startups and open source: browser-use, Skyvern, Open Interpreter, UI-TARS /
   UI-TARS-desktop, Agent S, OmniParser-based projects, Warmwind, and anything
   called "Fable OS" (verify whether a product by that name exists at all).
   Include anything comparable you find that I have not named.

For each entry: what it controls (browser-only vs full desktop), input modality
(is voice actually supported?), local vs cloud execution, minimum hardware, price,
maturity/user base, and reported reliability on real tasks (success rates, common
failure stories from reviews and user forums).

Then answer directly: does ANY shipped product combine (a) voice input, (b)
general Windows desktop control beyond the browser, (c) acceptable operation on
CPU-only consumer hardware, and (d) free or near-free cost? If none, list the 5-10
closest gaps nobody ships.

Format: comparison table + gap list. Every claim dated and cited; prefer sources
from March 2026 onward. Where you cannot verify, write "unknown" — do not pad.
```

---

## P2 — Accessibility reality check

```
Research task: test the hypothesis that "a blind or speech-only person operating a
Windows computer entirely by voice through an AI agent" is a real, unmet,
welcomed need — as of August 2026.

Background: a reviewer proposed positioning my Windows voice-assistant project as
an accessibility layer for blind users. Before betting the roadmap on that, I need
evidence about actual demand from the community, not the intuition of sighted
developers.

1. What AI capabilities have shipped inside screen readers: NVDA (including its
   add-on ecosystem — AI image description, OCR, LLM add-ons), JAWS AI features,
   Windows Narrator + Copilot integration. What do users say about them?
2. What do blind and low-vision users say they actually need from AI? Sources:
   NVDA users mailing list, r/Blind, Blind Android/Windows user forums, podcast
   and YouTube reviews by blind tech reviewers, and academic work (ASSETS/CHI
   2025-2026 papers on blind users and LLM agents). Distinguish: (a) richer
   screen-reader augmentation (descriptions, navigation, OCR), (b) task
   delegation ("do it for me"), (c) full voice-driven computer control. Which do
   they rank highest and why? Note the known tension: many blind users are FAST
   with keyboard + screen reader and distrust agents that take control away.
3. Existing voice-control accessibility tools: Windows Voice Access, Dragon,
   Talon, Numen — capabilities, gaps, user complaints.
4. Failure patterns: documented cases of accessibility tech built WITHOUT disabled
   users that flopped; what accessibility communities advise outside solo
   developers to do and not do.
5. Your verdict, argued from the evidence: is "blind user operates Windows by
   voice via an LLM agent" (a) an unmet need with real demand, (b) already being
   absorbed by platform vendors, or (c) a mis-specified need where the real gap
   is something else? Quote community voices directly where possible.

All claims cited and dated; prefer 2025-2026 sources. No padding.
```

---

## P3 — Technical state of the art: reliable UI automation on CPU-only Windows

```
Research task: the current (August 2026) best-practice stack for an LLM agent that
reliably operates Windows 11 — clicking the right element, filling forms,
recovering when a page changes — on CPU-only hardware.

My hardware: Intel Core Ultra 5 125H (integrated Arc iGPU + ~11 TOPS NPU),
15.5 GB RAM, no discrete GPU. My stack today: Python; Selenium (considering CDP or
Playwright); Windows UI Automation via the `uiautomation` package; Windows.Media.Ocr;
optional local VLM via Ollama/OpenVINO; cloud LLMs through an OpenAI-compatible
proxy over free provider tiers. Target tasks: web form filling (including Indian
government portals), operating desktop apps, always with human confirmation on
risky steps.

1. Browser driving in 2026: CDP-attach to the user's real Chrome/Edge vs
   Playwright vs Selenium — anti-bot detection reality, reuse of logged-in
   profiles, and which DOM/accessibility-tree serialization formats LLMs handle
   best (element maps, set-of-marks, ARIA snapshots). Self-healing selector
   techniques (re-query by role/label/neighboring text) and auto-wait patterns.
   Name concrete libraries with maturity assessment.
2. Windows UI Automation at scale: real latency numbers for full-tree walks vs
   scoped queries; UIA CacheRequest batching; event-driven waits vs polling;
   lessons from Microsoft's UFO papers and WindowsAgentArena; python
   `uiautomation` vs pywinauto vs FlaUI — which is fastest/most robust in 2026.
3. Local perception on my hardware class: OmniParser v2 CPU/iGPU
   seconds-per-frame; Qwen2.5-VL-3B / Moondream via OpenVINO on Arc iGPU or
   Meteor Lake NPU — tokens/sec and seconds-per-screenshot; Windows.Media.Ocr vs
   RapidOCR vs Tesseract on UI screenshots (accuracy and speed).
4. Benchmarks: current state-of-the-art success rates on OSWorld,
   WindowsAgentArena, WebArena/WebVoyager — and what the top methods do
   differently (perception format, retries, memory, verification steps).
5. Demonstration recording: frameworks that record a human performing a task once
   (DOM events or UIA events) and generalize it into a replayable, parameterized
   automation with LLM fallback — what exists, what's abandoned, what works.

Deliverable: a recommended tiered stack for my exact hardware (what to use for
browser, desktop, OCR, vision, in what order), expected success rates for
rehearsed flows vs novel tasks, and the top 5 mistakes teams made in this space.
Every number cited and dated; mark estimates as estimates.
```

---

## P4 — The rented cortex: which agent brain for a zero-budget builder

```
Research task: choose the "brain" for a personal voice assistant, for a student in
India with near-zero budget, as of August 2026.

Context: my working voice loop currently drives the Claude Agent SDK
(ClaudeSDKClient) as its reasoning engine, with tools exposed to it. I also run a
local OpenAI-compatible proxy that aggregates FREE provider tiers: Groq, Cerebras,
SambaNova, Google (Gemini), Mistral, Cohere, Cloudflare, OpenRouter free models,
plus local Ollama. The assistant needs multi-step TOOL CALLING (agent loops of
5-15 steps), MCP support preferred, and low latency for voice interaction.

1. Claude Agent SDK: current pricing/limits for hobby use — what does an
   always-on personal assistant doing ~200 agent turns/day cost with a Claude
   Pro subscription vs Max vs raw API? Rate limits that bite. Local custom tools
   and MCP server support maturity.
2. OpenCode (opencode.ai): what exactly is it now — provider-agnostic (can it
   point at ANY OpenAI-compatible endpoint, i.e. my proxy)? MCP client support?
   Can it run headless / be scripted / embedded as a library or server so a voice
   loop can drive it? Tool ecosystem, license, community health, release cadence.
3. Alternatives, same questions: Codex CLI (with ChatGPT plan pricing), Gemini
   CLI (free-tier limits), Open Interpreter, Goose (Block), and the option of a
   hand-rolled tool-calling loop directly against free-tier models.
4. Model reality check: which models reachable on FREE tiers are actually
   reliable at multi-step function/tool calling in August 2026 — Groq-hosted
   Llama/Qwen/Kimi variants, Cerebras-hosted models, Gemini Flash free tier,
   OpenRouter free pool. Cite any tool-calling benchmarks (BFCL or similar) and
   real rate limits (requests/min, tokens/day) that would break an interactive
   assistant.
5. Latency: which harness+model combination achieves sub-2-second first response
   for short agent turns?

Deliverable: a ranked recommendation with estimated monthly cost in ₹ for ~200
agent turns/day, and a fallback ladder (primary brain → fallback → offline).
Cited and dated; mark guesses as guesses.
```

---

## P5 — India: legal and ToS reality for an assisted-automation helper

```
Research task: the legal and terms-of-service reality, in India as of August 2026,
for a PERSONAL AI assistant that helps its owner fill forms and draft messages.

Important scope: the assistant is human-supervised with confirmation gates. It
NEVER solves CAPTCHAs, never enters passwords or OTPs, never clicks final submit —
the human does those. It autofills form fields from the owner's own profile data,
navigates pages, and drafts text. Everything runs on the owner's own computer for
the owner's own accounts.

1. Indian government portals — UIDAI/Aadhaar services, DigiLocker, Passport Seva,
   state e-district portals, government job portals (SSC, state PSCs, employment
   exchanges): published terms on automated/scripted access; any known
   enforcement actions; is assisted form-filling with a human present and
   confirming each submission treated differently from bot access anywhere?
2. Statute: IT Act 2000 (esp. s.43, s.66 unauthorized access) and DPDP Act 2023 —
   what applies when software on my own machine handles (a) my own personal data,
   (b) a freelance client's data I'm drafting replies about?
3. Job platforms — Naukri, LinkedIn, Indeed (India): ToS clauses on automation,
   detection and ban practices, documented cases of users banned for auto-apply
   tools.
4. AI-authorship disclosure: any Indian rules, advisories (MeitY etc.), or
   professional norms about disclosing AI drafting in client communication or job
   applications — or is it purely ethics today?
5. CAPTCHAs and OTPs legally: what does bypassing or automating past them expose
   a person to under Indian law, even on their own accounts?

Deliverable: three lists — CLEARLY FINE / GRAY (with named precautions) / NEVER —
every item citing a primary source (the actual ToS page, statute section, or
reported case) with dates. Flag where the law is simply silent.
```

---

## P6 — (Room project, optional) Far-field voice endpoint under ₹6,000

```
Research task: pick a far-field microphone + speaker endpoint for my room that
talks to a CUSTOM assistant hosted on my Windows laptop over LAN. Budget: ideally
under ₹3,000, hard cap ₹6,000. India availability matters. As of August 2026.

1. Amazon Echo Dot Max and the current Echo lineup: is there ANY realistic path
   to use one as a mic/speaker endpoint for a non-Alexa custom assistant — custom
   Alexa skill as a relay (what latency?), local APIs, community
   jailbreaks/firmware? Or is it a closed dead end? Current India prices.
2. Open endpoints: Home Assistant Voice Preview Edition, ESP32-S3-BOX-3, DIY
   ESP32-S3 + mic array, ReSpeaker Lite — India availability and street price,
   far-field wake-word quality in reviews, how audio streams to a custom Windows
   host (Wyoming protocol, raw streaming), speaker quality for TTS replies.
3. The ₹0 option: an old Android phone wall-mounted as a voice satellite — what
   software in 2026 does always-on wake word + audio streaming to a LAN host
   reliably (battery/heat caveats)?
4. For each option: end-to-end latency budget (wake word → laptop → spoken reply)
   and setup complexity.

Deliverable: ranked recommendation per budget tier (₹0 / ≤₹3,000 / ≤₹6,000), with
citations and dates. Say "unknown" where reviews don't exist.
```

---

## Handover prompt for Opus 5 (reports already on disk — nothing to attach)

Status 2026-08-07: Saurabh ran all six prompts through TWO models (ChatGPT and
Gemini deep research). 12 reports live as `.docx` originals under
`docs/research/fable research/{chatgpt,gemini}/` and as converted markdown under
`docs/research/fable research/md/` (P1..P6 × both models, index in its README.md).

```
You are closing the ARADHYA strategy debate at F:\ARADHYA. Read, in order:
1. brain/aradhya/strategic-review-2026-08-04 — your round-1 review.
2. brain/aradhya/counter-review-2026-08-05 — Fable 5's counter-review (full
   document: docs/reviews/2026-08-05-independent-review-fable5.md).
3. brain/aradhya/debate-response-2026-08-05 — YOUR round-2 reply: you verified
   all four of Fable's factual claims, conceded the MCP-client point, found that
   the main venv lacks the voice deps too (main ARADHYA is text-only today), and
   left ONE question explicitly unresolved.
4. The 12 external deep-research reports in
   "F:\ARADHYA\docs\research\fable research\md\" — files P1-chatgpt.md,
   P1-gemini.md … P6-chatgpt.md, P6-gemini.md (see that folder's README.md for
   the P-number → topic map). The SAME six prompts (in
   docs/reviews/2026-08-07-deep-research-prompts.md) were run through two
   independent research models; both post-date every debater's knowledge cutoff.

Ground rules:
- Treat both of your prior notes as HYPOTHESES. This arc has produced four
  confident-inference errors already (path traversal, dead API keys, floating
  shell, mcp_manager) — verify any code claim against the code before ruling.
- Two-model evidence rule: where ChatGPT and Gemini agree WITH sources, treat as
  strong evidence. Where they disagree, flag it explicitly and weigh source
  quality — do not average. Where both are silent, mark UNDECIDED — do not fill
  with priors.
- Citation formats differ: Gemini reports carry live hyperlinks; ChatGPT reports
  carry 【N†L..】 session markers — sourced but not resolvable, so spot-verify
  any ChatGPT-only claim that a decision turns on.
- The debate is converged except where listed below. Do not re-litigate agreed
  ground (Stage 0, tests, policy stack, human-only lines, credential rotation).

Rule on exactly these open points, citing report + section for each ruling:
1. THE FRONT-END QUESTION (your round-2 open item, upstream of everything):
   human→ARADHYA standalone product, or agent→ARADHYA as MCP server behind a
   rented brain? Evidence: P1 (does a shipped product already own standalone
   voice-operation of Windows?) + P4 (is a rented harness reliable and cheap
   enough to BE the front-end?). Note these can be sequenced (server first,
   standalone shell later) — if you choose a sequence, say which ships first
   and what evidence justifies the order.
2. THE BRAIN: keep the Claude Agent SDK as the voice loop's brain, or switch to
   an open-source harness (OpenCode etc.) over the freellmapi free tiers. P4.
   Include monthly ₹ estimate for ~200 agent turns/day.
3. FRAMING LABEL + CONSTRAINT: the debate converged on "an operator you brief"
   (who it's for) + "operable with the monitor off" (when it's done). P2 decides
   whether accessibility stays a build constraint only, or deserves a larger
   role (community demand exists) — or smaller (platform vendors absorbing it).
4. SCREEN-CONTROL STACK: confirm or amend the tiered plan (CDP-attach browser +
   element maps > scoped UIA + retries > Windows OCR > VLM-describes-never-
   clicks) against P3. Set expected success-rate targets for rehearsed flows.
5. CUT LIST: finalize per item — parasite/ (2,146 LOC), agents/+subagent_tools
   (1,398), telegram (513), federation (165), orphans (transcript.py,
   workspace_manager.py, wake_word.py, smart_router/). Where you keep something,
   name the stage that uses it. Record the "subagents-on-rented-brains pattern
   is sound" note so it is not re-litigated.
6. OCCUPANCY CHECK: if P1 shows a shipped competitor already owning
   "voice-operated Windows for consumers", state how stages 0-5 change.

Deliverable — a decision memo, max 2 pages:
- The front-end decision and final framing, each in one sentence.
- Kill list as concrete file paths.
- Stage 0 spec for week one (agreed baseline: declare+install
  selenium/uiautomation; stop conftest.py hiding missing deps at sys.modules
  level; wire the working voice loop to ARADHYA's tools through the existing
  ToolRegistry policy gate; acceptance = "open X / click Y / read this window"
  by voice 10/10 on 3 apps). Confirm or amend against the reports.
- Brain choice with the ₹ estimate.
- For EVERY decision: the single piece of evidence that would reverse it.

Then: write the memo to the brain as type `decision` in aradhya/, relate it with
`supersedes` to all three debate notes, and update STATE.md's aradhya block
(last:/next:/blocked:) so the next agent starts from the decision, not the debate.
```
