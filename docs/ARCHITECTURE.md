# Aradhya Architecture

## Product Direction

Aradhya is being built as a personal AI laptop assistant that can understand natural-language requests about the machine itself, plan a safe action, and then execute only after the user explicitly confirms. The design favors system control, workflow acceleration, and coordination over generic text generation.

## Core Principles

1. Wake explicitly through a floating icon or the `Ctrl + Win` hotkey.
2. Echo the transcript so the user can verify what Aradhya heard.
3. Plan before acting.
4. Require an explicit confirmation phrase such as `yes proceed`.
5. Refresh local context whenever Aradhya wakes or is asked about local data.
6. Keep Debate AI mode optional and off by default.

## Runtime Layers

### 1. Wake Layer

- Trigger sources: floating icon, hotkey, and later voice wake if desired.
- Responsibility: move the assistant from idle to active state.
- Side effect: refresh the local directory index according to policy.

### 2. Perception Layer

- Whisper will handle speech-to-text.
- Optional live microphone activation can capture speech from a global hotkey and feed it into the same voice inbox pipeline.
- Future screen-reading adapters will inspect visible UI elements.
- The current repo simulates this with direct CLI text input.
- A folder-based voice inbox now exists so audio files can be dropped into `audio/inbox` and processed through a transcription pipeline.

### 3. Planner Layer

- Converts transcripts into structured plans.
- Uses deterministic routing first for crisp local commands.
- Falls back to the configured local model only when the rules cannot classify the request.
- Requires the model to return a strict JSON shape instead of free-form instructions.
- Knows which requests need local file awareness, external-tool handoff, or Debate AI.

### 4. Confirmation Gate

- Every executable system task must pause behind an explicit approval phrase.
- Pending plans can be confirmed or canceled.
- This replaces the earlier confidence-based auto-open behavior.

### 5. Executor Layer

- Opens files, folders, and URLs when live execution is enabled.
- Defaults to dry-run mode for safe testing.
- Future adapters will cover UI automation, file conversion pipelines, and external browser workflows.

### Model Layer

- The local reasoning model is configured through `core/memory/profile.json`.
- The current default provider is Ollama.
- The current default model is `gemma4:e4b`.
- Future model swaps should happen by changing the profile, not the code.

### 6. Debate AI Layer

- Optional reasoning mode.
- Intended behavior: send the prompt to multiple advanced systems, force critique/rebuttal rounds, and stop once consensus is reached.
- Current repo status: planned and represented in the planner, but not yet integrated with external providers.

## Local Data Strategy

Aradhya maintains a text snapshot of the visible directory tree in `project_tree.txt`.

- Refresh on wake.
- Refresh on local-data requests.
- Apply skip rules for noisy directories such as `venv`, `node_modules`, `.git`, and caches.
- Use a node cap so refreshes stay responsive on large disks.

This index is a support artifact for context and auditing. Local task previews still use live filesystem heuristics when needed.

## Current Supported Task Types

- Open a named path.
- Open preferred security blogs.
- Find the folder with the strongest `.txt` concentration.
- Reopen yesterday's active project.
- Attempt to identify the most recently played game if game-library roots are configured.
- Toggle Debate AI mode.

## Planned Integrations

- Whisper for speech recognition.
- Ollama for the local model.
- Screen OCR plus UI automation for contextual control of tools such as Google Meet.
- External handoff orchestration for heavy document operations.
- Open-source assistant and agentic system components where reuse is stronger than rebuilding from scratch.

## Voice Workflow Today

1. Drop audio into `audio/inbox`.
2. Process it through the configured voice provider.
3. Save the transcript into `audio/transcripts`.
4. Route the transcript into the assistant planner when Aradhya is awake.

The default provider is currently `manual_transcript`, which lets the repo work immediately even before Whisper is installed. The current repo also supports an optional `faster_whisper` provider for real local file transcription, while keeping `manual_transcript` as the zero-setup default. A `whisper_command` provider remains available for external command-based workflows.

When live voice activation is enabled, microphone captures are written into the same inbox/transcript/archive workflow instead of introducing a separate transcription path. That keeps debugging, transcript inspection, and safety behavior consistent.

## Long-Term Vision

The long-term target is Aradhya OS: an operating environment designed around the assistant instead of embedding the assistant inside a conventional desktop workflow.
