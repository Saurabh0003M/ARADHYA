# Aradhya Architecture

## Product Direction

Aradhya is an **Operating Intelligence (OI)**: a personal AI laptop assistant that understands natural-language requests about the machine itself, aggregates context, plans a safe action, and executes only after the user explicitly confirms. The design favors system control, workflow acceleration, and coordination over generic text generation.

## Core Principles

1. Wake explicitly through a floating icon, the `Ctrl + Win` hotkey, or Telegram.
2. Echo the transcript/request so the user can verify what Aradhya heard.
3. Plan before acting.
4. Require an explicit confirmation phrase (such as `yes proceed`) for device-affecting actions.
5. Provide multi-layered safety via Hook Engines and Permission Rules.
6. Refresh local context dynamically (clipboard, active windows, fast file indices).

## Runtime Layers

### 1. Wake & Entry Layer

- **Trigger sources**: Desktop Floating Icon (via Tkinter/IPC), global hotkeys, background Daemon API, and remote Telegram bots.
- **Responsibility**: Move the assistant from idle to active state and accept inputs securely.
- **Side effect**: Refresh the local directory index according to policy.

### 2. Perception & Context Layer

- **Vision Tools**: Aradhya possesses visual context capabilities, able to capture the screen and read textual content via OCR.
- **Speech-to-Text**: Whisper integration captures speech from a global hotkey, feeding into a background voice inbox pipeline.
- **System Telemetry**: Captures active window titles (via `ctypes`), clipboard content, and recent system files.
- **State Store**: Uses a thread-safe, WAL-mode SQLite database to automatically compress older message contexts while preserving robust session continuity.

### 3. Planner Layer

- Converts user transcripts into structured ReAct execution plans.
- Uses deterministic routing first for crisp local commands.
- Falls back to the configured local model only when rules cannot classify the request.
- Requires the model to output strict JSON tool calls.
- Determines when local file awareness, external-tool handoff, or specific SKILL contexts are required.

### 4. Confirmation Gate

- **Safety Pipeline**: Tool execution passes through the Parasite OS `HookEngine` (which can modify or block calls) and the `PermissionEngine` (deny-first rules).
- **User Approval**: Every device-affecting system task must pause behind an explicit approval phrase (`yes proceed`).
- **Dry-run Mode**: Operates entirely in a read-only testing environment unless live execution is explicitly enabled.

### 5. Executor Layer

- Leverages the extensive Tool Registry (`Browser`, `File`, `Power`, `Scheduler`, `Session`, `Shell`, `System`, `Vision`, `Web`).
- Supports complex, stateful workflows such as autonomous browser navigation, automated form interactions, and scheduled background tasks.
- Integrates gracefully with external `SKILL.md` definitions and custom agents (e.g. `AutoGPT`, `Agentless` frameworks).

### 6. Model Layer

- The local reasoning model is configured through `core/config/profile.local.json`.
- **Default Provider**: Ollama.
- **Fallback Provider**: OpenRouter. Cloud workers are gated behind a strict `CloudPrivacyGate` to ensure sensitive local context does not leak.
- Future model swaps happen exclusively by changing the profile, not the code logic.

## Local Data Strategy

Aradhya maintains a text snapshot of the visible directory tree in `project_tree.txt`, augmented by fast path-heuristics.

- Refresh on wake or on specific local-data requests.
- Skip rules ignore noisy directories such as `venv`, `node_modules`, `.git`, and caches.
- Utilizes node caps to maintain responsiveness on exceptionally large disks.
- Employs token-aware history compaction (e.g. merging 60 older messages into a synthesized context block) to preserve LLM token budgets.

## Current Supported Task Types

- Comprehensive browser automation (navigating, typing, clicking, capturing DOM elements).
- Vision-assisted screen reading and interpretation.
- Opening paths, launching applications, managing sleep/power states, and managing the system clipboard.
- Interrogating project environments using localized Git and dependency awareness.
- Executing detailed, structured engineering sprints (via the Sprint Factory).
- Scheduling recurring background system tasks.

## Voice Workflow Today

1. Drop audio into `audio/inbox`.
2. Process it through the configured voice provider (e.g. `manual_transcript` or `faster_whisper`).
3. Save the transcript into `audio/transcripts`.
4. Route the transcript into the assistant planner when Aradhya is awake.

When live voice activation is enabled via push-to-talk hotkeys or wake-word listeners ("wakeup", "arise"), microphone captures are routed transparently into the same inbox/transcript/archive workflow. This ensures that debugging, transcript inspection, and safety behaviors remain entirely consistent across text and voice.

## Long-Term Vision

The long-term target is **Aradhya OS**: an operating environment designed fundamentally around the assistant, replacing the concept of embedding an assistant inside a conventional desktop workflow. The operating system *is* the intelligence.
