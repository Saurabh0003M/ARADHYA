# ARADHYA dogfood session guide — 2026-08-09

For Saurabh, to operate ARADHYA by hand, feature by feature, as a human — not by
running big commands. Grades from safe → powerful. After each step, react in the
transcript with a `#` line (e.g. `# this was confusing`), then copy the WHOLE
terminal session — your input, ARADHYA's output, your `#` notes — and paste it back.

**The point is not to succeed. The point is to find where it confuses or fails.**
A step that breaks is a better finding than a step that works. Do not reword things
to make them pass.

---

## Before you start — one speed change

The text agent picks a tool by asking the model, and on gemma4:e4b (9.6 GB) each
turn is minutes on this CPU. Switch to the small model first:

1. Launch ARADHYA (below), then type `/model` — see which model it's on.
2. If it's `gemma4:e4b` or `gemma4:e2b`, switch to `llama3.2:3b`:
   - try `/setup` (re-runs the model picker), OR
   - edit `core/config/profile.local.json` and set the model name to
     `llama3.2:3b`, then restart.
3. If neither way to switch is obvious → **that is finding #1. Write it down and
   move on** — I'll fix the model-switch UX.

Do NOT run a standalone `ollama run` in another window at the same time — the two
fight over one model in 15.5 GB and both crawl.

---

## Launch

Double-click `arise.bat` (or run it from a terminal in `F:\ARADHYA`). It checks
the venv, then starts the CLI. You should see a banner: model name, voice inbox,
skills count, log path.

- `# ` If the banner is confusing, or it crashes, paste the whole thing. That is
  finding #2 and it's the most important one — first impressions are the product.

---

## Part 1 — the map (safe, read-only, instant)

Type these one at a time. None of them change anything.

| Type this | What it should do | React on |
|---|---|---|
| `/help` | List what you can do | Could you tell what ARADHYA can actually *do* from this? |
| `/status` | Show current state (awake/asleep, model) | Did it make sense? |
| `/skills` | List loaded skills | Do you know what any of them are for? |
| `/profile` | Show your stored profile | Is anything wrong or missing? |
| `/audit` | Show the log of actions taken | Empty now — you'll check it again later |

`# ` after each: was the output readable? Would it make sense if *spoken* aloud
(the "monitor off" test)?

---

## Part 2 — can it SEE? (read-only, the core of your guide-mode idea)

Open **Notepad** and **Calculator** first (real windows for it to read). Then, in
ARADHYA, type as plain English — not commands:

1. `what windows are open right now?`
   - Should call `list_windows` and name Notepad, Calculator, your browser, etc.
   - `# ` Did it list the real windows, or make some up? Did it call the tool at
     all, or just chat?
2. `read the Notepad window and tell me what I can click`
   - Should call `list_window_controls` and describe Notepad's controls.
   - `# ` Was the description right? This is exactly what guide-mode needs — if it
     can *describe* what's clickable, it's one step from *pointing* at it.
3. `open the browser and read what's on example.com`
   - `browser_open` is gated → it will **ask you to confirm (y/n)**. Say yes.
   - Then `browser_read` should return what's on the page.
   - `# ` Did the confirmation prompt make sense? Did the page read correctly?

This part is the honest test of your dot-on-the-screen idea: everything guide-mode
needs is "can it reliably say *where* the clickable things are." Note every time
it names the wrong control or misses one — that's the accuracy budget for pointing.

---

## Part 3 — can it ACT? (gated — you approve each one)

Every action here will prompt you y/n before it happens. That prompt IS the safety
feature — pay attention to whether it tells you enough to decide.

1. `type "hello from Saurabh" into Notepad`
   - Prompts to confirm → yes → watch Notepad.
   - `# ` Did the text land? Did the prompt tell you what it was about to do?
2. `bring Calculator to the front`
   - `# ` Did the right window come forward?
3. `press the 7 button in Calculator`
   - `# ` Did it press 7? Or the wrong control?
4. Now type `/audit` again.
   - `# ` Does the log show what you just did? This is the "receipt" — for portal
     and client work later, this log is your proof of what happened. Is it
     readable?

---

## Part 4 — voice (only after text works)

This is the `lite/` loop — the real speak→act path. From `F:\ARADHYA\lite`:

```
.venv\Scripts\python.exe aradhya_lite.py
```

- Trigger by the hotkey (Ctrl+Alt+A) or the wake word, then speak the SAME
  commands from Parts 2 and 3.
- `# ` Did it hear you correctly? Did the spoken reply make sense with your eyes
  closed? Was it fast enough to feel like a conversation, or did you wait?

If voice misbehaves but the text CLI worked, the fault is the microphone/STT, not
the brain — say so in your notes and we isolate it there.

---

## What to send back

Copy the entire session — every line you typed, everything ARADHYA printed, and
your `#` reactions inline where they happened. Don't summarize it or clean it up.
Raw is more useful than tidy. If something crashed, the traceback is the gift.

Rough order of what I most want to learn, from your notes:
1. Where did you not know what to do next? (discoverability)
2. What did it get *wrong* — wrong tool, wrong window, wrong control? (accuracy)
3. What was so slow you'd never use it? (latency)
4. What made you think "oh, that's actually useful"? (keep this)
