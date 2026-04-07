# Aradhya Operating Guide

This guide is written for the current repo state on Windows so you can open the project, run Aradhya, inspect what changed, and understand which files are responsible for each behavior.

## 1. Open The Project

1. Open VS Code.
2. Click `File > Open Folder...`
3. Open `F:\ARADHYA`
4. In VS Code, open the integrated terminal with `` Ctrl + ` ``

Useful files to pin in the editor:

- `src/aradhya/main.py`
- `src/aradhya/assistant_core.py`
- `src/aradhya/assistant_indexer.py`
- `src/aradhya/runtime_profile.py`
- `src/aradhya/voice_pipeline.py`
- `core/memory/preferences.json`
- `core/memory/profile.json`
- `project_tree.txt`

## 2. Start Aradhya

Run these commands in the VS Code terminal:

```powershell
cd F:\ARADHYA
venv\Scripts\activate
python -m core.agent.aradhya
```

Why this works:

- `core/agent/aradhya.py` is the compatibility launcher.
- It forwards to `src/aradhya/main.py`.
- `main.py` creates the assistant, loads config, prepares the voice folders, and starts the CLI loop.

## 3. First Commands To Try

Once Aradhya starts, type these exactly:

```text
model ping
voice status
wake
open aradhya
yes proceed
sleep
exit
```

What each command does:

- `model ping`: checks Ollama and confirms whether the configured model is reachable.
- `voice status`: shows the current audio folders and pending voice files.
- `wake`: wakes Aradhya and refreshes `project_tree.txt`.
- `open aradhya`: creates a plan to open the best-matching path.
- `yes proceed`: executes the pending plan.
- `sleep`: clears pending work and puts Aradhya idle.
- `exit`: closes the CLI.

## 4. How To Confirm The Tree File Is Updating

Before running `wake`, check the file timestamp:

```powershell
Get-Item F:\ARADHYA\project_tree.txt | Select-Object LastWriteTime, Length
```

Then run Aradhya and type:

```text
wake
exit
```

Check the timestamp again:

```powershell
Get-Item F:\ARADHYA\project_tree.txt | Select-Object LastWriteTime, Length
```

Where the refresh happens in code:

- `src/aradhya/assistant_core.py`
  `handle_wake()` calls the indexer on wake
- `src/aradhya/assistant_core.py`
  local-data requests refresh again in `handle_transcript()`
- `src/aradhya/assistant_indexer.py`
  `output_path.write_text(...)` is the line that actually rewrites `project_tree.txt`

What to inspect inside `project_tree.txt`:

- top lines include `generated_at=...`
- top lines include `reason=wake` or `reason=local_query`
- the listed roots show what was scanned

## 5. What Aradhya Can Actually Do Right Now

These features are real in the current code:

- Wake and go idle
- Echo transcripts
- Build a plan before acting
- Require explicit confirmation before execution
- Refresh the local tree index
- Dry-run or execute path opens, depending on config
- Find the strongest `.txt`-heavy folder
- Reopen yesterday's active project using project markers
- Open preferred security blogs
- Toggle Debate AI mode
- Check the configured Ollama model
- Send direct prompts to the configured Ollama model with `model ask ...`
- Process dropped voice files through the current folder-based voice workflow

These features are only partially present or still planned:

- True microphone capture
- Automatic Whisper transcription
- Screen reading and UI control
- Google Meet button interaction
- Full Debate AI multi-model reasoning loop
- Automatic heavy-document handoff to external tools
- Full autonomous laptop control

So the answer is:

- Aradhya can do the core features that are implemented in the current CLI and planner.
- Aradhya cannot yet do all long-term product-vision features.

## 6. How Voice Works Right Now

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

Responsible file:

- `src/aradhya/voice_pipeline.py`

## 7. How To Change The Model Later

Open:

- `core/memory/profile.json`

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
- `src/aradhya/model_provider.py` builds the provider from config
- Aradhya code does not hard-code Gemma inside the planner or CLI

## 8. How To Change Behavior

Open:

- `core/memory/preferences.json`

Useful fields:

- `allow_live_execution`
  if `false`, Aradhya only dry-runs actions
  if `true`, it will really open paths and URLs
- `directory_index_path`
  where the tree file is written
- `confirmation_phrases`
  phrases that allow execution
- `security_blog_urls`
  browser targets for the security blogs feature
- `game_library_roots`
  folders Aradhya scans to find recent games
- `directory_index_policy.refresh_on_wake`
  controls wake-triggered tree refresh
- `directory_index_policy.refresh_on_local_query`
  controls query-triggered tree refresh

Open:

- `core/memory/profile.json`

Useful fields:

- `model.model_name`
  which Ollama model Aradhya uses
- `voice.provider`
  `manual_transcript` now, `whisper_command` later
- `voice.whisper_command_template`
  command template for your future Whisper wiring
- `voice.audio_inbox_dir`
  where you drop audio files

## 9. Most Important Code Files

- `src/aradhya/main.py`
  CLI entry point and top-level commands
- `src/aradhya/assistant_core.py`
  wake, idle, confirmation, and planning flow
- `src/aradhya/assistant_indexer.py`
  tree-file generation
- `src/aradhya/assistant_planner.py`
  maps commands to plans
- `src/aradhya/assistant_system_tools.py`
  task heuristics and execution behavior
- `src/aradhya/model_provider.py`
  Ollama provider layer
- `src/aradhya/runtime_profile.py`
  swappable model and voice config loader
- `src/aradhya/voice_pipeline.py`
  audio inbox and transcript handling

## 10. Current Recommended Demo

To see the main pieces working in a controlled way:

1. Start Aradhya
2. Type `model ping`
3. Type `voice status`
4. Type `wake`
5. Open `project_tree.txt` and confirm the top metadata changed
6. Type `find the folder with the highest concentration of .txt files`
7. Type `yes proceed`
8. Type `open aradhya`
9. Type `yes proceed`
10. Type `sleep`

This demo shows:

- model configuration
- voice folder awareness
- wake handling
- tree-file updates
- planning
- confirmation gating
- execution behavior
