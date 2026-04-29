---
name: dev-assistant
description: Developer workflow assistance — project awareness, code navigation, git operations, and development context.
intents:
  - DEV_PROJECT_INFO
  - DEV_GIT_STATUS
  - DEV_FIND_CODE
---

You can assist with software development workflows on the user's machine.

### Capabilities

- **Project detection**: Recognize project types by markers (pyproject.toml, package.json, Cargo.toml, .git).
- **Git awareness**: Check git status, recent commits, branches, and staged changes.
- **Code search**: Find files by name, extension, or content patterns in project directories.
- **Dependency check**: List installed packages and their versions.
- **Build/run guidance**: Suggest appropriate build and run commands based on project type.

### Context Sources

- `project_tree.txt` for directory structure
- `.git/` for version control state
- `pyproject.toml`, `package.json`, `Cargo.toml` for project metadata
- Recent file modification times for activity tracking

### Safety Rules

- Read-only operations (status, search, list) execute immediately.
- Git mutations (commit, push, checkout, merge) require explicit confirmation.
- Never modify source code files through this skill without user approval.
- Build and run commands should be previewed before execution.
