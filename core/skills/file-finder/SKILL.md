---
name: file-finder
description: Advanced file search — find files by name, content, type, date, and size across all configured roots.
intents:
  - FIND_FILE
  - SEARCH_FILES
  - LOCATE_FILE
  - FILE_STATS
---

You can search for files across the user's machine using multiple criteria.

### When to Activate

This skill triggers when the user asks:
- "Find all Python files"
- "Where is my resume?"
- "Search for files containing 'TODO'"
- "What are the largest files on my disk?"
- "Show files modified today"
- "Find duplicate files"

### Search Capabilities

1. **By name** — Exact or fuzzy filename matching, including wildcards (`*.py`, `report*`).
2. **By content** — Search inside text files for specific patterns (like `grep`).
3. **By type** — Filter by extension (`.py`, `.md`, `.pdf`, `.docx`, etc.).
4. **By date** — Find files modified in the last N hours/days.
5. **By size** — Find files larger/smaller than a threshold.
6. **By project** — Scope search to a specific project root.

### Tools to Use

- `run_command` with PowerShell:
  - Name search: `Get-ChildItem -Path <root> -Recurse -Filter "<pattern>" -File`
  - Content search: `Select-String -Path <root>\*.* -Pattern "<text>" -Recurse`
  - Date search: `Get-ChildItem -Recurse | Where-Object { $_.LastWriteTime -gt (Get-Date).AddDays(-1) }`
  - Size search: `Get-ChildItem -Recurse | Where-Object { $_.Length -gt 10MB } | Sort-Object Length -Descending`

### Output Format

Present results as a clean list with:
- Full path
- Size (human-readable)
- Last modified date
- Preview of matching content (for content searches)

Limit to 20 results by default. Mention total count if truncated.

### Safety Rules

- All searches are read-only. No confirmation needed.
- Skip system directories, `.git`, `node_modules`, `__pycache__`, and `venv` by default.
- Never read binary files for content searches.
