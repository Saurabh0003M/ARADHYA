# Aradhya OI Roadmap

For the full product thesis and category definition, see `docs/OI_VISION.md`.

## Vision

Aradhya is being built as an `OI`: `Operating Intelligence`.

- An `OS` runs the machine.
- An `OI` understands intent, gathers context, and safely gets work done on the machine.
- Models are replaceable engines, not the product itself.
- Policies, context, orchestration, and execution quality are the product.

In practical terms, Aradhya should become a local-first Windows operating
intelligence that can:

- switch between Ollama models without code changes
- understand machine context and user-specific context
- interact with shell, files, browser flows, and future on-screen controls
- use confirmation gates before risky actions
- hand off heavyweight document and conversion tasks to stronger external tools

## OI Feature Set

### Current Foundation

- Swappable local model configuration through Ollama
- Model diagnostics and startup model selection flow
- Safe planner with explicit confirmation for device-affecting tasks
- Local directory index refresh through `project_tree.txt`
- Path opening and local filesystem heuristics
- Voice inbox and transcript pipeline
- Push-to-talk live voice activation
- Optional spoken replies through a local TTS provider
- Debate AI mode toggle and planner route

### Core OI Features To Build

1. Model engine layer
- keep model selection declarative in `profile.json`
- support future Ollama engines without rewriting planner logic
- expose model capability metadata later if routing depends on model strengths

2. Context engine
- maintain filesystem context without expensive full rescans on every step
- track active app, active browser tab, and future screen snapshots
- add a user-owned personal context folder for custom commands, notes, and rules

3. Action engine
- open apps, folders, files, and URLs
- execute bounded shell actions
- operate browser workflows and form drafting
- add future UI automation for guided clicking and typed input

4. Safety and policy engine
- distinguish low-risk read/state operations from device-affecting actions
- require approval before launches, submissions, mutations, installs, deletes, or clicks
- keep audit-friendly previews of planned work

5. External handoff engine
- route large PDF summary, file conversion, OCR, and similar tasks to stronger external tools
- treat Aradhya as the orchestrator instead of rebuilding every specialist workflow locally

6. Debate AI and diagnostics
- add multi-model compare/critique/rebuttal workflows
- add health checks for context feeds, executors, browser adapters, and voice adapters

## Build Order

### Milestone 1: OI Shell

Goal: make Aradhya reliable as a local operating layer before deeper automation.

- keep Ollama model swapping as the engine contract
- keep wake, hotkey, voice inbox, spoken replies, and confirmation flow stable
- expand safe local commands such as app launch, folder open, and configurable custom commands
- add a personal context folder for user-defined commands and preferences

Why this comes first:
- it establishes the core OI loop: intent -> context -> plan -> confirm -> act

### Milestone 2: Context Engine

Goal: improve machine awareness without paying continuous full-scan cost.

- replace frequent whole-tree rebuild thinking with file watchers plus targeted rescans
- keep `project_tree.txt` as a snapshot artifact, but build it incrementally when possible
- add fast lookup structures for apps, paths, and user-defined commands
- prepare active-window and browser-context adapters

Why this matters:
- OI quality depends on context freshness, but naive full rescans become too expensive

### Milestone 3: Browser Operator

Goal: support real-world tasks such as forms, logins, and guided website flows.

- detect form-like tasks from intent
- draft fields before submit
- ask user to review before final submission
- store reusable site workflows and selectors where safe

Example:
- "Fill the Google form from my college group and let me review it first."

### Milestone 4: Screen Guidance

Goal: help users complete tasks on pages and apps that Aradhya cannot yet fully automate.

- add screenshot or screen-share based guidance mode
- describe next steps while the user clicks
- later support bounded click/typing automation after confirmation

Example:
- "I want to make my passport."
- Aradhya explains the next option, highlights the right path, and eventually can click after approval.

### Milestone 5: External Handoff

Goal: treat Aradhya as an orchestrator for specialist jobs.

- route large-document summarization to stronger external tools
- support conversion workflows like PDF to Word, color inversion, and extension conversion through handoff adapters
- bring results back into Aradhya's context and audit trail

### Milestone 6: Debate AI

Goal: turn Aradhya into a reasoning coordinator for higher-stakes decisions.

- send prompts to multiple models or providers
- run critique and rebuttal rounds
- stop when consensus or ranked recommendations are available
- keep this optional and explicitly invoked

### Milestone 7: Windows OI Experience

