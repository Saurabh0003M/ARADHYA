---
description: Run pytest (targeted by default, full suite in background with "all")
argument-hint: [path | all]
---

Run the test suite.

Arguments given: `$ARGUMENTS`

- If no argument was given, run the default targeted suite in the foreground:
  `pytest tests/unit -q`
- If the argument is `all`, run the FULL suite in the background
  (`run_in_background: true`, it takes ~2 minutes) and report results when it
  completes: `pytest -q`
- Otherwise treat the argument as a path/selector and run it in the foreground:
  `pytest $ARGUMENTS -q`

Coverage is opt-in (`pytest --cov=src --cov=core --cov-report=html`); never
add coverage flags to routine runs.

pytest exit code 1 with a printed failure list is a NORMAL test failure — read
the failures and report them. It is not a tool or environment error.
