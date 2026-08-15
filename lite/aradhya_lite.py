"""ARADHYA Lite — the thin always-on voice loop.

TWO ways to start talking (both give you "Yes sir?" then listen):
  1. HOTKEY  — press Ctrl+Alt+A (like your Wispr Ctrl+Win habit). Reliable, instant.
  2. WAKE WORD — say "Hey Jarvis" (until the custom "Hey Aradhya" model is trained).

Then: you speak -> Claude (one persistent Agent SDK session with your
basic-memory brain) answers -> the reply is spoken aloud. A small floating
pill in the bottom-right corner shows the current state at all times.

Design notes (see the brain notes in companion/ for the research behind this):
- RealtimeSTT owns the microphone directly (use_microphone=True). An earlier
  version fed audio manually and the wake word never fired — letting the library
  own the mic is the reliable path, and it coexists with Wispr Flow via WASAPI
  shared mode.
- The hotkey calls recorder.wakeup(), which triggers a listen exactly as if the
  wake word had been spoken — so one recorder serves both triggers.
- Brain = ONE persistent ClaudeSDKClient (a cold `claude -p` per turn costs
  seconds; that is what made big-ARADHYA feel slow).
- Voice = Edge en-IN-Neerja (natural Indian English) if available, else the
  offline Windows voice. Falls back automatically, so you always hear a reply.
- The loop is serialized: it does not listen while thinking or speaking, so it
  can never trigger on its own voice.

Run:  .venv\\Scripts\\python aradhya_lite.py
"""

import asyncio
import queue
import threading
import winsound
from pathlib import Path

from RealtimeSTT import AudioToTextRecorder
from RealtimeTTS import TextToAudioStream, SystemEngine

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    TextBlock,
)

try:
    import keyboard  # global hotkey
except Exception:  # pragma: no cover
    keyboard = None

# ── Settings ──────────────────────────────────────────────────────────────
HOTKEY = "ctrl+alt+a"          # press to start listening (change to taste)
ENABLE_SPOKEN_WAKEWORD = True  # also allow "Hey Jarvis" / "Hey Aradhya"
WHISPER_MODEL = "base.en"      # tiny.en = faster, small.en = more accurate
WAKE_SENSITIVITY = 0.6         # wake-word match; raise toward 0.8 if it false-triggers
# Voice-activity detection for your COMMAND (after the wake word / hotkey).
# webrtc: 0 = most sensitive … 3 = least (the library default 3 was deaf to speech).
# silero: 0 = least sensitive … 1 = most.
WEBRTC_SENSITIVITY = 1
SILERO_SENSITIVITY = 0.6
WAKE_WORD_TIMEOUT = 8          # seconds after wake to start talking before it re-arms
USE_EDGE_VOICE = True          # Indian-English neural voice (needs internet; falls back if it fails)
EDGE_VOICE = "en-IN-NeerjaNeural"
SHOW_OVERLAY = True            # floating status pill

HERE = Path(__file__).resolve().parent
ACK_WAV = HERE / "assets" / "ack.wav"
HEY_ARADHYA_MODEL = HERE / "models" / "hey_aradhya.onnx"

# ── ARADHYA's own effectors, over MCP ────────────────────────────────────────
# Decision memo 2026-08-07 §1: the effectors ship as an MCP server behind the
# ToolRegistry policy gate, and this voice loop is one client of it. The server
# runs in the MAIN venv (F:\ARADHYA\venv) — that is where uiautomation and
# playwright live; lite's own .venv has the audio stack and nothing else.
MAIN_VENV_PYTHON = HERE.parent / "venv" / "Scripts" / "python.exe"
ENABLE_EFFECTORS = True

# Confirmation for gated tools (invoke_control, set_control_text, browser_click…).
# A stdio server cannot prompt: its stdin IS the protocol stream. So:
#   False → gated tools are DENIED. Read-only ones still work. This is the default.
#   True  → this session is unlocked, exactly like the floating icon's "I"
#           control: no persisted grant, lapses when the process exits.
# The 10-command acceptance run needs this True, because "click Y" is gated.
INTERACTION_UNLOCKED = False

