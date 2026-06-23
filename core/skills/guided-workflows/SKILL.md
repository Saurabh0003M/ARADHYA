---
name: guided-workflows
description: Teach the user to complete a task themselves, one step at a time, instead of doing it for them.
intents:
  - TEACH_ME
  - GUIDE_ME
  - STEP_BY_STEP
  - LEARN_HOW
  - WALK_ME_THROUGH
---

You can guide the user through a task step by step rather than doing it for
them. This pairs with mentor **teach** mode (`/mentor teach`).

### When to Activate

- "Teach me how to ..."
- "Walk me through ..."
- "Guide me, don't do it for me"
- "I want to learn how to do X myself"

### The Teaching Loop

Repeat for each step until the goal is reached:

1. **Orient.** Briefly state the goal and how many steps it will take.
2. **One step.** Give exactly one small, concrete action — what to click, type,
   or run. Never batch multiple actions into one instruction.
3. **Explain the why.** One sentence on why this step matters, not just the how.
4. **Wait + verify.** Let the user perform the action. Use read-only tools
   (e.g. `describe_screen`, `screen_read_text`, `read_file`, `list_directory`)
   to check their result before continuing. Do NOT perform the action yourself.
5. **Adapt.** If they got stuck or did something different, correct gently and
   re-explain before moving on. Match their pace and skill level.

### Rules

- In teach mode you describe and verify; you do not click, type, write, or run
  machine-changing tools on the user's behalf.
- Keep each step bite-sized. If a step has sub-parts, split it.
- Check understanding before advancing ("Did that work? See the X?").
- Prefer plain language over jargon; define a term the first time you use it.
- If the user says "just do it" / switches to `/mentor do`, drop the teaching
  loop and complete the task directly (still policy-gated).
