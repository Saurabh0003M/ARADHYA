---
description: Run pytest with the repo's slow coverage addopts disabled
argument-hint: [path | all]
---

Run the test suite with coverage addopts overridden (bare `pytest` triggers
coverage + HTML report from pyproject addopts — never run it).

Arguments given: `$ARGUMENTS`

- If no argument was given, run the default targeted suite in the foreground:
  `pytest tests/unit --override-ini="addopts=" -q`
- If the argument is `all`, run the FULL suite in the background
  (`run_in_background: true`, it takes ~2 minutes) and report results when it
  completes: `pytest --override-ini="addopts=" -q`
- Otherwise treat the argument as a path/selector and run it in the foreground:
  `pytest $ARGUMENTS --override-ini="addopts=" -q`

pytest exit code 1 with a printed failure list is a NORMAL test failure — read
the failures and report them. It is not a tool or environment error.
