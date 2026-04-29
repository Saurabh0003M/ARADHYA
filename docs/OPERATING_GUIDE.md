# Aradhya Operating Guide

This guide is written for the current repo state on Windows so you can clone the project anywhere, run Aradhya, inspect what changed, and understand which files are responsible for each behavior.

## 1. Clone And Open The Project

Run this in PowerShell:

```powershell
git clone <your-github-url> aradhya
cd aradhya
code .
```

Useful files to pin in VS Code:

- `src/aradhya/main.py`
- `src/aradhya/assistant_core.py`
- `src/aradhya/assistant_indexer.py`
- `src/aradhya/runtime_profile.py`
- `src/aradhya/voice_pipeline.py`
- `core/memory/preferences.json`
- `core/memory/profile.json`
- `core/memory/profile.local.json`

## 2. Create The Environment

In the VS Code terminal:

Fastest path on Windows:

```powershell
scripts\first_run.bat
```

Manual path:

```powershell
py -3.10 -m venv venv
venv\Scripts\python.exe -m pip install --upgrade pip
venv\Scripts\python.exe -m pip install -r requirements.txt
venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

To verify a cloned machine after setup, run:

```powershell
scripts\doctor.bat
```

Why this is portable:

- the repo does not assume a fixed drive letter
- the runtime discovers the repo root from the current code location
- the default Ollama home is derived from the current user's home directory

## 3. Start Aradhya

Run:

```powershell
venv\Scripts\python.exe -m core.agent.aradhya
```

Or simply use the global shortcut from the project root:

```powershell
.\aradhya
```

Why this works:

- `core/agent/aradhya.py` is the compatibility launcher
- it forwards to `src/aradhya/main.py`
- `main.py` creates the assistant, loads config, prepares the voice folders, and starts the CLI loop

## 4. First Commands To Try

Once Aradhya starts, type these exactly:

```text
cache validate
model ping
voice status
voice activate
wake
open aradhya
yes proceed
voice stop
voice stop
icon enable
wake word enable
find the folder with the highest concentration of .txt files
yes proceed
sleep
exit
```

What each command does:

- `cache validate`: rebuilds the context cache, measures warm-cache reuse, and checks whether a targeted rescan can discover a new probe folder
- `model ping`: checks Ollama and confirms whether the configured model is reachable
- `voice status`: shows the current audio folders and pending voice files
- `voice activate`: starts the background hotkey listener for microphone capture and optional spoken replies
- `wake`: wakes Aradhya and refreshes `project_tree.txt`
- `open aradhya`: creates a plan to open the best-matching path
- `yes proceed`: executes the pending plan
- `voice stop`: stops live microphone capture mode
- `icon enable`: launches an always-on-top draggable menu that expands on click
- `wake word enable`: starts the continuous background wake word engine (say "wakeup" or "arise")
- `.txt` query: triggers a local-data search and refreshes the tree again
- `sleep`: clears pending work and puts Aradhya idle
- `exit`: closes the CLI

## 5. How To Confirm The Tree File Is Updating

Before running `wake`, check the file timestamp:

```powershell
Get-Item .\project_tree.txt | Select-Object LastWriteTime, Length
```

Then run Aradhya and type:

```text
wake
exit
```

Check the timestamp again:

```powershell
Get-Item .\project_tree.txt | Select-Object LastWriteTime, Length
Get-Content .\project_tree.txt -TotalCount 5
```

What you should see:

- `LastWriteTime` changes
- top lines include `generated_at=...`
- top lines include `reason=wake` or `reason=local_query`

Where the refresh happens in code:

- `src/aradhya/assistant_core.py`
  `handle_wake()` calls the indexer on wake
- `src/aradhya/assistant_core.py`
  local-data requests refresh again in `handle_transcript()`
- `src/aradhya/assistant_indexer.py`
  `output_path.write_text(...)` is the line that actually rewrites `project_tree.txt`

The human-readable tree file is only the summary artifact. The cache source of truth is:

- `data/processed/context/manifest.json`
- `data/processed/context/drive_*.json`

## 6. What Aradhya Can Actually Do Right Now

These features are real in the current code:

- wake and go idle
- echo transcripts
- build a plan before acting
- require explicit confirmation before device-affecting execution
- refresh the local tree index
- dry-run or execute path opens, depending on config
- find the strongest `.txt`-heavy folder
- reopen yesterday's active project using project markers
- open preferred security blogs
- toggle Debate AI mode
- check the configured Ollama model
- send direct prompts to the configured Ollama model with `model ask ...`
- process dropped voice files through the current folder-based voice workflow
- use the configured Ollama model as a fallback planner for ambiguous system requests
- optionally listen for a global hotkey, capture microphone audio, and route it through the same planner
- optionally speak Aradhya's live voice replies aloud with a local TTS provider

These features are only partially present or still planned:

- ambient or wake-word-based listening without push-to-talk (partially available via `wake word enable`)
- screen reading and UI control
- Google Meet button interaction
- full Debate AI multi-model reasoning loop
- automatic heavy-document handoff to external tools
- full autonomous laptop control

## 7. How Voice Works Right Now

Current folders:

- `audio/inbox`
- `audio/manual_transcripts`
- `audio/transcripts`
- `audio/processed`

Supported audio formats right now:

- `.mp3`
- `.wav`
- `.m4a`
- `.flac`
- `.ogg`
- `.opus`
- `.aac`

Current default flow:

1. Drop an audio file into `audio/inbox`
2. Create a matching transcript text file in `audio/manual_transcripts`
3. Start Aradhya
4. Type `voice process`

Example:

- `audio/inbox/task.opus`
- `audio/manual_transcripts/task.txt`

What happens next:

- Aradhya reads the matching `.txt`
- moves the audio into `audio/processed`
- writes the final transcript into `audio/transcripts`
- if Aradhya is awake, it routes that transcript into the planner

Optional real local file transcription:

1. Install `requirements-voice.txt`
2. Change `voice.provider` in `core/memory/profile.json` to `faster_whisper`
3. Drop the audio file into `audio/inbox`
4. Run `voice process`

In that mode Aradhya generates the transcript locally and still uses the same inbox, transcript, and archive folders.

Optional live voice activation:

1. Install `requirements-voice-activation.txt`
2. Set `voice.provider` to `faster_whisper` or `whisper_command`
3. Set `voice_output.enabled` to `true` if you want spoken replies
4. Run `voice activate`
5. Press the configured hotkey from `profile.json`
6. Speak your request and wait for Aradhya to print the transcript and response

If spoken replies are enabled, Aradhya speaks only the assistant reply itself. Status lines such as recording, transcript saves, and archive paths remain text-only for auditability.

Responsible file:

- `src/aradhya/voice_pipeline.py`

## 8. How To Change The Model Later

Open:

- `core/memory/profile.json`
- `core/memory/profile.local.json`

Current model section:

```json
"model": {
  "provider": "ollama",
  "model_name": "gemma4:e4b",
  "base_url": "http://127.0.0.1:11434"
}
```

To switch engines later:

1. Pull or install the new model in Ollama
2. Change only `"model_name"`
3. Keep the provider as `"ollama"` unless you add a different provider implementation

Example future change:

```json
"model_name": "gemma5"
```

Why this is swappable:

- the assistant reads the runtime profile from `profile.json`
- startup model selection writes machine-specific choices into `profile.local.json`
- `src/aradhya/model_provider.py` builds the provider from config
- Aradhya code does not hard-code Gemma inside the planner or CLI

## 9. How To Change Behavior

Open:

- `core/memory/preferences.json`
- `core/memory/profile.json`
- `core/memory/profile.local.json`

Useful fields in `preferences.json`:

- `allow_live_execution`
- `directory_index_path`
- `confirmation_phrases`
- `security_blog_urls`
- `game_library_roots`
- `directory_index_policy.refresh_on_wake`
- `directory_index_policy.refresh_on_local_query`
- `directory_index_policy.miss_cache_ttl_seconds`
- `directory_index_policy.miss_refresh_debounce_seconds`

Useful fields in `profile.json`:

- `model.model_name`
- `voice.provider`
- `voice.whisper_command_template`
- `voice.faster_whisper_model_size`
- `voice.faster_whisper_device`
- `voice.faster_whisper_compute_type`
- `voice.language`
- `voice.audio_inbox_dir`
- `voice_activation.enabled_on_startup`
- `voice_activation.hotkey_modifiers`
- `voice_activation.hotkey_key`
- `voice_activation.silence_duration`
- `voice_activation.silence_threshold`
- `voice_output.enabled`
- `voice_output.provider`
- `voice_output.voice_id`
- `voice_output.rate`
- `voice_output.volume`

## 10. Most Important Code Files

- `src/aradhya/main.py`
  CLI entry point and top-level commands
- `src/aradhya/assistant_core.py`
  wake, idle, confirmation, and planning flow
- `src/aradhya/assistant_indexer.py`
  tree-file generation
- `src/aradhya/assistant_planner.py`
  deterministic planner plus model-backed fallback routing
- `src/aradhya/llm_planner.py`
  strict JSON parsing and safe LLM intent classification
- `src/aradhya/json_extractor.py`
  robust JSON extraction from imperfect model responses
- `src/aradhya/assistant_system_tools.py`
  task heuristics and execution behavior
- `src/aradhya/model_provider.py`
  Ollama provider layer
- `src/aradhya/hotkey_listener.py`
  optional global hotkey listener for live voice activation
- `src/aradhya/microphone_capture.py`
  optional sounddevice-based microphone capture
- `src/aradhya/runtime_profile.py`
  swappable model and voice config loader
- `src/aradhya/voice_activation.py`
  background hotkey + microphone integration using the same inbox pipeline
- `src/aradhya/voice_pipeline.py`
  audio inbox and transcript handling
- `src/aradhya/voice_transcriber.py`
  swappable file transcription providers
