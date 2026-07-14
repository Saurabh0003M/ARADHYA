# ARADHYA Demo Video Script — OSDHack 2026

> **Duration target:** ~2.5 minutes (2:00–3:00)
> **Theme:** "100% On-Device AI · Local Ollama · No Cloud · Privacy-First"
> **Model:** `llama3.2:3b` via Ollama (runs entirely on this machine)

---

## Pre-recording checklist

- [ ] Ollama running (`ollama serve` or system tray)
- [ ] `llama3.2:3b` pulled (`ollama list` to confirm)
- [ ] Terminal: Windows Terminal or PowerShell, dark theme, font 14pt+
- [ ] Terminal window ~120 columns wide (for clean banner rendering)
- [ ] No sensitive files/tabs visible on screen
- [ ] Close other apps to maximise CPU for faster inference
- [ ] Delete or rename `core/sessions/` to start with a clean conversation

---

## Shot-by-shot script

### Beat 1 · Boot + Banner (0:00–0:20)

**Caption/voiceover:**
> "ARADHYA is a fully on-device AI operating assistant.
> Everything runs locally — your data never leaves this machine."

**Action:**
```
.\arise.bat
```

**Expected on screen:**
```
┌─────────────────────────────────────────────────────────────────────────────┐
│        _    ____      _    ____  _   ___   __ _                             │
│       / \  |  _ \    / \  |  _ \| | | \ \ / // \                            │
│      / _ \ | |_) |  / _ \ | | | | |_| |\ V // _ \                           │
│     / ___ \|  _ <  / ___ \| |_| |  _  | | |/ ___ \                          │
│    /_/   \_\_| \_\/_/   \_\____/|_| |_| |_/_/   \_\                         │
│                                                                             │
│           Operating Intelligence  v1.1                                      │
└─────────────────────────────────────────────────────────────────────────────┘

   Model    llama3.2:3b
   Voice    ...\audio\inbox
   Skills   12 active / 12 loaded
   Log      ...\core\logs\aradhya.log

  Type /help for commands  |  Just type naturally to talk to Aradhya
```

**Notes:** Hold on this screen for ~3 seconds. The banner confirms the model
is local (`llama3.2:3b`) and skills are loaded.

---

### Beat 2 · Natural-language chat reply (0:20–1:00)

**Caption/voiceover:**
> "Ask Aradhya anything in natural language — it responds using the
> local LLM running on your own CPU, with zero cloud calls."

**Action — type:**
```
what can you help me with?
```

**Expected on screen:**
The prompt shows `You >` with your question. After ~10–20 seconds of
streaming, Aradhya's reply appears with the `Aradhya >` prefix, listing
its capabilities (file management, system info, web search, scheduling, etc.).

**Editing note:** If the LLM takes longer than ~15s, speed up the waiting
portion in post (2× or a jump-cut). The key moment is the reply
appearing and **staying visible** on screen — this proves the on-device
model is working end-to-end.

---

### Beat 3 · Security Gate (1:00–1:45)

**Caption/voiceover:**
> "ARADHYA has a built-in Safety Confirmation Gate. Any dangerous
> operation — file writes, shell commands, system changes — requires
> explicit user approval before execution. Your machine stays safe."

**Action — type:**
```
create a file called demo.txt with the text hello world
```

**Expected on screen:**
After the planner routes to the agent path (~15–30s), a rich Security Gate
panel appears:

```
┌─ Security Gate ─────────────────────────────────────────────┐
│  Tool:   write_file                                         │
│  Path:   demo.txt                                           │
│  Risk:   Critical                                           │
│                                                             │
│  Content preview:                                           │
│  hello world                                                │
└─────────────────────────────────────────────────────────────┘

  Approve? [y]es / [a]lways / [n]o
```

**Action — type:** `n` (deny it — we don't want to actually create the file)

**Expected:** Aradhya acknowledges the denial and returns to the prompt.

**Editing note:** The agent/tool path takes ~2–4 minutes on CPU because 62
tool schemas are sent. **Speed this up in post** (4–8× or jump-cut to the
gate appearing). The Security Gate panel itself is the money shot — hold on
it for ~5 seconds.

---

### Beat 4 · /status — Local Inference Only (1:45–2:10)

**Caption/voiceover:**
> "The /status dashboard confirms: Dry-run Mode, Local Inference Only.
> No cloud APIs, no data exfiltration — 100% on-device."

**Action — type:**
```
/status
```

**Expected on screen:**
A Rich-styled table:

```
╭─ System Status ─────────────────────────────────────╮
│ [+] State      Awake                                │
│ [~] Safety     Dry-run Mode                         │
│ [ ] Action     None pending                         │
│ [+] Model      llama3.2:3b - Ready                  │
│ [+] Privacy    Local Inference Only                  │
│ [ ] Voice      disabled                              │
│ [~] Skills     12 active / 12 loaded                │
╰─────────────────────────────────────────────────────╯
```

**Notes:** Hold on this for ~3 seconds. The two key lines to highlight
(zoom/annotate in post) are:
- **Safety: Dry-run Mode** — dangerous ops need approval
- **Privacy: Local Inference Only** — no cloud fallback active

---

### Beat 5 · Close (2:10–2:30)

**Caption/voiceover:**
> "ARADHYA — your private, on-device AI operating assistant.
> Open source. Runs on your hardware. Your data stays yours."

**Action — type:**
```
/quit
```

or simply close the terminal.

**End card (overlay in post):**
```
ARADHYA — On-Device AI Operating Assistant
github.com/Saurabh0003M/ARADHYA
License: GPLv3 · OSDHack 2026
```

---

## Timing summary

| Beat | Content                       | Raw time  | Edited time |
|------|-------------------------------|-----------|-------------|
| 1    | Boot + banner                 | ~8s       | ~15s        |
| 2    | Chat reply                    | ~15–25s   | ~25s        |
| 3    | Security Gate                 | ~2–4 min  | ~35s        |
| 4    | /status dashboard             | ~2s       | ~15s        |
| 5    | Close + end card              | ~2s       | ~10s        |
| **Total** |                          |           | **~2:00**   |

---

## Recording tips

1. **Use OBS or ShareX** for screen recording — capture only the terminal window.
2. **Font size 14pt+** so text is readable at 1080p.
3. **Dark terminal theme** (e.g., One Dark, Dracula) for visual contrast.
4. **Type at a natural pace** — don't rush. Deliberate typing looks more professional.
5. **Speed up waits in post** — the tool-call latency (~4 min) is the main
   time sink; cut or speed it up. Keep the Security Gate reveal at 1× speed.
6. **Add captions in post** (not hardcoded) — use a subtitle track or overlay
   so the video is accessible and the key privacy points are reinforced visually.
7. **No audio required** — captions/text overlay work fine for a hackathon demo.
   If you do add voiceover, keep it calm and factual.

---

## Key phrases to emphasise

These should appear as on-screen text/captions at some point during the video:

- **100% On-Device** — all AI inference runs locally via Ollama
- **Privacy-First** — no data leaves your machine
- **Safety Gate** — dangerous operations require explicit human approval
- **12 Skills** — file management, web search, scheduling, system tools, and more
- **Open Source** — GPLv3 licensed, fully auditable
