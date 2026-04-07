# Voice Workflow

Aradhya now uses a folder-based voice pipeline so you have a clear place to drop audio.

## Folders

- `audio/inbox`: drop raw voice files here such as `.mp3`, `.wav`, `.m4a`, `.flac`, `.ogg`, `.opus`, or `.aac`
- `audio/processed`: Aradhya moves handled audio files here
- `audio/transcripts`: final transcript text files land here
- `audio/manual_transcripts`: optional fallback folder for matching `.txt` transcripts

## Current Default Flow

The default voice provider is `manual_transcript`.

1. Drop an audio file into `audio/inbox`
2. Create a matching text file in `audio/manual_transcripts`
3. Example:
   `meeting_note.mp3` in `audio/inbox`
   `meeting_note.txt` in `audio/manual_transcripts`
4. Run `voice process` in the CLI

Aradhya will move the audio into `audio/processed`, save the final transcript in `audio/transcripts`, and if Aradhya is awake it will immediately route that transcript into the assistant planner.

## Faster-Whisper File Transcription

If you want real local transcription from dropped audio files:

1. Install the optional dependencies:
   `venv\Scripts\python.exe -m pip install -r requirements-voice.txt`
2. Update `core/memory/profile.json`
3. Change `"provider"` from `"manual_transcript"` to `"faster_whisper"`
4. Optionally tune:
   - `"faster_whisper_model_size"`
   - `"faster_whisper_device"`
   - `"faster_whisper_compute_type"`
   - `"language"`

In `faster_whisper` mode, you only drop the audio file into `audio/inbox`, then run `voice process`. Aradhya will generate the transcript locally, save it in `audio/transcripts`, and archive the handled audio.

## Live Microphone Activation

Aradhya can also feed microphone captures into the same inbox pipeline.

1. Install `requirements-voice-activation.txt`
2. Set `voice.provider` to `faster_whisper` or `whisper_command`
3. Start Aradhya and run `voice activate`
4. Press the configured hotkey, speak, and let Aradhya transcribe the saved capture

This path still archives the handled audio and writes the transcript into the same folders as dropped files, so it stays easy to inspect and debug.

## Whisper Command Alternative

When you install or choose a Whisper command workflow, update `core/memory/profile.json`:

- change `"provider"` from `"manual_transcript"` to `"whisper_command"`
- set `"whisper_command_template"`

The command template can use:

- `{audio_path}`
- `{transcript_path}`

If the command writes transcript text to `{transcript_path}`, Aradhya will pick it up automatically.
