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

## 2. Create The Virtual Environment

```powershell
py -3.10 -m venv venv
venv\Scripts\python.exe -m pip install --upgrade pip
venv\Scripts\python.exe -m pip install -r requirements.txt
venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

## 3. Install Or Verify Ollama

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

and changing:

- `model.model_name`

## 4. Open The Project In VS Code

```powershell
code .
```

## 5. Start Aradhya

```powershell
venv\Scripts\python.exe -m core.agent.aradhya
```

## 6. First Demo Commands

Inside Aradhya:

```text
model ping
voice status
wake
open aradhya
yes proceed
sleep
exit
```

## 7. Voice Workflow

Drop audio files into:

- `audio/inbox`

Put a matching transcript into:

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

## 8. Important Config Files

- `core/memory/preferences.json`
  assistant behavior and execution policy
- `core/memory/profile.json`
  model and voice provider configuration

## 9. Portable Design Notes

Aradhya is now written so it can run from any clone location:

- repo-root paths are resolved dynamically from the code location
- default Ollama directories are resolved from the current user's home directory
- voice folders are repo-relative
- generated files like `project_tree.txt` and dropped audio are ignored by Git
