# Aradhya

Aradhya is a local-first Operating Intelligence assistant for Windows. It runs
on the user's machine, prefers Ollama for local inference, keeps private data
local by default, and routes device-affecting actions through explicit
confirmation and runtime policy.

The project is not just a chatbot wrapper. Aradhya is becoming a Windows OI
layer: intent routing, local context, model orchestration, skills, tool use,
audit trails, sessions, hooks, permissions, and safe execution.

## Current Capabilities

- Rich terminal assistant with slash commands and natural language requests.
- Ollama-first local model provider with health checks and direct model prompts.
- Optional OpenRouter worker support behind a cloud privacy assessment gate.
- Deterministic planner for common local tasks plus model-driven agent fallback.
- Tool registry for files, shell, web, browser, vision, power, sessions,
  scheduler, skill installation, and learnings.
- Confirmation gate for risky tools and dry-run behavior when live execution is
  disabled.
- Pattern-based permission rules with deny rules taking priority over allow
  rules.
- JSONL audit logging for turns, commands, security events, and tool calls.
- Session storage, history compression, and SQLite-backed state primitives.
- Local directory indexing and cache validation for path-aware responses.
- Voice inbox processing, manual transcripts, optional local transcription,
  live voice activation, and wake-word support.
- Local `SKILL.md` loading from bundled and user/project skill locations.
- User/project hook configuration for session and tool lifecycle events.
- Agent definition loading from Markdown files with YAML-style frontmatter.
- Public API catalog search, inspection, category browsing, and recommendation.
- Topology and LAN federation foundation commands.
- Parasite OS host-repo digestion, candidate ranking, inspection, and ledger
  generation.
- Portable path resolution through `ARADHYA_HOME`, `parasite.toml`, and
  `~/.aradhya` defaults.

Browser operation, screen guidance, full LAN transport, and drive migration are
still planned or partial. They are not complete product surfaces yet.

## Requirements

- Windows 10 or 11
- Python 3.10+
- Git
- Ollama
- At least one local Ollama model

The active model configuration is loaded from `core/config/profile.local.json`
first, then `core/config/profile.json`, with legacy fallbacks under
`core/memory/`.

## First Run

From PowerShell:

```powershell
git clone https://github.com/Saurabh0003M/ARADHYA.git ARADHYA
cd ARADHYA
scripts\first_run.bat
```

Then verify the environment:

```powershell
scripts\doctor.bat
```

## Launch

```powershell
.\arise.bat
```

The launcher prefers `venv\Scripts\python.exe` when the virtual environment has
the required packages. If the venv is incomplete, it falls back to `python` on
`PATH` and tells you to rerun setup.

Direct launch:

```powershell
venv\Scripts\python.exe -m src.aradhya.main
```

## First Commands

Inside Aradhya:

```text
/help
/status
/model
/model workers
/skills
/voice
/cache
/audit
open README.md
yes proceed
find the folder with the highest concentration of .txt files
exit
```

## Command Reference

Core:

- `/help` - show commands.
- `/status` - show model, voice, skills, wake state, and live execution state.
- `/topology` and `/topology rescan` - show or regenerate local topology.
- `/sleep` - send Aradhya to idle.
- `exit` - shut down the CLI.

Voice:

- `/voice` - show voice pipeline status.
- `/voice process` - process pending audio from `audio/inbox`.
- `/voice activate` and `/voice stop` - start or stop live microphone capture.
- `/wake-word on` and `/wake-word off` - control wake-word detection.

Model and skills:

- `/model` - check configured model health.
- `/model ask <prompt>` - send a direct prompt to the configured model.
- `/model workers` - list local and optional cloud workers.
- `/model workers assess <text>` - check whether text is safe for cloud
  routing.
- `/skills` - list loaded skills.
- `/skills enable <name>` and `/skills disable <name>` - toggle a skill.

Tools and integration:

- `/icon on` and `/icon off` - control the floating quick-access icon.
- `/cache` - validate and benchmark the local context cache.
- `/apis`, `/apis search <query>`, `/apis category <name>`,
  `/apis inspect <name>`, `/apis recommend <need>` - use the local public API
  catalog.
- `/parasite status`, `/parasite candidates`, `/parasite inspect <repo>`,
  `/parasite ledger`, `/parasite digest <repo>`, `/parasite resume <repo>` -
  operate the Parasite OS host-repo digestion and integration ledger.
