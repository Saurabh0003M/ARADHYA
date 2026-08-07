# AGENTS.md — Aradhya Operating Intelligence

> This file is the definitive reference for any AI agent or tool
> interacting with the Aradhya codebase.  If you are an AI reading this,
> follow these instructions precisely.

## What is Aradhya?

Aradhya is a **local-first Operating Intelligence (OI)** assistant for
Windows. It runs on the user's machine using Ollama for LLM inference
by default, with cloud fallbacks via OpenRouter gated by privacy checks.
It is an autonomous orchestrator managing files, web browsing, screen vision,
and persistent background tasks.

## Architecture

```
User Input (CLI / Hotkey / Telegram / Desktop Floating Icon)
       |
       v
   main.py / daemon.py ──> Command Dispatch (/help, /voice, /telegram, etc.)
       |
       v  (natural language / raw input)
   assistant_core.py   ──> Intent Planner + Context Engine (SQLite State Store)
       |
       v
   agent_loop.py       ──> Hook Engine -> Permission Rules -> Confirmation Gate
       |                           |
       v                           v
   model_provider.py       tools/ (browser, desktop, file, hardware, maintenance, power,
   (Ollama/OpenRouter)            profile, scheduler, session, shell, system, vision, web)
                           skills/ (dynamic behavioral extensions via SKILL.md)
                           workflows/ (trust-boundary engine, guided workflows)
```

## Key Files

| File | Purpose |
|------|---------|
| `src/aradhya/main.py` | CLI entry point, slash-command dispatch |
| `src/aradhya/daemon.py` | Persistent background process, HTTP API, System Tray |
| `src/aradhya/assistant_core.py` | State machine, context aggregation, planner orchestration |
| `src/aradhya/agent_loop.py` | ReAct execution loop (prompt -> model -> tools) |
| `src/aradhya/state_store.py` | Thread-safe SQLite backend for sessions and audit |
| `src/aradhya/hooks/hook_engine.py` | Lifecycle interception and dynamic input/output rules |
| `src/aradhya/permission_rules.py` | Pattern-based allow/deny execution policies |
| `src/aradhya/ui/floating_icon.py` | Tkinter desktop overlay for quick Mic/Vision activation |
| `src/aradhya/channels/telegram.py` | Remote access proxy mimicking live streaming |
| `src/aradhya/tools/` | Tool implementations (Browser, Desktop, File, Hardware, Maintenance, Power, Profile, Scheduler, Session, Shell, System, Vision, Web) |
| `src/aradhya/skills/` | Skill framework (`SKILL.md` parser, registry, active context) |
| `src/aradhya/workflows/trust_boundary.py` | Trust-boundary workflow engine for safe multi-step operations |
| `src/aradhya/desktop_control.py` | Desktop control via UI Automation |
| `src/aradhya/user_profile.py` | Structured user-context store for form assistance |
| `src/aradhya/utils/hardware_profile.py` | Hardware detection and model recommendations |

## Safety Rules — NEVER VIOLATE

1. **Confirmation Gate**: The tools `run_command`, `write_file`, `delete_file`,
   `move_file`, `open_path`, `open_url`, `browser_click`, `browser_type`,
   `browser_submit`, `clipboard_write`, and `schedule_task` require explicit 
   user confirmation before execution.

2. **Dry-run by default**: `allow_live_execution` is `false` by default.
   Plans are generated but not executed until the user approves.

3. **Audit Everything**: All tool calls are automatically logged to 
   `~/.aradhya/audit/audit.jsonl` via event-sourcing. Never bypass the logger.

4. **Hooks and Permissions**: Respect the Parasite OS engines. `PreToolUse`
   and `PostToolUse` rules may deny, modify, or block actions prior to user gating.

5. **Local-first**: Prefer local tools and local models. Cloud APIs (OpenRouter) 
   are strictly fallback mechanisms subject to `CloudPrivacyGate` evaluation.

## Coding Conventions

