<div align="center">
  <h1>✨ Aradhya</h1>
  <p><strong>A Local-First Operating Intelligence (OI) Assistant for Windows</strong></p>

  [![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
  [![Windows](https://img.shields.io/badge/OS-Windows_10%20%7C%2011-0078D6?logo=windows&logoColor=white)](https://www.microsoft.com/en-us/windows/)
  [![Ollama](https://img.shields.io/badge/Local_AI-Ollama-white?logo=ollama&logoColor=black)](https://ollama.com/)
</div>

<br />

> **Aradhya** is not just another chatbot wrapper. It is evolving into a comprehensive **Windows Operating Intelligence (OI) layer**—featuring intent routing, local context, model orchestration, dynamic skills, safe tool execution, and session management.

---

## 🚀 Key Features

* **🧠 Local-First Inference**: Prefers Ollama for local model execution, keeping your data completely private.
* **🛡️ Sovereign Safety**: Routes all device-affecting actions through explicit confirmation gates. "Dry-run" is the default behavior.
* **💻 Rich Terminal UI**: Interactive assistant with slash commands and natural language understanding.
* **🛠️ Extensive Tool Registry**: Built-in tools for file management, shell execution, web browsing, vision, power management, scheduling, and more.
* **📜 Audit Trails**: Every turn, command, security event, and tool call is logged in JSONL format for complete transparency.
* **🎙️ Voice Integration**: Supports voice inbox processing, optional local transcription, and wake-word activation.
* **🔌 Dynamic Skills & Agents**: Easily extend capabilities using Markdown-based `SKILL.md` files or YAML-frontmatter agent definitions.
* **🌐 Local API Catalog**: Browse, search, and utilize a local public API catalog directly from the CLI.
* **🕸️ Network Topology**: Foundation for LAN federation and topology discovery.

*(Browser operations, screen guidance, full LAN transport, and drive migration are currently in development!)*

---

## 📋 Requirements

Before you begin, ensure you have the following installed:
- **Windows 10 or 11**
- **Python 3.10+**
- **Git**
- **[Ollama](https://ollama.com/)** (with at least one local model downloaded)

---

## 🛠️ Quick Start

### 1. Installation

Open PowerShell and clone the repository:

```powershell
git clone https://github.com/Saurabh0003M/ARADHYA.git ARADHYA
cd ARADHYA
scripts\first_run.bat
```

### 2. Verify Environment

Ensure everything is configured correctly:
```powershell
scripts\doctor.bat
```

### 3. Launch Aradhya

Start the assistant:
```powershell
.\arise.bat
```
*(The launcher automatically prefers the virtual environment's Python if available).*

Alternatively, you can launch it directly:
```powershell
venv\Scripts\python.exe -m src.aradhya.main
```

---

## 💬 Command Reference

Once Aradhya is running, try these commands:

### Core Commands
| Command | Description |
|---|---|
| `/help` | Display all available commands |
| `/status` | Show model, voice, skills, wake state, and live execution state |
| `/topology` | Show local topology (use `/topology rescan` to regenerate) |
| `/sleep` | Send Aradhya to idle mode |
| `exit` | Shut down the CLI |

### Model & Skills
| Command | Description |
|---|---|
| `/model` | Check configured model health |
| `/model ask <prompt>` | Send a direct prompt to the configured model |
| `/model workers` | List local and optional cloud workers |
| `/skills` | List loaded skills |
| `/skills enable/disable <name>`| Toggle specific skills on or off |

### Tools & Integration
| Command | Description |
|---|---|
| `/icon on/off` | Control the floating quick-access icon |
| `/cache` | Validate and benchmark the local context cache |
| `/apis search <query>` | Use the local public API catalog |
| `/parasite status` | Operate Parasite OS host-repo digestion |
| `/federation status` | Use the current LAN federation foundation |
| `/telegram start/stop` | Control the Telegram channel (if configured) |
| `/audit` | Show recent audit log entries |

### Voice Commands
| Command | Description |
|---|---|
| `/voice` | Show voice pipeline status |
| `/voice process` | Process pending audio from `audio/inbox` |
| `/voice activate` | Start live microphone capture |
| `/wake-word on` | Enable wake-word detection |

### Natural Language Examples
You can just talk to Aradhya!
> *"open README.md"*
> *"yes proceed"*
> *"find the folder with the highest concentration of .txt files"*

---

## 🔒 Safety First

Aradhya is designed around **User Sovereignty**:
- **Confirmation Gates**: Risky tools require your explicit approval before execution.
- **Dry-Run Default**: `allow_live_execution` is disabled by default. Machine-changing actions are previewed unless explicitly enabled.
- **Strict Permissions**: Pattern-based rules (e.g., `write_file(*.py)`) govern access, with "deny" rules always taking precedence.
- **Privacy Gate**: Optional cloud model workers are gated behind a privacy assessment.

---

## ⚙️ Configuration

Aradhya uses a flexible configuration hierarchy. The active model config is loaded from:
1. `core/config/profile.local.json` *(Primary)*
2. `core/config/profile.json`
3. Legacy fallbacks under `core/memory/`

**Key Configuration Fields:**
- `model.provider`: Usually `ollama`
- `model.model_name`: Your local Ollama model name
- `model.base_url`: Ollama API URL (default: `http://127.0.0.1:11434`)
- `allow_live_execution`: Toggle live execution vs dry-runs
- `user_roots`: Define specific search roots instead of scanning the entire home folder

**Portable Runtime State resolves through:**
1. `ARADHYA_HOME`
2. `[paths].home` in `parasite.toml`
3. `~/.aradhya`

---

## 🎙️ Advanced Voice Settings

**Default Voice Provider**: `manual_transcript`
1. Put audio in `audio/inbox` (e.g., `task.wav`)
2. Put matching text in `audio/manual_transcripts` (e.g., `task.txt`)
3. Run `/voice process`

**Optional Local Transcription Setup:**
```powershell
venv\Scripts\python.exe -m pip install -r requirements-voice.txt
```

**Optional Live Microphone Activation:**
```powershell
venv\Scripts\python.exe -m pip install -r requirements-voice-activation.txt
```

---

## 🧩 Skills, Agents, Hooks, And Permissions

- **Skills**: Bundled skills live under `core/skills/<name>/SKILL.md`. Use `/skills` to manage them.
- **Agents**: Define custom agents in `~/.aradhya/agents` or `.aradhya/agents` using YAML-frontmatter Markdown files.
- **Hooks**: Customize lifecycles (e.g., `PreToolUse`, `SessionStart`) via `hooks.json`.
- **Permissions**: Control tool access patterns via `permissions.json`.

---

## 🏗️ Project Architecture

```text
📦 ARADHYA
 ┣ 📂 core
 ┃ ┣ 📂 config       # Runtime configuration
 ┃ ┣ 📂 memory       # User context & legacy configs
 ┃ ┗ 📂 skills       # Bundled SKILL.md files
 ┣ 📂 docs           # Roadmaps, vision & progress
 ┣ 📂 scripts        # Setup & launch helpers
 ┣ 📂 src/aradhya    # Core application source
 ┃ ┣ 📜 main.py               # CLI entry & dispatch
 ┃ ┣ 📜 assistant_core.py     # State machine & tools
 ┃ ┣ 📜 agent_loop.py         # Agent execution loop
 ┃ ┗ 📂 tools                 # Tool implementations
 ┗ 📂 tests/unit     # Pytest unit tests
```

---

## 👨‍💻 Development

Run unit tests (without default coverage addopts):
```powershell
venv\Scripts\python.exe -m pytest tests\unit --override-ini="addopts="
```

Use a dedicated base temp directory outside the Git worktree when validating cleanup-sensitive changes:
```powershell
venv\Scripts\python.exe -m pytest tests\unit --override-ini="addopts=" --basetemp C:\tmp\aradhya_readme_cleanup
```

Run the environment doctor to diagnose issues:
```powershell
scripts\doctor.bat
```

> **Note**: Generated pytest runtime artifacts under `data/processed/pytest_*` are ignored and should not be committed.
