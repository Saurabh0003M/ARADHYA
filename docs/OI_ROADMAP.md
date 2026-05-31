# Aradhya OI Roadmap

For the full product thesis and category definition, see `docs/OI_VISION.md`.
For current Parasite OS build status and migration gates, see
`docs/PARASITE_OS_PROGRESS.md`.

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
- interact with shell, files, browser flows, and on-screen controls
- use confirmation gates before risky actions
- hand off heavyweight document and conversion tasks to stronger external tools
- dynamically absorb skills from web, code, or repositories at runtime

## OI Feature Set

### Current Foundation (Completed)

- **Model Engine Layer**: Swappable local model configuration through Ollama, with robust OpenRouter fallback (including 429 rate-limit failover chains and strict `CloudPrivacyGate` evaluation).
- **Context Engine**: Local directory index refresh (`project_tree.txt`), active window telemetry, clipboard context, and active browser context tracking.
- **Action Engine (Browser & UI)**: Complete browser automation tools (draft/submit/click), UI awareness via screenshot capabilities (`vision_tools.py`), and bounded shell actions.
- **Safety and Policy Engine**: Pattern-based Permission Engine (Regex gating and conditional blocks), lifecycle `HookEngine` (pre/post tool interception), and mandatory confirmation gates.
- **Parasite OS Digestion**: 7-stage state-machine ingestion pipeline (`ENGULF` to `ABSORB`), with automatic skill deduplication and host capability ranking via ledgers.
- **Agent Definitions**: YAML frontmatter + Markdown system prompt parsing for discrete personas.
- **Voice Subsystem**: Continuous 2.5s wake-word detection loops, `faster_whisper` offline pipelines, and `pyttsx3` text-to-speech integration.
- **Multi-Modal UI**: Rich CLI streaming, Tkinter Desktop Floating Icon with IPC file queues, and Telegram long-polling bot with simulated live-streaming (`editMessageText`).
- **Dynamic Skills & Learnings**: Intent-based token-conserving skill loading, runtime Git/Web skill absorption, and a `LearningsEngine` that auto-promotes recurring insights (e.g., 3+ hits) to standing rules.
- **LAN Federation Foundation**: Local SHA-256 identity fingerprinting, capability topology manifests, and peer registries.

### Core OI Features To Build (Next Priorities)

1. **Context Engine Phase 2**
- Move from repeated directory index updates toward watcher-backed invalidation (`O(delta)`).
- Complete the Miss-Debouncing cache validation routines to speed up frequent path lookups.

2. **External Handoff Engine**
- Route large PDF summary, file conversion, OCR, and similar tasks to stronger external tools or `AutoGPT`/`Agentless` framework hosts.
- Treat Aradhya as the orchestrator instead of rebuilding every specialist workflow locally.

3. **Debate AI and Diagnostics**
- Expand the current "Debate AI" UI toggle into full multi-model compare/critique/rebuttal workflows.
- Keep debate loops tightly constrained (strict round caps) to prevent token exhaustion.

4. **Federation Transport Layer**
- Complete LAN pairing handshake with signed identity envelopes.
- Implement secure, replay-protected peer-to-peer transport for capability routing.
- Prove drive/VM portability from a copied workspace before moving the active repo to the `D:\` drive.

## Build Order (Milestone Status)

### Milestone 1: OI Shell (✅ DONE)
Goal: make Aradhya reliable as a local operating layer before deeper automation.

### Milestone 2: Context Engine (🔄 IN PROGRESS)
Goal: improve machine awareness without paying continuous full-scan cost.
- File watchers and incremental builds are pending.
- Active-window and clipboard contexts are fully shipped.

### Milestone 3: Browser Operator (✅ DONE)
Goal: support real-world tasks such as forms, logins, and guided website flows.
- Implemented `browser_tools.py` with full navigation, interaction, and draft-before-submit flows.

### Milestone 4: Screen Guidance (✅ DONE)
Goal: help users complete tasks on pages and apps that Aradhya cannot yet fully automate.
- Vision tools with OCR and screenshot capabilities are fully shipped.

### Milestone 5: External Handoff (🔄 IN PROGRESS)
Goal: treat Aradhya as an orchestrator for specialist jobs.
- Foundation laid via skill loading, but PDF/conversion routing is pending.

### Milestone 6: Debate AI (🔄 IN PROGRESS)
Goal: turn Aradhya into a reasoning coordinator for higher-stakes decisions.
- UI toggles exist, but the strict critique protocol loops are pending.

### Milestone 7: Windows OI Experience (✅ DONE)
Goal: shift from "assistant app" to "operating intelligence layer".
- Desktop Floating Icon, Tray Daemon, background APIs, and rich shell integrations are fully implemented.

## Engineering Rules

To keep Aradhya scalable as an OI system:

1. Prefer incremental context updates over repeated full rescans.
2. Keep the model focused on reasoning, not on brute-force searching the machine.
3. Cache expensive local context in reusable indexes (like intent-based skill loading).
4. Put strict limits on debate rounds, snapshot sizes, and stored histories (like SQLite compaction).
5. Treat UI and browser automation as bounded workflows with audit trails.
6. Delegate specialist document and conversion work instead of rebuilding every tool.