- **Python 3.10+** with `from __future__ import annotations`
- **loguru** for logging (not stdlib `logging`)
- **rich** for terminal output (import from `src/aradhya/ui/cli.py`, never print raw)
- **Slash commands**: All new commands use `/command` format
- **Skills**: New capabilities go in `core/skills/<name>/SKILL.md`
- **Tools**: New tools register in `assistant_core._build_tool_registry()`
- **Tests**: Unit tests in `tests/unit/`, run with `pytest -q` (requires `pip install -r requirements-dev.txt`; coverage is opt-in, see CONTRIBUTING.md)

## How to Add a New Skill

1. Create `core/skills/<skill-name>/SKILL.md`
2. Add YAML frontmatter with `name`, `description`, `intents`
3. Write Markdown instructions for the AI
4. The skill auto-loads on next startup (no code changes needed)

## How to Add a New Tool

1. Create a function in the appropriate `src/aradhya/tools/<category>.py`
2. Decorate it with `@tool_definition`
3. Register it inside `assistant_core.py` `_build_tool_registry()` method
4. If dangerous, the tool is naturally gated via `agent_loop.py`'s `DANGEROUS_TOOLS` set
5. Add a unit test in `tests/unit/`

## Project Philosophy (from ETHOS)

- **Search before building** — understand the landscape before coding
- **Boil the lake** — if a full implementation is only slightly harder, do the complete thing
- **User sovereignty** — AI recommends, human decides
- **Local control** — user's machine, user's data, user's rules

---

## LLM Access via freellmapi

All LLM calls on this machine route through a self-hosted OpenAI-compatible proxy.
**Proxy must be running** before any LLM call: `cd F:\ARADHYA\freellmapi && npm run dev`

- **API endpoint**: `http://localhost:3001/v1/chat/completions`
- **Dashboard**: `http://localhost:5173`
- **Auth**: `OPENAI_API_KEY` env var (already set as Windows user env var — no config needed)

### Provider Matrix

| Provider | Speed | Best For |
|---|---|---|
| **Groq** | ⚡ Fastest | Speed-critical tasks, quick answers |
| **Cerebras** | ⚡ Very fast | Real-time streaming |
| **SambaNova** | 🚀 Fast | Balanced speed + quality |
| **Google** | 🔄 Medium | Long documents, multimodal (Gemini) |
| **Mistral** | 🔄 Medium | **Code generation** (Codestral/Devstral) |
| **Cohere** | 🔄 Medium | **RAG / retrieval**, Command-A reasoning |
| **Cloudflare** | ⚡ Fast | Lightweight / classification tasks |
| **OpenRouter** | 🔄 Variable | Fallback pool, rare models |
| **NVIDIA NIM** | 🔄 Medium | ⚠️ Some models 410 Gone — use `auto` |
| **Ollama** | 🐌 Local | Privacy-critical, offline, no rate limits |
| **LLM7** | ⚡ Fast | Free tier general tasks |
| **Pollinations** | ⚡ Fast | Always-available free fallback |

### Model Selection by Task

| Task | Model | Provider |
|---|---|---|
| Fast answer | `llama-3.1-8b-instant` | Groq |
| General purpose | `llama-3.3-70b-versatile` | Groq |
| Code generation | `codestral-latest` | Mistral |
| Code review | `qwen/qwen3-coder:free` | OpenRouter |
| Deep reasoning | `deepseek-ai/deepseek-v4-pro` | NVIDIA NIM |
| Long document | `gemini-2.5-flash` | Google |
| RAG / retrieval | `command-a-reasoning-08-2025` | Cohere |
| Private data | local model | Ollama |
| Auto-route | `auto` | freellmapi picks best |

### Rate Limits & High Traffic

Handled **automatically** by freellmapi — no retry logic needed in agent code:
- 20-attempt retry loop per request
- 429/503/timeout → skips that model+key, tries next provider
- All providers exhausted → HTTP 429 → tell user to wait briefly
