# Aradhya

Aradhya is a personal AI laptop assistant focused on system-level help, not just chat. The current codebase centers on a safe planner that wakes on demand, echoes the transcript, prepares a task, waits for an explicit confirmation phrase such as `yes proceed`, and only then executes.

## Current Foundation

- Wake-aware assistant session model with `wake`, `ctrl+win`, and `sleep` flow in the CLI.
- Strict plan-then-confirm execution pipeline for system actions.
- Local directory-index refresh that creates or updates `project_tree.txt` on wake and local-data queries.
- Heuristics for opening paths, finding the most `.txt`-dense folder, reopening yesterday's active project, opening preferred security blogs, and toggling Debate AI mode.
- Safe dry-run execution by default so the assistant can be tested without launching apps unexpectedly.
- A runtime profile that binds Aradhya to a configurable Ollama model instead of hard-coding Gemma into the code.
- A voice inbox pipeline with explicit folders for dropped audio, processed files, and transcripts.

If you want a hands-on walkthrough, open `docs/OPERATING_GUIDE.md`.

## Project Structure

```text
<repo-root>
|-- core/
|   |-- agent/
|   |   `-- aradhya.py
|   `-- memory/
|       |-- preferences.json
|       `-- profile.json
|-- docs/
|   |-- ARCHITECTURE.md
|   |-- OPERATING_GUIDE.md
|   `-- phases/
|-- src/
|   `-- aradhya/
|       |-- assistant_core.py
|       |-- assistant_indexer.py
|       |-- assistant_models.py
|       |-- assistant_planner.py
|       |-- assistant_system_tools.py
|       |-- model_provider.py
|       |-- runtime_profile.py
|       |-- voice_pipeline.py
|       `-- main.py
|-- audio/
|-- tests/
|   `-- unit/
`-- scripts/
```

## Quick Start

Clone the repo, create a virtual environment, install dependencies, and run Aradhya:

```powershell
git clone <your-github-url> aradhya
cd aradhya
py -3.10 -m venv venv
venv\Scripts\python.exe -m pip install --upgrade pip
venv\Scripts\python.exe -m pip install -r requirements.txt
venv\Scripts\python.exe -m pip install -r requirements-dev.txt
venv\Scripts\python.exe -m core.agent.aradhya
```

If you already activated the environment, this also works:

```powershell
python -m core.agent.aradhya
```

Inside the CLI:

- Type `wake` to simulate the floating icon.
- Type `ctrl+win` to simulate the hotkey wake path.
- Type a spoken request as plain text.
- Type `yes proceed` to execute the pending plan.
- Type `voice status` to inspect the audio inbox setup.
- Type `voice process` to process dropped audio files.
- Type `model ping` to check the configured Ollama model.
- Type `model ask <prompt>` to send a direct prompt to the configured local model.
- Type `sleep` to return Aradhya to idle.

## Configuration

Runtime behavior is loaded from `core/memory/preferences.json`.

- `allow_live_execution`: if `false`, Aradhya dry-runs actions instead of opening apps or URLs.
- `directory_index_path`: where the tree file is written.
- `security_blog_urls`: browser targets for the security-blog feature.
- `game_library_roots`: folders used when searching for a recent game.

Runtime model and voice bindings are loaded from `core/memory/profile.json`.

- The default local model is `gemma4:e4b`.
- The Ollama model directory defaults to the current user's home folder via `Path.home() / ".ollama"`.
- To switch to a future model like `gemma5`, change only `model_name` in `profile.json`.

## Voice Files

If you want to feed voice through files right now, drop audio into `audio/inbox`.

- Supported input types: `.mp3`, `.wav`, `.m4a`, `.flac`, `.ogg`, `.opus`, `.aac`
- Final transcripts land in `audio/transcripts`
- Processed audio is archived in `audio/processed`
- Until Whisper is configured, put a matching `.txt` transcript into `audio/manual_transcripts`

Example:

- `audio/inbox/task.opus`
- `audio/manual_transcripts/task.txt`

Then run `voice process`.

## Testing

```powershell
venv\Scripts\python.exe -m pytest tests\unit\test_agent.py tests\unit\test_runtime_profile.py
```

## Roadmap

The current implementation establishes the assistant core for the updated vision. The next layers are:

- Whisper-based speech input and transcript playback
- screen-reading plus UI control adapters
- external-tool handoff for heavy document work
- multi-model Debate AI orchestration
- the longer-term Aradhya OS direction