Goal: shift from "assistant app" to "operating intelligence layer".

- tray or floating entrypoint
- startup integration
- richer shell hooks
- future Windows-level product packaging

## Time And Space Complexity View

The main architectural rule is simple:

- avoid repeated full-machine scans
- prefer incremental updates, bounded searches, and reusable indexes

### 1. Directory Index Refresh

Current design:
- a full visible-tree refresh is roughly `O(N)` time where `N` is the number of scanned nodes
- output storage is `O(N)` space because `project_tree.txt` grows with the number of indexed nodes

Risk:
- doing this continuously across large roots will become slow and memory-heavy

Target design:
- file watchers plus targeted rescans reduce common-case refresh work toward `O(delta)`
- keep periodic full rebuilds as maintenance, not as the main loop
- cap snapshot size and keep ignored-directory rules aggressive

### 2. Path Search And Local Heuristics

Current design:
- named path search is roughly `O(N)` over visible files and folders in configured roots
- `.txt` density search is also `O(N)` over scanned directories and files
- yesterday-project and recent-game heuristics are bounded scans but still linear in explored items

Risk:
- repeated local queries on large roots will stack up latency

Target design:
- maintain a cached path catalog keyed by normalized names
- keep hot lookup paths near `O(1)` average for exact-name hits and `O(log N)` or bounded ranked search for indexed fuzzy matches
- pay `O(N)` rebuild cost only when the catalog is refreshed
- accept `O(N)` index storage as the tradeoff for fast runtime lookup

### 3. Voice Inbox

Current design:
- listing pending audio is `O(K)` where `K` is the number of files in the inbox
- transcript/archive storage is `O(total transcript bytes + total archived bytes)`

Risk:
- very large inboxes will slow status checks and processing batches

Target design:
- keep the inbox small and archival automatic
- process incrementally and optionally keep queue metadata if the inbox grows

### 4. Planner

Current deterministic planning:
- rule checks are effectively `O(R * L)` where `R` is the number of rules and `L` is transcript length
- in practice `R` is small, so this stays cheap

LLM fallback:
- local model cost is dominated by prompt and response tokens, not Python control flow
- practical complexity is model-runtime dependent and should be treated as expensive compared to rule routing

Target design:
- keep deterministic routing first
- use LLM fallback only when rules cannot safely classify the request

### 5. Debate AI

Expected design:
- if `M` models run for `R` rounds over context size `C`, token work grows roughly with `O(M * R * C)`
- wall-clock cost also grows with the slowest provider in each round
- memory pressure grows with stored transcripts, critiques, and summaries

Risk:
- unconstrained debate loops become expensive very quickly

Target design:
- use strict round caps
- summarize intermediate outputs aggressively
- allow debate only for explicitly requested or high-value tasks

### 6. Screen Understanding

Expected design:
- image/screenshot analysis is proportional to frame size and frequency
- continuous high-rate screen processing can become the most expensive perception path

Risk:
- full-frame continuous interpretation will waste compute and increase latency

Target design:
- trigger analysis on user request, state changes, or bounded sampling intervals
- keep screenshot buffers bounded
- prefer event-driven snapshots over continuous frame streams when possible

### 7. Browser And UI Automation

Expected design:
- workflow runtime is roughly `O(S)` for `S` planned interaction steps
- memory cost is driven by stored DOM snapshots, selectors, action logs, and screenshots

Risk:
- replaying full DOMs or storing too much screen state can bloat memory

Target design:
- keep compact workflow states
- store only the selectors, action steps, confirmation preview, and final audit log needed for recovery

## Engineering Rules

To keep Aradhya scalable as an OI system:

1. Prefer incremental context updates over repeated full rescans.
2. Keep the model focused on reasoning, not on brute-force searching the machine.
3. Cache expensive local context in reusable indexes.
4. Put strict limits on debate rounds, snapshot sizes, and stored histories.
5. Treat UI and browser automation as bounded workflows with audit trails.
6. Delegate specialist document and conversion work instead of rebuilding every tool.

## Immediate Next Targets

1. Add a personal context folder for custom commands and user-owned rules.
2. Replace naive frequent tree thinking with watcher-driven context refresh design.
3. Expand safe local commands for app launching and named Windows targets.
4. Add browser workflow planning with review-before-submit behavior.
5. Design the first screen-guidance mode around screenshots instead of full live streams.
6. Define a bounded Debate AI protocol with round limits and summary compression.
