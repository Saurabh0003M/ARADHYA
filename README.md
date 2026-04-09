# Aradhya

Aradhya is a personal AI laptop assistant focused on system-level help, not just chat. The current codebase centers on a safe planner that wakes on demand, echoes the transcript, prepares a task, waits for an explicit confirmation phrase such as `yes proceed`, and only then executes.

## Current Foundation

- Wake-aware assistant session model with `wake`, `ctrl+win`, and `sleep` flow in the CLI.
- Strict confirmation for device-affecting system actions, with immediate execution for low-risk internal state changes.
- Local directory-index refresh that creates or updates `project_tree.txt` on wake and local-data queries.
- Heuristics for opening paths, finding the most `.txt`-dense folder, reopening yesterday's active project, opening preferred security blogs, and toggling Debate AI mode.
- Hybrid planning that keeps deterministic routing first and uses the configured Ollama model as a JSON-only fallback classifier for ambiguous requests.
- Safe dry-run execution by default so the assistant can be tested without launching apps unexpectedly.
- A runtime profile that binds Aradhya to a configurable Ollama model instead of hard-coding Gemma into the code.
- A voice inbox pipeline with explicit folders for dropped audio, processed files, and transcripts, plus an optional `faster_whisper` provider for real local transcription.
- Optional live voice activation that can listen for a global hotkey, record from the microphone, and route the transcript through the same planner and confirmation gate.
- Optional local spoken replies during live voice activation through a Windows-friendly `pyttsx3` output provider.

If you want a hands-on walkthrough, open `docs/OPERATING_GUIDE.md`.

## Aradhya OI Features

Aradhya is being shaped as an `OI` layer: `Operating Intelligence`.
The operating system runs the machine. Aradhya is meant to understand
intent, gather live context, and safely operate the machine under policy.

- Swappable model engine through Ollama so users can replace today's model
  with future local models without rewriting Aradhya itself.
- Wake-aware operating flow with explicit active and idle states.
- Policy-bounded execution with confirmation for device-affecting actions.
- Local machine context through `project_tree.txt`, configured roots, and
  path-aware heuristics.
- Diagnostics for local model readiness, Ollama reachability, and startup
  model selection when the configured engine is missing.
- Deterministic-first planning with local-model fallback classification for
  ambiguous requests.
- Voice inbox workflow for dropped recordings, transcripts, and archived audio.
- Push-to-talk live voice activation through a global hotkey.
- Optional spoken replies through a local Windows-friendly text-to-speech path.
- Debate AI mode for future multi-model critique, rebuttal, and consensus.
- External-tool handoff direction for large PDF, document, and conversion work
  that is better delegated than rebuilt inside Aradhya.
- Future screen-reading, browser-operation, and UI-guidance capabilities for
  form filling, guided workflows, and on-screen assistance.

If you want the product-level vision, open `docs/OI_VISION.md`.
If you want the milestone order and implementation direction, open
`docs/OI_ROADMAP.md`.

## Project Structure

