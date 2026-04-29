---
name: system-tools
description: Core system operations — open paths, apps, URLs, find files, manage folders, and launch programs on Windows.
intents:
  - OPEN_PATH
  - OPEN_SECURITY_BLOGS
  - LOCATE_TXT_DENSE_FOLDER
  - OPEN_YESTERDAYS_PROJECT
  - OPEN_RECENT_GAME
  - SCREEN_CONTROL
  - EXTERNAL_DOCUMENT_HANDOFF
---

You have access to system-level operations on the user's Windows machine.

### Capabilities

- **Open paths**: Open files, folders, and applications by name or path.
- **Open URLs**: Open web pages in the default browser.
- **Find files**: Locate files and folders across configured user roots.
- **Find .txt-heavy folders**: Identify directories with the highest concentration of text files.
- **Reopen yesterday's project**: Find the project the user was most active in yesterday.
- **Open recent game**: Find the most recently played game from configured game library roots.
- **Open security blogs**: Open the user's preferred security blog URLs.

### Safety Rules

- Opening files, folders, apps, and URLs requires explicit user confirmation.
- Read-only queries (finding paths, listing files) can respond immediately.
- Never execute destructive operations (delete, format, overwrite) through this skill.
- Always show the resolved path before opening it so the user can verify.
