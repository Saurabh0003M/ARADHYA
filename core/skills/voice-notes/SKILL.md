---
name: voice-notes
description: Voice inbox management — process dropped audio files, manage transcripts, and handle push-to-talk recordings.
intents:
  - VOICE_PROCESS
  - VOICE_STATUS
---

You can manage the voice inbox pipeline for the user.

### Capabilities

- **Process audio inbox**: Transcribe audio files dropped into the inbox folder.
- **Check voice status**: Report the current state of the voice pipeline, pending files, and activation status.
- **Archive management**: Processed audio is archived and transcripts are saved for reference.
- **Live activation**: Push-to-talk voice capture routes through the same inbox pipeline.

### Audio Formats

Supported: `.mp3`, `.wav`, `.m4a`, `.flac`, `.ogg`, `.opus`, `.aac`

### Workflow

1. Audio arrives in `audio/inbox/` (dropped manually or captured via push-to-talk).
2. The configured voice provider transcribes the audio.
3. Transcripts are saved to `audio/transcripts/`.
4. Processed audio is archived to `audio/processed/`.
5. If Aradhya is awake, the transcript is routed into the planner.

### Safety Rules

- Voice processing is explicit — the user must trigger it.
- Transcripts are stored locally and never sent to external services unless the user's voice provider requires it.
