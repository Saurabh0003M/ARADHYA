# AGENTS.md — Aradhya Operating Intelligence

> This file is the definitive reference for any AI agent or tool
> interacting with the Aradhya codebase.  If you are an AI reading this,
> follow these instructions precisely.

## What is Aradhya?

Aradhya is a **local-first Operating Intelligence (OI)** assistant for
Windows.  It runs on the user's machine using Ollama for LLM inference,
meaning all data stays local and no cloud API keys are required.

## Architecture

```
User Input (CLI / Voice / Telegram / Floating Icon)
       |
       v
   main.py  ──>  Command Dispatch (/help, /status, /voice, etc.)
       |
       v  (natural language input)
   assistant_core.py  ──>  Context Engine + Session Manager
       |
       v
   agent_loop.py  ──>  Tool Registry + Confirmation Gate
       |                    |
       v                    v
   model_provider.py    tools/ (file, shell, web, browser, vision, power)
   (Ollama API)
```

## Key Files

| File | Purpose |
|------|---------|
| `src/aradhya/main.py` | CLI entry point, slash-command dispatch |
| `src/aradhya/assistant_core.py` | State machine, planner, tool orchestration |
| `src/aradhya/agent_loop.py` | Agentic execution loop (prompt -> model -> tool -> result) |
| `src/aradhya/cli_ui.py` | Rich terminal rendering (all user-facing output) |
| `src/aradhya/model_provider.py` | Ollama API integration |
| `src/aradhya/tools/` | Tool implementations (read_file, run_command, etc.) |
| `src/aradhya/skills/` | Skill framework (SKILL.md loader, registry) |
| `src/aradhya/audit_logger.py` | JSONL audit trail for all tool executions |
| `src/aradhya/telegram_bot.py` | Telegram bot for remote access |
| `core/memory/profile.json` | Model and voice configuration |
| `core/memory/preferences.json` | Behavior preferences (execution policy, index settings) |
| `core/skills/` | Bundled SKILL.md files |

## Safety Rules — NEVER VIOLATE

1. **Confirmation gate**: The tools `run_command`, `write_file`, `delete_file`,
   `move_file`, `open_path`, `open_url`, `browser_click`, `browser_type`,
   `browser_submit`, `clipboard_write` require explicit user confirmation
   before execution.

2. **Dry-run by default**: `allow_live_execution` is `false` by default.
   Plans are generated but not executed until the user approves.

3. **Audit everything**: All tool calls are logged to `~/.aradhya/audit/audit.jsonl`.
   Never disable or bypass the audit logger.

4. **No auto-submit**: Never auto-execute destructive operations.
   The user is always the final decision maker.

5. **Local-first**: Prefer local tools and local models.
   Cloud APIs are optional fallbacks, never defaults.

## Coding Conventions

- **Python 3.10+** with `from __future__ import annotations`
- **loguru** for logging (not stdlib `logging`)
- **rich** for terminal output (import from `cli_ui.py`, never print raw)
- **Slash commands**: All new commands use `/command` format
- **Skills**: New capabilities go in `core/skills/<name>/SKILL.md`
- **Tools**: New tools register in `assistant_core._build_tool_registry()`
- **Tests**: Unit tests in `tests/unit/`, run with `pytest --override-ini="addopts="`

## How to Add a New Skill

1. Create `core/skills/<skill-name>/SKILL.md`
2. Add YAML frontmatter with `name`, `description`, `intents`
3. Write Markdown instructions for the AI
4. The skill auto-loads on next startup (no code changes needed)

## How to Add a New Tool

1. Create function in appropriate `src/aradhya/tools/<category>.py`
2. Register in `assistant_core.py` `_build_tool_registry()` method
3. If dangerous, add to `dangerous_tools` set in `agent_loop.py`
4. Add unit test in `tests/unit/`

## Project Philosophy (from ETHOS)

- **Search before building** — understand the landscape before coding
- **Boil the lake** — if a full implementation is only slightly harder, do the complete thing
- **User sovereignty** — AI recommends, human decides
- **Local control** — user's machine, user's data, user's rules
