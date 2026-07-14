# Aradhya Operating Guide

This guide reflects the current Windows repo state for the Aradhya Operating Intelligence.

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
- Local LAN federation and topology state

## 3. Launching Interfaces

Aradhya supports multiple robust interfaces.

### Rich Terminal CLI
Recommended start:
```powershell
.\arise.bat
```
*(Provides live-streaming text, thought-block rendering, and dashboard tables).*

### Background Daemon & Floating Icon
Launch the background daemon (with the system tray and floating icon overlay):
```powershell
venv\Scripts\python.exe -m src.aradhya.daemon
```
The Floating Icon is a drag-and-drop overlay with quick-toggles for the Microphone, Screen Watch, and Debate AI. It communicates with the Daemon via an IPC file queue (`.aradhya_ipc_queue`).

### Telegram Bot
To start secure remote access:
```text
/telegram start
```
*(Only accessible to the first registered user; simulates live token generation via throttled message edits).*

## 4. First Commands To Try

Inside the Aradhya CLI:

```text
/help
/status
/model
/skills
/voice
/cache
/topology
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
- `/model` checks Ollama/OpenRouter health.
- `/voice` shows the audio inbox status.
- `/cache` validates the directory cache.
- Opening files, folders, apps, and URLs waits for confirmation.
- `allow_live_execution` is false by default, so confirmed opens are dry-run previews unless you enable live execution.

## 5. Configuration Files

Current primary config path:
- `core/config/profile.json`
- `core/config/profile.local.json`
- `core/config/preferences.json`

Machine-local model selections should go in `profile.local.json`.

## 6. Model Setup & Cloud Fallbacks

Aradhya uses **Ollama** by default, with optional **OpenRouter** and **Cloudflare Workers AI** providers for cloud-safe reasoning.

### Local Ollama Config:
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
1. Pull the model with Ollama, e.g. `ollama pull qwen2.5-coder:7b`.
2. Update `core/config/profile.local.json`.
3. Restart Aradhya.

### OpenRouter Config:
To use cloud workers (like DeepSeek, Llama 3, etc.):
1. Export `ARADHYA_OPENROUTER_API_KEY`.
2. Set provider to `openrouter` in `profile.local.json`.
3. Aradhya will automatically route requests through the `CloudPrivacyGate` to ensure no sensitive local secrets are leaked, and it provides an HTTP 429 failover chain if a model is rate-limited.

### Cloudflare Workers AI Config:
To use Cloudflare Workers AI:
1. Export `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID`. `CLOUDFLARE_AUTH_TOKEN` is also accepted as a fallback for older snippets.
2. Set provider to `cloudflare` in `profile.local.json`.
3. Optionally set `model.model_name`; otherwise Aradhya defaults to `@cf/zai-org/glm-5.2`.

## 7. Voice & Audio Workflow

### Default Flow (Manual / Inbox)
1. Put audio in `audio/inbox`, e.g., `task.wav`.
2. Put matching text in `audio/manual_transcripts`, e.g., `task.txt`.
3. Run `/voice process`.

### Real Local Transcription (`faster_whisper`)
1. Install `requirements-voice.txt`.
2. Set `voice.provider` to `faster_whisper` in `core/config/profile.local.json`.
3. Audio dropped in the inbox is automatically transcribed locally.

### Live Voice Activation (Push-To-Talk)
1. Install `requirements-voice-activation.txt`.
2. Ensure `voice.provider` is `faster_whisper` or `whisper_command`.
3. Run `/voice activate` or use the global keyboard hotkey. Aradhya records until silence, transcribes, processes the command, and replies using `pyttsx3` text-to-speech.

### Continuous Wake-Word Detection
Toggle background listening via:
```text
/wake-word on
```
Aradhya listens in 2.5-second chunks for "wakeup" or "arise".

## 8. Directory Cache & State Store

Aradhya writes a human-readable summary to `project_tree.txt`.
However, core session memory, message history, and audit events are managed by a robust, thread-safe **SQLite WAL Database** (`state.sqlite`).

Default roots are intentionally bounded for first-run responsiveness:
- Desktop, Documents, Downloads (if they exist)
- The cloned project root

*(Do not point `user_roots` at all of `C:\Users\<you>` unless you accept slower startup scans).*

## 9. Important Code Subsystems

- `src/aradhya/main.py`: CLI entry point & rich rendering loop.
- `src/aradhya/daemon.py`: Background tray icon & HTTP API.
- `src/aradhya/agent_loop.py`: ReAct execution, context boundaries, and kill switches.
- `src/aradhya/state_store.py`: SQLite session and history compaction logic.
- `src/aradhya/tools/`: Capabilities (Browser, File, Shell, Vision, Scheduler).
- `src/aradhya/hooks/` & `src/aradhya/permission_rules.py`: The Symbiont safety gates and interception engines.
- `src/aradhya/symbiont/`: The 7-stage host-repo ingestion state-machine.
- `src/aradhya/voice/`: Transcriber, synthesizer, hotkey activation, and wake-word listeners.
