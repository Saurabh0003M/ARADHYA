# Aradhya Operating Guide

This guide reflects the current Windows repo state.

## 1. First Setup

From PowerShell:

```powershell
cd "F:\ARADHYA"
scripts\first_run.bat
```

What this does:

- creates or repairs `venv`
- installs `requirements.txt`
- installs `requirements-dev.txt`
- runs `scripts\doctor.bat`

Optional feature packs:

```powershell
venv\Scripts\python.exe -m pip install -r requirements-voice.txt
venv\Scripts\python.exe -m pip install -r requirements-voice-activation.txt
venv\Scripts\python.exe -m pip install -r requirements-windows.txt
```

## 2. Health Check

Run:

```powershell
scripts\doctor.bat
```

Doctor checks:

- Python 3.10+
- local venv health
- core runtime imports such as `rich`, `mcp`, `loguru`, `requests`, `pandas`, and `numpy`
- development test dependencies
- configured Ollama model availability

## 3. Launch

Recommended:

```powershell
.\arise.bat
```

Direct module form:

```powershell
venv\Scripts\python.exe -m src.aradhya.main
```

The launcher prefers the local venv when it has the required runtime packages. If the venv is incomplete, it falls back to `python` on `PATH` and tells you to rerun `scripts\first_run.bat`.

## 4. First Commands To Try

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
enable debate mode
research the safest rollout for this change
disable debate mode
/audit
exit
```

Notes:

- `/model` checks Ollama health.
- `/voice` shows the audio inbox status.
- `/cache` validates the directory cache.
- Opening files, folders, apps, and URLs waits for confirmation.
- `allow_live_execution` is false by default, so confirmed opens are dry-run previews unless you enable live execution.

## 5. Configuration Files

Current primary config path:

- `core/config/profile.json`
- `core/config/profile.local.json`
- `core/config/preferences.json`

Legacy fallback path:

- `core/memory/profile.json`
- `core/memory/profile.local.json`
- `core/memory/preferences.json`

Machine-local model selections should go in `profile.local.json`.

## 6. Model Setup

Aradhya uses Ollama by default.

The current model comes from:

```json
{
  "model": {
    "provider": "ollama",
    "model_name": "gemma4:e2b",
    "base_url": "http://127.0.0.1:11434"
  }
}
```

To change models:

1. Pull the model with Ollama, for example `ollama pull qwen2.5-coder:7b`.
2. Update `core/config/profile.local.json`.
3. Restart Aradhya.

## 7. Voice Workflow

Default voice provider: `manual_transcript`.

Manual flow:

1. Put audio in `audio/inbox`, for example `task.wav`.
2. Put matching text in `audio/manual_transcripts`, for example `task.txt`.
3. Run `/voice process`.

Aradhya then:

- reads the matching transcript
- moves audio to `audio/processed`
- writes final text to `audio/transcripts`
- routes the transcript into the planner if Aradhya is awake

Real local transcription:

1. Install `requirements-voice.txt`.
2. Set `voice.provider` to `faster_whisper` in `core/config/profile.json` or `profile.local.json`.
3. Run `/voice process`.

Live microphone activation:

1. Install `requirements-voice-activation.txt`.
2. Set `voice.provider` to `faster_whisper` or `whisper_command`.
3. Run `/voice activate`.

## 8. Directory Cache

Aradhya writes a human-readable summary to:

- `project_tree.txt`

The cache source of truth is:

- `data/processed/context/manifest.json`
- `data/processed/context/drive_*.json`

Default roots are intentionally bounded for first-run responsiveness:

- Desktop, if it exists
- Documents, if it exists
- Downloads, if it exists
- the cloned project root

Do not point `user_roots` at all of `C:\Users\<you>` unless you accept slower startup scans.

## 9. Important Code Files

- `src/aradhya/main.py`: CLI entry point
- `src/aradhya/assistant_core.py`: wake, idle, confirmation, and planning flow
- `src/aradhya/assistant_indexer.py`: directory cache and `project_tree.txt`
- `src/aradhya/assistant_planner.py`: deterministic planner
- `src/aradhya/llm_planner.py`: local-model fallback planner
- `src/aradhya/model_provider.py`: Ollama provider
- `src/aradhya/runtime_profile.py`: model and voice config loader
- `src/aradhya/voice/pipeline.py`: audio inbox and transcript handling
- `src/aradhya/voice/transcriber.py`: transcription providers
- `src/aradhya/voice/activation.py`: live microphone activation