- `/federation init`, `/federation status`, `/federation doctor` - use the
  current LAN federation foundation.
- `/telegram start` and `/telegram stop` - control the Telegram channel when
  configured.
- `/daemon start` and `/daemon stop` - control the background daemon.
- `/setup` - run the interactive setup wizard.
- `/audit` - show recent audit log entries.

## Safety Model

Aradhya is designed around user sovereignty:

- Risky tools require confirmation before execution.
- `allow_live_execution` is false by default, so confirmed machine-changing
  actions become dry-run previews unless live execution is enabled.
- Permission rules can allow or deny specific tool calls by pattern; deny rules
  always win.
- Tool runtime policy constrains allowed roots, mutation grants, and live
  execution.
- Shell, file writes, deletes, moves, opens, browser actions, and clipboard
  writes stay behind the confirmation/policy path.
- Tool calls, turns, commands, and security events are audited.
- Local models and local tools are preferred; cloud model workers are optional
  and checked by the privacy gate.

## Configuration

Primary config:

- `core/config/profile.json`
- `core/config/profile.local.json`
- `core/config/preferences.json`

Legacy fallback config:

- `core/memory/profile.json`
- `core/memory/profile.local.json`
- `core/memory/preferences.json`

Common fields:

- `model.provider`: model provider, usually `ollama`.
- `model.model_name`: local Ollama model name.
- `model.base_url`: Ollama API URL, usually `http://127.0.0.1:11434`.
- `allow_live_execution`: when false, machine-changing actions are blocked or
  previewed.
- `user_roots`: optional local search roots. If omitted, Aradhya uses common
  user folders and the repo root instead of scanning the entire home folder.

Portable runtime state resolves through:

1. `ARADHYA_HOME`
2. `[paths].home` in `parasite.toml`
3. `~/.aradhya`

## Voice

Default voice provider: `manual_transcript`.

Manual transcript flow:

1. Put audio in `audio/inbox`, for example `task.wav`.
2. Put matching text in `audio/manual_transcripts`, for example `task.txt`.
3. Run `/voice process`.

Optional local transcription:

```powershell
venv\Scripts\python.exe -m pip install -r requirements-voice.txt
```

Optional live microphone activation:

```powershell
venv\Scripts\python.exe -m pip install -r requirements-voice-activation.txt
```

## Skills, Agents, Hooks, And Permissions

Skills:

- Bundled skills live under `core/skills/<name>/SKILL.md`.
- Additional skill loading is handled by the skill framework.
- Use `/skills` to inspect loaded skills.

Agents:

- User agents can be defined as Markdown files in `~/.aradhya/agents`.
- Project agents can be defined under `.aradhya/agents`.
- Agent files use YAML-style frontmatter for fields such as `name`,
  `description`, `tools`, `model`, `max_turns`, and `isolation`.

Hooks:

- User hooks load from `~/.aradhya/hooks/hooks.json`.
- Project hooks load from `.aradhya/hooks/hooks.json`.
- Supported hook events include `SessionStart`, `PreToolUse`, `PostToolUse`,
  and `Stop`.

Permissions:

- User permission rules load from `~/.aradhya/permissions.json`.
- Project permission rules load from `.aradhya/permissions.json`.
- Rules can allow, deny, or require confirmation for tool patterns such as
  `run_command(git *)` or `write_file(*.py)`.

## Project Structure

```text
core/
  config/        Runtime configuration
  memory/        User context and legacy config fallback
  skills/        Bundled SKILL.md files
docs/            Roadmaps, vision, and progress notes
scripts/         Setup, doctor, and launch helpers
src/aradhya/
  main.py        CLI entry point and slash-command dispatch
  assistant_core.py
  agent_loop.py
  model_provider.py
  tools/
  hooks/
  agents/
  voice/
tests/unit/      Unit tests
```

## Development Workflow

Run unit tests without the default coverage addopts:

```powershell
venv\Scripts\python.exe -m pytest tests\unit --override-ini="addopts="
```

Use a dedicated base temp directory outside the Git worktree when validating
cleanup-sensitive changes:

```powershell
venv\Scripts\python.exe -m pytest tests\unit --override-ini="addopts=" --basetemp C:\tmp\aradhya_readme_cleanup
```

Run the environment doctor:

```powershell
scripts\doctor.bat
```

Generated pytest/runtime artifacts under `data/processed/pytest_*` are ignored
and should not be committed.
