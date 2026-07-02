---
description: Push the current branch and open a GitHub PR (refuses on main)
argument-hint: [PR title]
---

Create a pull request for the current branch. Follow these steps in order and
stop at the first failure:

1. **Refuse on main.** Run `git rev-parse --abbrev-ref HEAD`. If the branch is
   `main` (or `master`), STOP immediately and tell the user to create a feature
   branch first. Never push to or open a PR from main.
2. **Verify gh auth with the stale token shadowed.** Run:
   `$env:GITHUB_TOKEN=$null; gh auth status`
   If this fails, STOP and tell the user to run `gh auth login` once in a
   terminal — do not fall back to the `GITHUB_TOKEN` env var.
3. **Push the branch:**
   `$env:GITHUB_TOKEN=$null; git push -u origin HEAD`
4. **Create the PR** against `main`:
   `$env:GITHUB_TOKEN=$null; gh pr create --base main --title "..." --body "..."`
   Use `$ARGUMENTS` as the title if given, otherwise derive the title from the
   branch's commits. In the body, summarize what changed and why (bullets),
   mention how it was tested, and end with:
   🤖 Generated with [Claude Code](https://claude.com/claude-code)
5. **Print the PR URL** returned by `gh pr create` as the final line.
