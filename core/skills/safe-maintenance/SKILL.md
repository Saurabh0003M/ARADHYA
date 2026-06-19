---
name: safe-maintenance
description: Reclaim disk space safely — scan for regenerable caches and build artifacts, present a ranked plan, and delete only what the user confirms.
intents:
  - DISK_CLEANUP
  - FREE_SPACE
  - CLEAN_CACHES
  - DISK_FULL
  - MAINTENANCE
---

You help the user reclaim disk space safely. This is a general maintenance loop —
it works the same whether the user says "my disk is full", "clean old caches in
this project", or "free up space in Downloads". Only the root directory changes.

### When to Activate

- "My disk is full / I'm running out of space"
- "Clean up caches in this project"
- "What's taking up space in <folder>?"
- "Remove build artifacts / node_modules I don't need"

### The Loop — analyze → plan → confirm → execute → summarize

This mirrors the trust-boundary workflow. **Never delete without an explicit
confirmation, and never delete outside the directories you scanned.**

1. **ANALYZE (read-only).** Call `analyze_disk_usage` with the user's root(s).
   It reports regenerable cleanup candidates (caches, build artifacts,
   `node_modules`) and how much space each uses. It never deletes anything.

2. **PLAN.** Present the candidates as a ranked list — largest first — with the
   path, size, and risk for each. Group them so the user can pick.

3. **USER SELECTS + CONFIRM.** Ask which candidates to remove. Restate the exact
   set and total space, then wait for an explicit "yes proceed". Deletion is
   irreversible; the regenerable ones come back on the next build/install, but
   say so rather than assuming.

4. **EXECUTE.** Only after confirmation, remove the selected items. Deletion is
   confined to the scanned roots.

5. **SUMMARIZE.** Report what was removed, what failed, and total space freed.

### Safety Rules

- `analyze_disk_usage` is read-only and needs no confirmation.
- Actual deletes are confirmation-gated `delete_file` / maintenance-workflow
  actions — always honor the gate.
- Never propose deleting `.git`, source files, documents, or anything not on the
  regenerable-candidate list.
- Caches (`__pycache__`, `.pytest_cache`, `.mypy_cache`) are safe to remove;
  `node_modules` and `build`/`dist` are regenerable but cost time/network to
  rebuild — flag that so the user chooses knowingly.
- If unsure whether something is regenerable, leave it out and ask.
