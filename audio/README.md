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

## Whisper Later

When you install or choose a Whisper command workflow, update `core/memory/profile.json`:

- change `"provider"` from `"manual_transcript"` to `"whisper_command"`
- set `"whisper_command_template"`

The command template can use:

- `{audio_path}`
- `{transcript_path}`

If the command writes transcript text to `{transcript_path}`, Aradhya will pick it up automatically.
