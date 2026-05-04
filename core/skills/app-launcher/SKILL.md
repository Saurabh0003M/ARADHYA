---
name: app-launcher
description: Smart application launcher — finds and opens apps by fuzzy name match, manages favorites, and tracks usage.
intents:
  - LAUNCH_APP
  - FIND_APP
  - OPEN_PROGRAM
  - APP_LIST
---

You can find and launch applications on the user's Windows machine.

### When to Activate

This skill triggers when the user asks:
- "Open Chrome" / "Launch VS Code" / "Start Discord"
- "Find the app called ..."
- "What apps do I have?"
- "Open my code editor"

### Search Strategy

Search for applications in this order (stop at first match):

1. **Start Menu shortcuts** — Scan `%APPDATA%\Microsoft\Windows\Start Menu\Programs` and `%ProgramData%\Microsoft\Windows\Start Menu\Programs` for `.lnk` files.
2. **PATH executables** — Check if the app name matches a command on PATH.
3. **Common install paths** — Check `C:\Program Files`, `C:\Program Files (x86)`, and `%LOCALAPPDATA%\Programs`.
4. **Fuzzy match** — If no exact match, try fuzzy matching on app names (e.g., "code" matches "Visual Studio Code").

### Common Aliases

Map common short names to full app names:
- "chrome" -> "Google Chrome"
- "code" / "vscode" -> "Visual Studio Code"  
- "explorer" -> "File Explorer"
- "cmd" -> "Command Prompt"
- "ps" / "powershell" -> "Windows PowerShell"
- "notepad++" -> "Notepad++"
- "discord" -> "Discord"
- "slack" -> "Slack"
- "teams" -> "Microsoft Teams"

### Tools to Use

- `run_command` with `start "" "path\to\app.exe"` to launch
- `list_directory` to scan Start Menu folders
- `run_command` with `where <appname>` to check PATH

### Safety Rules

- Launching applications requires explicit user confirmation.
- Read-only searching (listing apps, finding paths) executes immediately.
- Never pass untrusted user input directly to `start` — sanitize the path first.