SYSTEM_PROMPT = """\
You are ARADHYA, Saurabh's voice assistant on his Windows PC.
Every reply you write is spoken aloud by TTS, so: 2-5 short conversational
sentences, plain prose only — no markdown, no bullet lists, no code blocks,
no emoji. If a result is long, save it as a note and say where you put it.
Use the basic-memory brain (project 'brain') to remember and recall context
about Saurabh; write journal observations to the journal/ folder when he
shares something worth keeping. If a request sounds destructive or
irreversible, say what you would do and ask him to confirm first.

You can act on this machine through the `aradhya` MCP server. Use it rather
than describing what you would do:
- list_windows to see what is open; focus_window to bring one forward.
- list_window_controls to read a window's controls before touching anything.
  Controls are marked [invokable] (invoke_control can press it) and [editable]
  (set_control_text can type into it). Never guess a control name — list first.
- browser_open then browser_navigate to open a page; browser_read returns the
  page as an element map with roles, names and ids.
Say what you found in plain speech: he may be listening with the monitor off,
so "Notepad has a File menu, an Edit menu and a text area" beats reading a list.
If a tool is denied, say so plainly and say why — never report a denied action
as done.

Human-only, always, no exceptions: never type or submit a CAPTCHA, a one-time
password, a password, or the final submit of a form. Read the screen, tell him
what it says, and let him do it.
"""


# Only these are copied into the MCP server's environment. Passing the whole
# environment would hand every API key on this machine to a subprocess that
# does not need one — and this dict ends up in logs and debug output, so a
# blanket copy is a credential leak waiting for someone to print it.
_ENV_PASSTHROUGH = (
    "PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP",
    "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "APPDATA", "LOCALAPPDATA",
    "PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMDATA",
    "ARADHYA_HOME",
)


def effector_mcp_config() -> dict:
    """The `aradhya` MCP server config passed to the Claude Agent SDK."""
    import os

    env = {
        name: os.environ[name] for name in _ENV_PASSTHROUGH if name in os.environ
    }
    env["PYTHONUTF8"] = "1"
    env["ARADHYA_MCP_GATE"] = "unlocked" if INTERACTION_UNLOCKED else "deny"
    return {
        "type": "stdio",
        "command": str(MAIN_VENV_PYTHON),
        "args": ["-m", "src.aradhya.mcp_server"],
        "cwd": str(HERE.parent),
        "env": env,
    }


# ── Floating status pill ────────────────────────────────────────────────────
class Overlay:
    """A tiny always-on-top window showing the current state. Fully optional:
    any failure degrades to console-only without touching the voice loop."""

    COLORS = {
        "idle": ("ARADHYA  ·  ready", "#2b2b2b"),
        "listening": ("🎤  Listening…", "#1a7f37"),
        "thinking": ("💭  Thinking…", "#b7791f"),
        "speaking": ("🗣  Speaking…", "#1f6feb"),
    }

    def __init__(self):
        self.root = None
        self.label = None
        self._pending = "idle"
        if not SHOW_OVERLAY:
            return
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            import tkinter as tk

            self.root = tk.Tk()
            self.root.overrideredirect(True)
            self.root.attributes("-topmost", True)
            try:
                self.root.attributes("-alpha", 0.92)
            except Exception:
                pass
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            w, h = 230, 56
            self.root.geometry(f"{w}x{h}+{sw - w - 24}+{sh - h - 80}")
            self.label = tk.Label(
                self.root, font=("Segoe UI Emoji", 13, "bold"), fg="white",
                bg="#2b2b2b", anchor="center",
            )
            self.label.pack(fill="both", expand=True)
            self._render()
            self.root.mainloop()
        except Exception as exc:  # pragma: no cover
            print(f"[overlay] disabled ({exc})")
            self.root = None

    def _render(self):
        text, color = self.COLORS.get(self._pending, self.COLORS["idle"])
        if self.label is not None:
            self.label.config(text=text, bg=color)
            self.root.config(bg=color)

    def set(self, state: str):
        self._pending = state
        if self.root is not None:
            try:
                self.root.after(0, self._render)
            except Exception:
                pass


