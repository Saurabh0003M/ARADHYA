# Aradhya Agentic Coding Assistant - PRD

## Original Problem Statement
Build an agentic AI assistant (Operating Intelligence) with CLI aesthetic, deeply integrated with local filesystem and Git. Local models (Ollama) are primary, cloud models optional. Single unified natural language input - no separate modes. Floating Air Command hub for quick toggles. User can change preferences by talking to Aradhya. Multi-step workflows with user confirmation.

## Architecture
- **Backend**: FastAPI (Python) on port 8001
- **Frontend**: React + Tailwind CSS v3 on port 3000
- **Database**: MongoDB (messages, commands, settings, templates)
- **LLM**: OpenAI GPT-4.1 via Emergent LLM key (cloud); Ollama local models primary
- **Repo**: github.com/Saurabh0003M/ARADHYA.git (branch: user-handling)

## What's Implemented (v2.0 - April 14, 2026)

### UI/UX - CLI Terminal Aesthetic
- Dark/Light theme with proper CSS variable system (all colors switch)
- Sun/Moon icon toggle in status bar + Settings panel
- Monospace fonts (JetBrains Mono), color-coded terminal output
- ASCII art welcome banner with natural language examples
- Single unified `$` prompt input (no separate chat/command/search modes)

### Air Command Hub (Floating)
- Single "A" icon button, bottom-right
- Expands on click → shows Quick Toggles (Mic, Screen, Internet, Interact, Voice) + Panels (Files, Git, Templates, Settings) + Utils (Clear, Stop)
- Auto-collapses on mouse leave (400ms delay)
- VS Code-style dropdown design

### Agentic Features
- **File Explorer**: Directory tree with file preview, binary file warnings
- **Git Panel**: Status, branches, stage all, commit (AI auto-message), push, create branch, log
- **Shell Execution**: Blocked in sandbox mode (403 error)
- **Workspace Diff**: Compare old vs new file content
- **Natural Language Commands**: AI interprets intent from plain English

### Settings (Centralized)
- **Theme**: Dark/Light with Moon/Sun icons
- **Assistant Name**: Editable, saved to DB
- **Model Selector**: LOCAL FIRST (Ollama), Cloud optional (GPT-4.1, GPT-5.2, Claude)
- **Workspace Path**: Configurable
- **Sandbox Mode**: Toggle shell/file write protection
- **Security Filter**: Web search content filtering
- **Voice Presets**: 4 presets (Aria Female, Luna Baby, Atlas Male, System Default)
- **TTS Toggle**: Voice replies on/off
- **Model Optimization**: TurboQuant quantization reference

### Custom Templates
- 6 built-in templates
- User-created templates (Create/Delete CRUD)
- Execute templates with one click

### Voice
- Browser Web Speech API for mic input (Ctrl+Space)
- TTS output speaks all assistant responses using selected voice preset
- 4 voice presets with different rate/pitch settings

## Testing Results
- Iteration 1: 100% backend, 95% frontend
- Iteration 2: 95.2% backend, 90% frontend
- **Iteration 3: 95.2% backend, 100% frontend** ← Current

## Backlog
### P1 (Next)
- Split-pane Diff Viewer with Accept/Reject buttons
- Shell output display inline in terminal
- Win+Ctrl push-to-talk activation
- Multi-step workflow execution with step-by-step display
- Preferences via natural language chat (backend parsing)

### P2
- Ollama model folder detection ("Add Model → Select Folder")
- Screen capture/share toggle (vision context)
- App launching and system control commands
- Multi-app workflows (open whatsapp, fill forms, review before submit)

### P3 (Future)
- Desktop app (Electron)
- Wispr Flow system-wide voice activation
- Debate AI multi-model reasoning
- Browser automation (Playwright-based)
