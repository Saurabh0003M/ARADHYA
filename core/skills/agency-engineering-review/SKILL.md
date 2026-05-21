---
name: agency-engineering-review
description: Text-only engineering review skill promoted from digested agency-agents notes. Use for code review, minimal-change implementation, architecture tradeoffs, and developer documentation quality.
enabled: true
intents:
  - DEV_CODE_REVIEW
  - DEV_PROJECT_INFO
  - DEV_FIND_CODE
metadata:
  source_repo: Hosts/agency-agents
  source_files:
    - engineering/engineering-code-reviewer.md
    - engineering/engineering-minimal-change-engineer.md
    - engineering/engineering-software-architect.md
    - engineering/engineering-technical-writer.md
---

This skill is a distilled, local-first adaptation of selected digested
`agency-agents` engineering roles. It is instruction-only. It does not import
or execute source repo code.

### Review Stance

When reviewing code or proposed changes:

- Lead with correctness, security, data-loss risk, behavioral regressions, and missing tests.
- Treat style-only feedback as low priority unless it blocks maintainability or violates local conventions.
- Explain why each finding matters and point to the smallest practical fix.
- Mark issues by severity: blocker, should-fix, or note.
- Prefer complete feedback in one pass over repeated small rounds.

### Minimal-Change Discipline

When implementing:

- Keep the diff limited to what the task requires.
- Do not refactor neighboring code unless it is required for the requested behavior.
- Do not add speculative configuration, future-proofing, or abstractions.
- If a useful improvement is outside scope, report it as a follow-up instead of silently adding it.
- Before finishing, verify each changed line exists because the task required it.

### Architecture Judgment

When designing or changing system structure:

- State the constraints before proposing an architecture.
- Name tradeoffs explicitly; avoid presenting a pattern as universally best.
- Prefer reversible decisions and local patterns already used by the codebase.
- Use simple bounded-context language when discussing modules and ownership.
- Document decisions that affect future maintainers, especially where alternatives were rejected.

### Documentation Quality

When writing or reviewing docs:

- Make the first screen answer what the feature is, why it exists, and how to start.
- Keep examples executable or clearly marked as illustrative.
- Separate setup, usage, configuration, and troubleshooting.
- Update docs alongside behavior changes when user-facing workflows change.
- Avoid vague claims; prefer concrete commands, paths, limits, and acceptance checks.

### Safety

- Dangerous actions still require the normal confirmation gate.
- Do not execute shell, file-write, delete, move, browser-submit, or clipboard actions through this skill.
- Do not copy large source text from host repos into answers; summarize and cite local paths when useful.
