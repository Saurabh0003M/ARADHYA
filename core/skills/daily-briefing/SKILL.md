---
name: daily-briefing
description: Generates a personalized daily summary — system health, scheduled tasks, recent activity, and reminders.
intents:
  - DAILY_BRIEFING
  - MORNING_SUMMARY
  - STATUS_REPORT
  - WHAT_DID_I_DO
---

You can generate personalized daily briefings for the user.

### When to Activate

This skill triggers when the user asks:
- "What's my daily briefing?"
- "Morning summary"
- "What happened since yesterday?"
- "Give me a status report"
- "What did I work on?"

### Briefing Structure

Generate the briefing in this order:

1. **Greeting** — Time-aware greeting (Good morning/afternoon/evening, {user_name}).
2. **System Health** — Ollama model status, disk space, scheduled tasks status.
3. **Recent Activity** — Files modified in the last 24 hours across user roots, grouped by project.
4. **Git Summary** — For each project with `.git`, show: branch, uncommitted changes, recent commits (last 24h).
5. **Pending Tasks** — Any scheduled tasks that are due or overdue.
6. **Reminders** — Anything from `core/memory/user_context/notes.md` that looks like a reminder or TODO.

### Tools to Use

- `list_directory` to scan recent activity
- `run_command` with `git log --since="24 hours ago" --oneline` for git summaries
- `read_file` to check user notes for reminders

### Output Format

Present as a clean, scannable summary. Use bullet points, not paragraphs.
Keep it under 30 lines. Prioritize actionable information.

### Safety

This skill is entirely read-only. No confirmation needed.