# ── Voice out (Edge → Windows fallback) ──────────────────────────────────────
class Voice:
    def __init__(self):
        self.system = SystemEngine()
        self.edge = None
        self._edge_dead = False
        if USE_EDGE_VOICE:
            try:
                from RealtimeTTS import EdgeEngine

                eng = EdgeEngine()
                eng.set_voice(EDGE_VOICE)
                self.edge = eng
            except Exception as exc:
                print(f"[tts] Edge voice unavailable ({exc}); using offline Windows voice")

    def say(self, text: str) -> None:
        """Blocking: speak the whole reply, preferring Edge, falling back once."""
        if self.edge is not None and not self._edge_dead:
            try:
                stream = TextToAudioStream(self.edge)
                stream.feed(text)
                stream.play()
                return
            except Exception as exc:
                print(f"[tts] Edge playback failed ({exc}); switching to Windows voice for this session")
                self._edge_dead = True
        stream = TextToAudioStream(self.system)
        stream.feed(text)
        stream.play()


def play_ack() -> None:
    if ACK_WAV.exists():
        winsound.PlaySound(str(ACK_WAV), winsound.SND_FILENAME | winsound.SND_ASYNC)
    else:
        winsound.MessageBeep()


# ── Recorder ─────────────────────────────────────────────────────────────────
def build_recorder(overlay: Overlay) -> AudioToTextRecorder:
    def on_wake():
        play_ack()
        overlay.set("listening")
        print("[wake] woke up — go ahead, I'm listening…")

    kwargs = dict(
        model=WHISPER_MODEL,
        language="en",
        use_microphone=True,           # let RealtimeSTT own the mic (reliable path)
        spinner=False,
        post_speech_silence_duration=0.8,
        wake_word_buffer_duration=0.2,  # drop the wake-word tail so it doesn't corrupt the command
        silero_use_onnx=True,           # avoid the interactive torch.hub trust prompt
        # Command capture: make VAD actually sensitive to speech (defaults were deaf).
        webrtc_sensitivity=WEBRTC_SENSITIVITY,
        silero_sensitivity=SILERO_SENSITIVITY,
        min_length_of_recording=0.3,
        on_wakeword_detected=on_wake,
        # Stage logging so any stall is visible in the console.
        on_recording_start=lambda: print("[rec] recording your command…"),
        on_recording_stop=lambda: print("[rec] got it, transcribing…"),
        on_wakeword_timeout=lambda: print("[wake] (no speech heard — say it again)"),
    )
    if ENABLE_SPOKEN_WAKEWORD:
        kwargs["wake_word_timeout"] = WAKE_WORD_TIMEOUT
    if ENABLE_SPOKEN_WAKEWORD:
        kwargs["wakeword_backend"] = "openwakeword"
        kwargs["wake_words_sensitivity"] = WAKE_SENSITIVITY
        if HEY_ARADHYA_MODEL.exists():
            kwargs["openwakeword_model_paths"] = str(HEY_ARADHYA_MODEL)
            kwargs["wake_words"] = "hey aradhya"  # must be set even with a custom path (RealtimeSTT #266)
            print(f"[wake] custom model: {HEY_ARADHYA_MODEL.name} — say 'Hey Aradhya'")
        else:
            kwargs["wake_words"] = "hey jarvis"
            print("[wake] say 'Hey Jarvis' (custom 'Hey Aradhya' model not trained yet)")
    return AudioToTextRecorder(**kwargs)


