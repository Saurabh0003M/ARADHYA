"""ARADHYA Lite — the thin always-on voice loop.

Say the wake word -> hear "Yes sir?" -> speak your request -> Claude
(one persistent Agent SDK session, with the basic-memory brain) answers
-> the reply is spoken aloud while it is still being generated.

Design decisions (from the July 2026 research reports; see the brain notes
in companion/ for sources):
- Ears: RealtimeSTT — wake word (openWakeWord backend) + Silero VAD +
  faster-whisper, CPU-only. Returns text to code instead of typing into a window.
- Mic: sounddevice in WASAPI *shared* mode feeding recorder.feed_audio(),
  because RealtimeSTT's internal PyAudio stream can lock Windows out of the
  mic or die with [Errno -9998] at 16 kHz.
- Brain: ONE persistent ClaudeSDKClient session. A cold `claude -p` per
  utterance costs seconds — the exact mistake that made big-ARADHYA feel slow.
- Mouth: RealtimeTTS EdgeEngine (free Indian-English neural voice; unofficial
  endpoint with a documented history of sudden 403 outages) with automatic
  fallback to the offline Windows SystemEngine.
- Echo guard: mic frames are zeroed while TTS plays, so the assistant cannot
  wake itself by speaking its own name.

Run:  .venv\\Scripts\\python aradhya_lite.py   (see README.md / setup.ps1)
"""

import asyncio
import threading
import winsound
from pathlib import Path

import numpy as np
import sounddevice as sd

from RealtimeSTT import AudioToTextRecorder
from RealtimeTTS import TextToAudioStream, SystemEngine

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    TextBlock,
)

HERE = Path(__file__).resolve().parent
ACK_WAV = HERE / "assets" / "ack.wav"
HEY_ARADHYA_MODEL = HERE / "models" / "hey_aradhya.onnx"

WHISPER_MODEL = "base.en"      # tiny.en if replies feel slow, small.en for accuracy
SAMPLE_RATE = 16000
BLOCK_SIZE = 512               # 32 ms chunks
WAKE_SENSITIVITY = 0.6         # raise toward 0.8 if TV/family speech false-triggers
EDGE_VOICE = "en-IN-NeerjaNeural"

SYSTEM_PROMPT = """\
You are ARADHYA, Saurabh's voice assistant on his Windows PC.
Every reply you write is spoken aloud by TTS, so: 2-5 short conversational
sentences, plain prose only — no markdown, no bullet lists, no code blocks,
no emoji. If a result is long, save it as a note and say where you put it.
Use the basic-memory brain (project 'brain') to remember and recall context
about Saurabh; write journal observations to the journal/ folder when he
shares something worth keeping. If a request sounds destructive or
irreversible, say what you would do and ask him to confirm first.
"""

# Mic frames are replaced with silence while this is set (TTS echo guard).
mic_muted = threading.Event()
recorder: AudioToTextRecorder | None = None


def play_ack() -> None:
    """Instant acknowledgment on wake-word hit — pre-rendered WAV beats any TTS."""
    if ACK_WAV.exists():
        winsound.PlaySound(str(ACK_WAV), winsound.SND_FILENAME | winsound.SND_ASYNC)
    else:
        winsound.MessageBeep()


def mic_callback(indata, frames, time_info, status) -> None:
    if recorder is None:
        return
    if mic_muted.is_set():
        recorder.feed_audio(np.zeros_like(indata).tobytes())
    else:
        recorder.feed_audio(indata.tobytes())


def build_recorder() -> AudioToTextRecorder:
    kwargs = dict(
        model=WHISPER_MODEL,
        language="en",
        use_microphone=False,          # we feed audio ourselves (WASAPI shared mode)
        spinner=False,
        post_speech_silence_duration=0.8,
        wake_word_buffer_duration=0.5,  # drop the wake-word tail so it doesn't corrupt the command
        wake_words_sensitivity=WAKE_SENSITIVITY,
        wakeword_backend="openwakeword",
        on_wakeword_detected=play_ack,
    )
    if HEY_ARADHYA_MODEL.exists():
        kwargs["openwakeword_model_paths"] = str(HEY_ARADHYA_MODEL)
        # wake_words must still be passed or openWakeWord init is skipped
        # entirely (RealtimeSTT issue #266) and detection dies with an
        # AttributeError on owwModel.
        kwargs["wake_words"] = "hey aradhya"
        print(f"[wake] custom model: {HEY_ARADHYA_MODEL.name}")
    else:
        # openWakeWord ships a pre-trained "hey jarvis" — day-one wake word
        # until models/hey_aradhya.onnx is trained (see README).
        kwargs["wake_words"] = "hey jarvis"
        print("[wake] no custom model yet — say 'Hey Jarvis' (train hey_aradhya.onnx later)")
    return AudioToTextRecorder(**kwargs)


