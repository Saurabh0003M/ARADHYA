---
description: Push the current branch and open a GitHub PR (refuses on main)
argument-hint: [PR title]
---

Create a pull request for the current branch. Follow these steps in order and
stop at the first failure:

1. **Refuse on main.** Run `git rev-parse --abbrev-ref HEAD`. If the branch is
   `main` (or `master`), STOP immediately and tell the user to create a feature
   branch first. Never push to or open a PR from main.
2. **Verify gh auth.** Run `gh auth status`. Auth comes from the
   `GITHUB_TOKEN` env var (there is no keyring auth — never unset or null the
   var, and never print it). If auth fails, STOP and ask the user to refresh
   the token.
3. **Push the branch:**
   `git push -u origin HEAD`
4. **Create the PR** against `main`:
   `gh pr create --base main --title "..." --body "..."`
   Use `$ARGUMENTS` as the title if given, otherwise derive the title from the
   branch's commits. In the body, summarize what changed and why (bullets),
   mention how it was tested, and end with:
   🤖 Generated with [Claude Code](https://claude.com/claude-code)
5. **Print the PR URL** returned by `gh pr create` as the final line.