# ── Brain ────────────────────────────────────────────────────────────────────
def build_options() -> ClaudeAgentOptions:
    # No "Bash": a mis-heard voice command must not run shell. Loosen consciously.
    allowed = ["Read", "Glob", "Grep", "Write", "Edit", "WebSearch", "mcp__basic-memory"]
    kwargs = dict(
        cwd=str(HERE.parent),
        system_prompt=SYSTEM_PROMPT,
        permission_mode="acceptEdits",
        allowed_tools=allowed,
        setting_sources=["user", "project"],  # load user MCP config -> basic-memory brain
    )
    if ENABLE_EFFECTORS:
        if not MAIN_VENV_PYTHON.exists():
            print(f"[effectors] disabled — no interpreter at {MAIN_VENV_PYTHON}")
        else:
            kwargs["mcp_servers"] = {"aradhya": effector_mcp_config()}
            allowed.append("mcp__aradhya")
            state = "UNLOCKED" if INTERACTION_UNLOCKED else "read-only (gated tools denied)"
            print(f"[effectors] aradhya MCP server enabled — {state}")
    try:
        return ClaudeAgentOptions(**kwargs)
    except TypeError:
        kwargs.pop("setting_sources")
        return ClaudeAgentOptions(**kwargs)


async def ask(client: ClaudeSDKClient, text: str) -> str:
    await client.query(text)
    parts: list[str] = []
    async for msg in client.receive_response():
        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, TextBlock) and block.text:
                    parts.append(block.text)
    return "".join(parts).strip()


# ── Main ─────────────────────────────────────────────────────────────────────
async def main() -> None:
    print("ARADHYA Lite starting (Ctrl+C to stop)…")
    overlay = Overlay()
    # Build Voice in a worker thread: EdgeEngine.set_voice() calls asyncio.run()
    # internally, which is illegal from inside our running event loop.
    voice = await asyncio.to_thread(Voice)
    recorder = build_recorder(overlay)

    text_q: queue.Queue[str] = queue.Queue()
    done = threading.Event()
    awaiting = threading.Event()  # True only while blocked in recorder.text()

    def on_hotkey():
        if not awaiting.is_set():
            return  # busy thinking/speaking — ignore the press
        play_ack()
        overlay.set("listening")
        print(f"[hotkey] {HOTKEY} → listening…")
        recorder.wakeup()

    hotkey_ok = False
    if keyboard is not None:
        try:
            keyboard.add_hotkey(HOTKEY, on_hotkey)
            hotkey_ok = True
        except Exception as exc:
            print(f"[hotkey] could not register {HOTKEY}: {exc}")
    else:
        print("[hotkey] 'keyboard' package not installed — hotkey disabled")

    def listen_loop():
        while True:
            overlay.set("idle")
            awaiting.set()
            try:
                text = recorder.text()
            except Exception as exc:
                print(f"[listen] {exc}")
                awaiting.clear()
                continue
            awaiting.clear()
            if not text or not text.strip():
                print(f"[listen] (empty transcription: {text!r})")
                continue
            done.clear()
            text_q.put(text.strip())
            done.wait()  # wait until the reply has been spoken before listening again

    threading.Thread(target=listen_loop, daemon=True).start()

    banner = ["", "  ┌─ ARADHYA Lite is live ─────────────────────────────"]
    if hotkey_ok:
        banner.append(f"  │  Press {HOTKEY.upper()} to talk")
    if ENABLE_SPOKEN_WAKEWORD:
        wake = "Hey Aradhya" if HEY_ARADHYA_MODEL.exists() else "Hey Jarvis"
        banner.append(f"  │  …or say \"{wake}\"")
    banner += ["  │  You'll hear \"Yes sir?\" — then just speak.",
               "  └────────────────────────────────────────────────────", ""]
    print("\n".join(banner))

    async with ClaudeSDKClient(options=build_options()) as client:
        while True:
            text = await asyncio.to_thread(text_q.get)
            print(f"\n[you] {text}")
            overlay.set("thinking")
            try:
                reply = await ask(client, text)
            except Exception as exc:
                reply = "Sorry sir, something went wrong. Please check the console."
                print(f"[error] {exc}")
            print(f"[aradhya] {reply}\n")
            if reply:
                overlay.set("speaking")
                await asyncio.to_thread(voice.say, reply)
            overlay.set("idle")
            done.set()  # release the listener for the next turn


if __name__ == "__main__":
    # RealtimeSTT uses multiprocessing; on Windows the spawn start method
    # re-imports this module and would fork-bomb without this guard.
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nARADHYA Lite stopped.")