def make_tts() -> TextToAudioStream:
    try:
        from RealtimeTTS import EdgeEngine

        return TextToAudioStream(EdgeEngine(voice=EDGE_VOICE))
    except Exception as exc:  # missing extra, no network, endpoint 403, ...
        print(f"[tts] Edge voice unavailable ({exc}); using offline Windows voice")
        return TextToAudioStream(SystemEngine())


def speak_offline(text: str) -> None:
    """Last-resort voice path that cannot fail on network."""
    try:
        stream = TextToAudioStream(SystemEngine())
        stream.feed(text)
        mic_muted.set()
        stream.play()
    finally:
        mic_muted.clear()


def listen_loop(loop: asyncio.AbstractEventLoop, queue: asyncio.Queue) -> None:
    """Blocking wake-word -> transcript loop, running in its own thread."""
    while True:
        text = recorder.text()
        if text and text.strip():
            asyncio.run_coroutine_threadsafe(queue.put(text.strip()), loop)


async def ask_and_speak(client: ClaudeSDKClient, tts: TextToAudioStream, text: str) -> str:
    await client.query(text)
    parts: list[str] = []
    async for msg in client.receive_response():
        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, TextBlock) and block.text.strip():
                    parts.append(block.text)
                    mic_muted.set()
                    tts.feed(block.text)
                    if not tts.is_playing():
                        tts.play_async()
    while tts.is_playing():
        await asyncio.sleep(0.2)
    mic_muted.clear()
    return "".join(parts)


def build_options() -> ClaudeAgentOptions:
    kwargs = dict(
        cwd=str(HERE.parent),
        system_prompt=SYSTEM_PROMPT,
        permission_mode="acceptEdits",
        # Deliberately no "Bash": a mis-heard voice command must not run shell.
        # Loosen consciously (see README) once the loop has earned trust.
        allowed_tools=["Read", "Glob", "Grep", "Write", "Edit", "WebSearch", "mcp__basic-memory"],
        setting_sources=["user", "project"],  # load user MCP config -> basic-memory brain
    )
    try:
        return ClaudeAgentOptions(**kwargs)
    except TypeError:  # older SDK without setting_sources
        kwargs.pop("setting_sources")
        return ClaudeAgentOptions(**kwargs)


async def main() -> None:
    global recorder
    print("ARADHYA Lite starting (Ctrl+C to stop)…")
    recorder = build_recorder()
    tts = make_tts()

    loop = asyncio.get_running_loop()
    heard: asyncio.Queue[str] = asyncio.Queue()
    threading.Thread(target=listen_loop, args=(loop, heard), daemon=True).start()

    mic = sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="int16",
        blocksize=BLOCK_SIZE,
        callback=mic_callback,
    )
    mic.start()
    print("[mic] listening (WASAPI shared mode — other apps keep the mic too)")

    async with ClaudeSDKClient(options=build_options()) as client:
        print("[brain] persistent Claude session open — waiting for the wake word.\n")
        while True:
            text = await heard.get()
            print(f"\n[you] {text}")
            try:
                reply = await ask_and_speak(client, tts, text)
                print(f"[aradhya] {reply}\n")
            except Exception as exc:
                print(f"[error] {exc}")
                mic_muted.clear()
                tts = make_tts()  # engine may be wedged (e.g. Edge 403) — rebuild
                speak_offline("Sorry sir, something broke. Please check the console.")


if __name__ == "__main__":
    # Required: RealtimeSTT uses multiprocessing; on Windows the spawn start
    # method re-imports this module and would fork-bomb without the guard.
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nARADHYA Lite stopped.")
