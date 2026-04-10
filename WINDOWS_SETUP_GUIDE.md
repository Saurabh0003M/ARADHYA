# Aradhya Setup Guide - Windows

This guide is written for a fresh Windows machine. It does not assume a specific drive letter or user path.

## Requirements

- Windows 10 or Windows 11
- Python 3.10 or newer
- Git
- VS Code
- Ollama installed locally

## 1. Clone The Project

```powershell
git clone <your-github-url> aradhya
cd aradhya
```

## 2. Recommended First Run

For most Windows machines, use the bootstrap script first:

```powershell
scripts\first_run.bat
```

What it does:

- finds a usable Python launcher on the machine
- checks that the version is at least Python 3.10
- creates or repairs the repo-local `venv`
- installs `requirements.txt` and `requirements-dev.txt`
- runs `scripts\doctor.bat` so the remaining Ollama and model steps are obvious

The older `scripts\setup.bat` entrypoint still works, but it now delegates to `scripts\first_run.bat`.

## 3. Manual Virtual Environment Setup

```powershell
py -3.10 -m venv venv
venv\Scripts\python.exe -m pip install --upgrade pip
venv\Scripts\python.exe -m pip install -r requirements.txt
venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Optional real local file transcription:

```powershell
venv\Scripts\python.exe -m pip install -r requirements-voice.txt
```

Optional live microphone activation:

```powershell
venv\Scripts\python.exe -m pip install -r requirements-voice-activation.txt
```

If the local `venv` points at a missing Python installation, recreate it instead of reusing it:

```powershell
Remove-Item -Recurse -Force .\venv
py -3.10 -m venv venv
venv\Scripts\python.exe -m pip install --upgrade pip
venv\Scripts\python.exe -m pip install -r requirements.txt
venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

## 4. Verify The Machine State

Run:

```powershell
scripts\doctor.bat
```

The doctor script checks:

- Python availability on `PATH`
- Python version suitability
- whether `venv` exists and is healthy
- whether core dependencies are installed
- whether `requirements.txt` or `requirements-dev.txt` changed after the last recorded install
- whether Ollama is available and whether the configured model is installed

## 5. Install Or Verify Ollama

Confirm Ollama is available:

```powershell
ollama list
```

If you want to use the default engine:

```powershell
ollama pull gemma4:e4b
```

You can switch to another Ollama model later by editing:

- `core/memory/profile.json`
- `core/memory/profile.local.json`

and changing:

- `model.model_name`

## 6. Open The Project In VS Code

```powershell
code .
```

## 7. Start Aradhya

```powershell
venv\Scripts\python.exe -m core.agent.aradhya
```

## 8. First Demo Commands

Inside Aradhya:

```text
cache validate
model ping
voice status
wake
open aradhya
yes proceed
sleep
exit
```

## 9. Voice Workflow

Drop audio files into:

- `audio/inbox`

In the default `manual_transcript` mode, put a matching transcript into:

- `audio/manual_transcripts`

Then run:

```text
voice process
```

Supported audio formats:

- `.mp3`
- `.wav`
- `.m4a`
- `.flac`
- `.ogg`
- `.opus`
- `.aac`

If you install `requirements-voice.txt`, you can switch `core/memory/profile.json` to:

- `voice.provider = "faster_whisper"`

Then Aradhya will transcribe dropped files locally without needing the matching `.txt` helper file.

If you also want live microphone activation:

- keep `voice.provider` as `faster_whisper` or `whisper_command`
- review the `voice_activation` section in `core/memory/profile.json`
- start Aradhya and run `voice activate`

## 10. Important Config Files

- `core/memory/preferences.json`
  assistant behavior and execution policy
- `core/memory/profile.json`
  model and voice provider configuration

Useful voice fields in `profile.json`:

- `voice.provider`
- `voice.faster_whisper_model_size`
- `voice.faster_whisper_device`
- `voice.faster_whisper_compute_type`
- `voice.language`
- `voice_activation.hotkey_modifiers`
- `voice_activation.hotkey_key`
- `voice_activation.silence_duration`
- `voice_activation.silence_threshold`

Aradhya merges `profile.local.json` over `profile.json`, and the interactive model bootstrap writes there so local model choices do not modify shared repo defaults.

## 11. Portable Design Notes

Aradhya is now written so it can run from any clone location:

- repo-root paths are resolved dynamically from the code location
- default Ollama directories are resolved from the current user's home directory
- voice folders are repo-relative
- generated files like `project_tree.txt` and dropped audio are ignored by Git
