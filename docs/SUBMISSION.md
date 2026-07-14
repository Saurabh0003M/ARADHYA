# ARADHYA — OSDHack 2026 Submission

> **Theme:** On-Device AI · **Track:** Open Source · **License:** GPLv3

---

## What We Built

**ARADHYA** is a local-first **Operating Intelligence (OI)** for Windows — a terminal AI assistant that understands natural language, reasons about your intent, and acts on your machine using a rich set of tools, all while running its AI model **entirely on-device**.

You type a request in plain English. ARADHYA's local LLM figures out what you need — whether it's managing files, running shell commands, searching the web, scheduling tasks, or querying system hardware — and executes a multi-step plan, asking for your explicit approval before anything touches the machine. No cloud account required. No data leaves your device.

---

## Why It Matters

Privacy should not be a feature you opt into — it should be the default. Most AI assistants funnel every keystroke to a remote API. ARADHYA inverts that: inference runs locally via Ollama, your prompts and file contents never leave the machine, and the system works fully offline once the model is pulled. For users who handle sensitive code, personal documents, or simply value data sovereignty, this is a meaningful difference.

Safety is the other pillar. AI that can run shell commands and write files is powerful — and dangerous. ARADHYA enforces a strict, multi-layered **Confirmation Gate**: every device-affecting action passes through a Hook Engine (lifecycle rules), a Permission Engine (pattern-based allow/deny policies), and finally an explicit user-approval prompt before execution. Dry-run mode is the default. Every action is audit-logged to a JSONL trail. The result is an assistant you can trust with real work on your real machine.

---

## How It Works

ARADHYA's pipeline is concrete and auditable:

1. **Natural-language input** — the user types a request in the CLI (or via Telegram, or a desktop floating icon).
2. **Intent routing** — the `IntentPlanner` in `assistant_core.py` classifies the request: is it a simple chat reply, a slash command, or something that needs tool use?
3. **Local LLM inference** — the request (plus session context) is sent to **Ollama** running `llama3.2:3b` locally. No network call.
4. **ReAct agent loop** — `agent_loop.py` implements a structured cycle: *prompt → model → tool calls → execute → feed results → loop* until the model produces a final answer. This is a true agentic loop, not a single-shot prompt.
5. **Tool registry** — the model can call from a registry of 60+ tools across categories: file management, shell execution, web search, browser automation, power management, scheduling, system diagnostics, hardware profiling, and more. Each tool is a decorated Python function registered in `assistant_core._build_tool_registry()`.
6. **Confirmation Gate** — every tool call passes through `HookEngine → PermissionEngine → User Approval`. Dangerous tools (writes, deletes, shell commands, browser actions) require the user to type `yes` before execution.
7. **Audit & memory** — all actions are event-sourced to `audit.jsonl`. Session history is persisted in a thread-safe **SQLite WAL database** with automatic context compaction, so conversations survive restarts without unbounded growth.

---

## How It Uses On-Device AI

This is the core of our submission. ARADHYA's AI — intent classification, multi-step reasoning, tool selection, and natural-language responses — runs **100% locally** through [Ollama](https://ollama.com/) with the `llama3.2:3b` model (~2 GB, runs on CPU). There is no cloud API key in the default configuration. The system starts, thinks, and responds without touching the network.

An optional cloud fallback exists (OpenRouter / Cloudflare Workers AI) for users who want larger models, but it is **never active by default**. When enabled, every outbound request passes through a `CloudPrivacyGate` that evaluates the prompt for sensitive content and blocks transmission if the risk score is too high. The cloud path is an escape hatch, not the architecture.

**On-device AI is not a checkbox feature here — it is the design.**

---

## How to Run It

**Requirements:** Windows 10/11, Python 3.10+, Git, [Ollama](https://ollama.com/).

```powershell
# 1. Clone the repo
git clone https://github.com/Saurabh0003M/ARADHYA.git ARADHYA
cd ARADHYA

# 2. Create venv, install dependencies
scripts\first_run.bat

# 3. Pull the default local model (~2 GB download, runs on CPU)
ollama pull llama3.2:3b

# 4. Verify everything is wired up
scripts\doctor.bat

# 5. Launch the assistant CLI
.\arise.bat
```

That's it. Five steps, no API keys, no Docker, no cloud signup.

---

## What's Next / Honest Scope

**What works today (demonstrated core):**

- Local natural-language chat powered by on-device Ollama inference
- 60+ registered tools for file, shell, web, system, scheduling, and hardware operations
- Full Safety Confirmation Gate with Hook Engine, Permission Engine, and user approval
- Persistent SQLite session memory with automatic context compaction
- Complete JSONL audit trail of every action
- Dynamic skill loading from `SKILL.md` definitions (12 bundled skills)
- `/status`, `/help`, `/audit`, and other slash commands for system introspection

**What exists but is experimental (requires optional dependencies):**

- **Voice integration** — local transcription via Faster-Whisper, push-to-talk, wake-word detection. Requires `requirements-voice.txt` and `requirements-voice-activation.txt`.
- **Screen vision** — screen capture, OCR, and visual-context tools. Requires a vision-capable model and optional dependencies.
- **Desktop control** — UI Automation–based control of native Windows apps. Requires `uiautomation` and `comtypes` extras.
- **Telegram bot** — remote access channel simulating a live-streaming experience.

We are not claiming these work out of the box. They are real code, tested individually, but they require additional setup and are not part of the default Quick Start path. The solid, demonstrated core is: **local chat + tool use + the safety gate** — and that core runs reliably from a clean install in under five minutes.

### Roadmap

**Hybrid local-manager / cloud-worker orchestration (planned).** The local model (`llama3.2:3b`) will act as the reasoning manager and delegate specialized subtasks to optional cloud "worker" models through ARADHYA's existing subagent system (`spawn_subagent` already accepts a per-worker model parameter). Every cloud call will be gated by the existing `CloudPrivacyGate`, so orchestration logic and private context stay on-device — the local model does the thinking; cloud workers are opt-in accelerators, never a replacement. This keeps the On-Device AI thesis fully intact.

**Credential hardening (planned).** Cloud API-key storage will move out of any committed file and into environment variables or the gitignored `profile.local.json`, with all key access routed through `os.environ` so that secrets never appear in version control.

---

*ARADHYA — your private, on-device AI operating assistant. Open source. Runs on your hardware. Your data stays yours.*
