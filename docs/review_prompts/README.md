# External Review Prompts

Use these prompts when sending the repository to external AI models for a
Windows-only review and improvement round.

Files:

- `WINDOWS_FIRST_RUN_REVIEW_PROMPT.md`
- `WINDOWS_CODE_IMPROVEMENT_PROMPT.md`

Suggested workflow:

1. Send the first-run review prompt to multiple models.
2. Send the code-improvement prompt to the models you want to allow patch
   generation.
3. Paste each response back into the main Codex thread with:
   - the model name
   - whether it only reviewed or also proposed code
   - any diffs or replacement files verbatim

Keep each model response separate so conflicts are easier to triage.