```text
<repo-root>
|-- core/
|   |-- agent/
|   |   `-- aradhya.py
|   `-- memory/
|       |-- preferences.json
|       |-- profile.json
|       `-- profile.local.json
|-- docs/
|   |-- ARCHITECTURE.md
|   |-- OPERATING_GUIDE.md
|   `-- phases/
|-- scripts/
|   |-- doctor.bat
|   |-- first_run.bat
|   `-- run_agent.bat
|-- src/
|   `-- aradhya/
|       |-- assistant_core.py
|       |-- assistant_indexer.py
|       |-- llm_planner.py
|       |-- logging_utils.py
|       |-- json_extractor.py
|       |-- assistant_models.py
|       |-- assistant_planner.py
|       |-- assistant_system_tools.py
|       |-- hotkey_listener.py
|       |-- microphone_capture.py
|       |-- model_provider.py
|       |-- runtime_profile.py
|       |-- voice_activation.py
|       |-- voice_pipeline.py
|       |-- voice_transcriber.py
|       `-- main.py
|-- audio/
|-- tests/
|   `-- unit/
`-- requirements.txt
```

## Quick Start

Clone the repo, create a virtual environment, install dependencies, and run Aradhya:

On Windows, the quickest setup path is:

```powershell
git clone <your-github-url> aradhya
cd aradhya
scripts\first_run.bat
```

If you want the manual setup steps instead:

```powershell
git clone <your-github-url> aradhya
cd aradhya
py -3.10 -m venv venv
venv\Scripts\python.exe -m pip install --upgrade pip
venv\Scripts\python.exe -m pip install -r requirements.txt
venv\Scripts\python.exe -m pip install -r requirements-dev.txt
venv\Scripts\python.exe -m core.agent.aradhya
```

Optional local transcription:

```powershell
venv\Scripts\python.exe -m pip install -r requirements-voice.txt
```

Optional live microphone activation:

```powershell
venv\Scripts\python.exe -m pip install -r requirements-voice-activation.txt
```

If you already activated the environment, this also works:

```powershell
python -m core.agent.aradhya
```

To verify a new machine after cloning on `C:` or `D:`, run:

```powershell
scripts\doctor.bat
```

Inside the CLI:

- Type `wake` to simulate the floating icon.
- Type `ctrl+win` to simulate the hotkey wake path.
- Type a spoken request as plain text.
- Type `yes proceed` to execute the pending plan.
- Type `cache validate` to rebuild and benchmark the context cache.
- Type `voice status` to inspect the audio inbox setup.
- Type `voice process` to process dropped audio files.
- Type `voice activate` to start background hotkey-based microphone capture.
- Type `voice stop` to stop the background hotkey listener.
- Type `model ping` to check the configured Ollama model.
- Type `model ask <prompt>` to send a direct prompt to the configured local model.
- Type `sleep` to return Aradhya to idle.

## Configuration

Runtime behavior is loaded from `core/memory/preferences.json`.

- `allow_live_execution`: if `false`, Aradhya dry-runs actions instead of opening apps or URLs.
- `directory_index_path`: where the tree file is written.
- `security_blog_urls`: browser targets for the security-blog feature.
- `game_library_roots`: folders used when searching for a recent game.

Runtime model, voice, and spoken-reply bindings are loaded from `core/memory/profile.json`.
Machine-specific overrides can live in `core/memory/profile.local.json`, which is git-ignored and merged over the shared profile at runtime.

- The default local model is `gemma4:e4b`.
- Interactive startup model selection writes only to `profile.local.json` so local choices do not dirty the shared repo defaults.
- The Ollama model directory defaults to the current user's home folder via `Path.home() / ".ollama"`.
- To switch to a future model like `gemma5`, change only `model_name` in `profile.json`.
- The default voice provider is `manual_transcript` so the repo still works immediately after clone.
- To enable real local file transcription, install `requirements-voice.txt` and change `voice.provider` to `faster_whisper`.
- `voice.faster_whisper_model_size`, `voice.faster_whisper_device`, `voice.faster_whisper_compute_type`, and `voice.language` control the optional Faster-Whisper provider.
- Live microphone activation is configured under `voice_activation` in `profile.json`.
- Spoken replies for push-to-talk voice mode are configured under `voice_output` in `profile.json`.
- To enable spoken replies, install `requirements-voice-activation.txt` and set `voice_output.enabled` to `true`.
- For live voice activation, use `voice.provider = faster_whisper` or `voice.provider = whisper_command`, then install `requirements-voice-activation.txt`.

## Windows Helper Scripts

- `scripts\first_run.bat`: finds a usable Python launcher, creates or repairs `venv`, installs the core dependencies, records a dependency stamp, and then runs the setup doctor.
- `scripts\doctor.bat`: checks Python availability, verifies the local `venv`, confirms core dependencies, warns when `requirements*.txt` changed after the last install, and inspects Ollama plus the configured model.
- `scripts\setup.bat`: compatibility wrapper that now delegates to `scripts\first_run.bat`.
- `scripts\run_agent.bat`: launches Aradhya through the repo-local `venv`.
- `scripts\run_tests.bat`: runs the unit test suite through the repo-local `venv`.

## Voice Files

If you want to feed voice through files right now, drop audio into `audio/inbox`.

- Supported input types: `.mp3`, `.wav`, `.m4a`, `.flac`, `.ogg`, `.opus`, `.aac`
- Final transcripts land in `audio/transcripts`
- Processed audio is archived in `audio/processed`
- In the default `manual_transcript` mode, put a matching `.txt` transcript into `audio/manual_transcripts`
- In `faster_whisper` mode, Aradhya generates the transcript itself from the dropped audio file

Example:

- `audio/inbox/task.opus`
- `audio/manual_transcripts/task.txt`

Then run `voice process`.

## Live Voice Activation

If you want Aradhya to listen through the microphone:

1. Install `requirements-voice-activation.txt`
2. Set `voice.provider` to `faster_whisper` or `whisper_command`
3. Optionally set `voice_output.enabled` to `true` if you want spoken replies
4. Adjust `voice_activation` and `voice_output` settings in `core/memory/profile.json` if needed
5. Start the CLI and run `voice activate`

Live capture writes audio into the same inbox flow, so transcripts, archives, planner routing, and optional spoken replies stay consistent with the file-based path.

## Testing

```powershell
venv\Scripts\python.exe -m pytest tests\unit
```

If `venv\Scripts\python.exe` points at a missing base installation, recreate the environment locally instead of reusing an old `venv` directory:

```powershell
Remove-Item -Recurse -Force .\venv
py -3.10 -m venv venv
venv\Scripts\python.exe -m pip install --upgrade pip
venv\Scripts\python.exe -m pip install -r requirements.txt
venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

If you want a quick health check after pulling changes or moving the repo to another laptop, run:

```powershell
scripts\doctor.bat
```

## Roadmap

The current implementation establishes the assistant core for the updated vision. The next layers are:

- microphone-based push-to-talk voice capture
- screen-reading plus UI control adapters
- external-tool handoff for heavy document work
- multi-model Debate AI orchestration
- the longer-term Aradhya OS direction

For the full OI vision, see `docs/OI_VISION.md`.
For the roadmap, milestone order, and time/space complexity notes, see
`docs/OI_ROADMAP.md`.
