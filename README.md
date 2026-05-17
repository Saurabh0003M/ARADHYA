# Aradhya

Aradhya is a local-first Operating Intelligence assistant for Windows. It uses Ollama for local model inference, keeps user data on the machine, and routes risky system actions through explicit confirmation.

## What It Can Do Today

- Start a Rich terminal assistant.
- Use a local Ollama model for chat and fallback planning.
- Build safe plans before opening files, folders, apps, or URLs.
- Require confirmation before device-affecting actions.
- Keep a local directory cache and summary in `project_tree.txt`.
- Process dropped voice files through the audio inbox.
- Optionally use push-to-talk microphone capture.
- Load local `SKILL.md` instruction packs from `core/skills`.

## Requirements

- Windows 10 or 11
- Python 3.10+
- Git
- Ollama
- At least one local Ollama model

The current configured model is read from `core/config/profile.local.json` first, then `core/config/profile.json`.

## First Run

From PowerShell:

```powershell
git clone https://github.com/Saurabh0003M/ARADHYA.git ARADHYA
cd ARADHYA
scripts\first_run.bat
```

Then verify:

```powershell
scripts\doctor.bat
```

## Launch

```powershell
.\arise.bat
```

The launcher prefers `venv\Scripts\python.exe` when the venv has the required runtime packages. If the venv is incomplete, it falls back to `python` on `PATH` and tells you to rerun setup.

Direct launch:

```powershell
venv\Scripts\python.exe -m src.aradhya.main
```

## First Commands

Inside Aradhya:

```text
/help
/status
/model
/skills
/voice
/cache
open README.md
yes proceed
find the folder with the highest concentration of .txt files
exit
```

## Configuration

Primary config:

- `core/config/profile.json`
- `core/config/profile.local.json`
- `core/config/preferences.json`

Legacy fallback config:

- `core/memory/profile.json`
- `core/memory/profile.local.json`
- `core/memory/preferences.json`

Important fields:

- `model.model_name`: Ollama model name.
- `model.base_url`: Ollama API URL, usually `http://127.0.0.1:11434`.
- `allow_live_execution`: false by default. When false, confirmed opens and launches are dry-run previews.
- `user_roots`: optional search roots. If omitted, Aradhya uses Desktop, Documents, Downloads, and the repo root instead of scanning the entire home folder.

## Voice

Default voice provider: `manual_transcript`.

Manual transcript flow:

1. Put audio in `audio/inbox`, for example `task.wav`.
2. Put matching text in `audio/manual_transcripts`, for example `task.txt`.
3. Run `/voice process`.

Optional local transcription:

```powershell
venv\Scripts\python.exe -m pip install -r requirements-voice.txt
```

Optional live microphone activation:

```powershell
venv\Scripts\python.exe -m pip install -r requirements-voice-activation.txt
```

## Project Structure

```text
core/
  config/       Runtime configuration
  memory/       User context and legacy config fallback
  skills/       Bundled SKILL.md files
src/aradhya/
  main.py       CLI entry point
  assistant_core.py
  assistant_indexer.py
  model_provider.py
  voice/
scripts/
  first_run.bat
  doctor.bat
  run_agent.bat
```

## Safety Model

- Risky tools require explicit confirmation.
- Live execution is disabled by default.
- Tool calls are audited.
- Local tools and local models are preferred.
