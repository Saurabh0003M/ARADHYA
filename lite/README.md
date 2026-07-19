# ARADHYA Lite

The thin, always-on voice loop: **"Hey Aradhya" → "Yes sir?" → speak → Claude acts → spoken reply.**
Ears and mouth are local; the brain is one persistent Claude session with the
basic-memory knowledge base. This is the modular restart of ARADHYA — start
small, prove the loop, fold it back into the main product.

## Quick start

```powershell
cd F:\ARADHYA\lite
powershell -NoProfile -ExecutionPolicy Bypass -File setup.ps1   # venv + deps + ack.wav
.venv\Scripts\python aradhya_lite.py
```

Then say **"Hey Jarvis"** (day-one wake word, pre-trained) — you'll hear
*"Yes sir?"* — speak your request, pause, and the reply is spoken back.

Requirements: a mic, Claude Code logged in with your Claude.ai account, and
(optional, for the Indian-English neural voice) `winget install mpv`.
Without mpv or without internet the loop automatically uses the offline
Windows voice instead.

## Getting the real "Hey Aradhya" wake word

Picovoice's free tier died 2026-06-30, so we train our own model with
**livekit-wakeword** (Apache-2.0, conv-attention, ~100x fewer false triggers
than plain openWakeWord, and its VoxCPM voice-design prompts synthesize
*Indian English accented* training data). Full recipe with commands is in
[hey_aradhya.yaml](hey_aradhya.yaml). Drop the result at
`models/hey_aradhya.onnx` and restart — the script picks it up automatically.
Heads-up: `livekit-wakeword setup` downloads several GB of noise datasets and
training takes ~1–2 h on this CPU.

## Tuning knobs (top of `aradhya_lite.py`)

| Constant | Default | When to change |
|---|---|---|
| `WHISPER_MODEL` | `base.en` | `tiny.en` if transcription feels slow; `small.en` for accuracy |
| `WAKE_SENSITIVITY` | 0.6 | move toward 0.8 if TV/family speech false-triggers |
| `EDGE_VOICE` | `en-IN-NeerjaNeural` | any `edge-tts --list-voices` name |
| `allowed_tools` | read/write + brain, **no Bash** | add `"Bash"` only once you trust the loop — a mis-heard command must not run shell |

## Known failure modes (from the research, already mitigated)

- **Self-wake echo**: mic is muted (zero-fed) while TTS plays.
- **Chopped commands**: `wake_word_buffer_duration=0.5` discards the wake-word tail.
- **Silent-night hallucination**: Silero VAD gates the wake engine.
- **Edge-TTS 403 outages**: documented, recurring, unfixable from our side —
  the script auto-falls back to the offline Windows voice; consider Piper
  (`hi_IN` voices exist) as the quality offline upgrade.
- **Windows fork-bomb**: the `if __name__ == "__main__"` guard is mandatory
  (RealtimeSTT uses multiprocessing with spawn).
- **RealtimeSTT #266**: `wake_words` must be passed even when using
  `openwakeword_model_paths`, or wake-word init is silently skipped.

## Roadmap

1. Piper offline voice upgrade (`hi_IN`/`en` medium voices, ~100–250 ms).
2. Nightly "sleep-time reflection" job: journal ingestion → brain observations
   → link audit (memory-defrag pattern).
3. Barge-in (interrupt the reply by speaking).
4. Phone path: RichardAtCT/claude-code-telegram + sendVoice replies.
5. Fold proven modules back into ARADHYA proper as toggleable features.
