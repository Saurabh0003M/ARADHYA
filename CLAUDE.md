@AGENTS.md

## Environment (Windows — read first)
- Shell is Windows PowerShell 5.1. NEVER append `2>&1` to native commands (git, python, gh) — it wraps stderr lines in ErrorRecords and reports success as failure. For anything needing pipes into stdin, heredocs, or multi-line strings, use the Bash tool instead.
- The console is cp1252. Any Python that prints non-ASCII must run with `PYTHONUTF8=1` (already set in .claude/settings.json env). Write large or non-ASCII output to a UTF-8 file and Read it; never dump blobs to the console.
- `gh` is installed at `C:\Program Files\GitHub CLI\gh.exe` and on PATH. Auth is via `gh auth login` keyring. NEVER use the `GITHUB_TOKEN` env var — if it is set it is stale and shadows gh auth; run gh as `$env:GITHUB_TOKEN=$null; gh ...` until the var is removed from the user environment.
- Never print environment variables whose names contain KEY, TOKEN, or SECRET. To verify one exists, print its length only.

## Tests
- Targeted run (default after every change): `pytest tests/unit/test_<area>.py --override-ini="addopts=" -q`
- Never run bare `pytest`: pyproject addopts force coverage + HTML report (slow; requires pytest-cov).
- The full suite takes ~2 minutes — run it in the background, and only at milestones (before a commit), not after every edit.
- pytest exit code 1 with a printed failure list is a NORMAL test failure: read the failures. It is not a tool or environment error.

## Workflow
- Before starting any task: `git fetch origin` and `gh pr list --state open`. Never re-implement work already claimed by an open PR. One agent/PR per area of the codebase at a time.
- Commit after each completed backlog item (once tests are green), before starting the next. Never batch a whole day's work into one uncommitted tree.
- Long deliverables (audits, reports, plans): append to a file incrementally as you work, then summarize in chat. Never hold a long deliverable only in your final message.
- Before writing code that references attributes of an existing class or dataclass, Read its definition first.
- The repo contains `.tmp/` junk and `Hosts/` snapshot repos; scope searches to `src/`, `tests/`, `docs/`, `core/`.
