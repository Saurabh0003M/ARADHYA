# Stage 0 — measurements

Numbers taken on the target machine while executing the Stage 0 checklist from
`2026-08-07-decision-memo.md`. Recorded because two of the memo's rulings are
*conditional on measurement*, and a condition nobody measures is a decision
nobody made.

**Machine:** Windows 11, Intel Core Ultra 5 125H, no dGPU, 15.5 GB RAM.
**Date:** 2026-08-07. **Venv:** `./venv` (Python 3.10.11).

---

## Browser leg — CDP attach (memo §4 amendment 1)

Real Edge (`msedge.exe`, `C:\Program Files (x86)\Microsoft\Edge\Application`),
launched by `browser_open` with `--remote-debugging-port=9222` and ARADHYA's own
persistent profile.

| Operation | Time |
|---|---|
| `browser_open` — cold (launch Edge, then attach) | 2.6 s |
| `browser_open` — attach to an already-running browser | 0.46 s |
| `browser_navigate` to a local file | 0.08 s |
| `browser_navigate` to `example.com` | 0.26 s |
| `browser_read` — element map, local fixture (8 elements) | 0.02 s |
| `browser_read` — element map, `duckduckgo.com` (156 elements) | 0.8 s incl. navigation |

Element-map quality, on the fixture and on real sites:

- Accessible name comes from the label, not `innerText`. A `<select>` is no
  longer named after its own options (`"Free Pro"` → `""` with `value='Free'`).
- Password field values are **never** returned. Hidden inputs are excluded.
- Landmark/container roles (`list`, `listitem`, `navigation`, `region`, …) are
  excluded: they are never click targets and their accessible name is the
  concatenated text of everything inside them. On duckduckgo.com this took the
  map from 170 entries to **156 actionable ones** with no useful loss.

**Conclusion:** the CDP path is comfortably fast enough. No reversal condition
triggered (the memo's reversal is "a CDP-attach driver failing on a target that
selenium handles" — nothing observed).

**Constraint found, not in the reports:** Chrome 136+ and current Edge refuse
`--remote-debugging-port` when the browser uses its *default* user-data-dir. So
"attach to the user's everyday logged-in profile" is impossible by design, at
any price. The honest equivalent, and what ships, is a persistent ARADHYA
profile at `~/.aradhya/browser-profile` that the user signs into once.

---

## Desktop leg — UI Automation (memo §4 amendment 2)

Amendment 2 says CacheRequest scoping is "day-one, not an optimisation", citing
P3-gemini's >8 s full-tree walk on a 1,000-element app vs <50 ms cached, and the
checklist made it conditional: *add it now if a scoped lookup takes >~1 s.*

Measured, all five tools against three real apps (Notepad, Calculator, File
Explorer) plus Edge and WhatsApp:

| Operation | Controls | Time |
|---|---|---|
| `list_windows` (7–8 top-level windows) | — | 0.18 s |
| `list_window_controls` Notepad | 70 | 0.12 s |
| `list_window_controls` Calculator | 83 | 0.12 s |
| `list_window_controls` File Explorer (site-packages, 259 controls) | 259 | 0.37 s |
| `list_window_controls` Edge | 125 | 0.24 s |
| `list_window_controls` WhatsApp | 44 | 0.14 s |
| `focus_window` Notepad | — | 0.57 s |
| `set_control_text` Notepad | — | 0.58 s |
| `invoke_control` Calculator | — | 0.62 s |

Cost breakdown on the largest window available: **0.70 ms/control** to walk the
tree, **1.35 ms/control** when the five properties are read as well. All five
tools succeeded on all three apps.

**Ruling: CacheRequest batching is NOT added at Stage 0.** The stated trigger
(>~1 s) is not met by any operation, with the slowest at 0.62 s and the largest
scoped lookup at 0.37 s. The research figure does not reproduce here —
`uiautomation`'s `WalkControl` is already ~100× faster than the >8 s P3-gemini
reports for a comparable walk.

**Re-open when** a target app produces a scoped lookup over ~1 s. At the
measured 1.35 ms/control that is roughly a **750-element window**; Office apps
and Teams are the likely first offenders. The measurement to repeat is
`tests/integration/test_desktop_uia_live.py::test_scoped_control_lookup_is_within_budget`,
which fails with this exact instruction when the budget is breached.

### The real defect the desktop leg had

Chasing the timing found something worse than slowness. `desktop_control.py`
called `control.GetInvokePattern()` unguarded, but `uiautomation` defines that
method **only on control classes that support the Invoke pattern**. On an
`EditControl`, `TextControl`, `PaneControl`, `GroupControl` or `ImageControl` it
raises `AttributeError` — which the per-control `except Exception: continue`
swallowed, **deleting the entire control from the map**.

Measured on one File Explorer window: **188 of 299 controls silently dropped
(63%)**, and 100 of those 188 were `EditControl` — every text field. So the tool
the model uses to discover what it can type into was hiding every box it could
type into.

After the fix (probe the pattern with `getattr`, and record `editable` from the
Value pattern alongside `invokable`):

| Window | Controls before | Controls after | Editable now visible |
|---|---|---|---|
| Notepad | 27 | 70 | `DocumentControl "Text editor"` |
| Edge | 91 | 125 | `EditControl "Address and search bar"`, the page's form fields |
| File Explorer | 102 | 259 | 124 |
| WhatsApp | 31 | 44 | 1 |

Timings above are all post-fix, so the budget headroom already includes the ~2.5×
larger maps.

Two smaller fixes in the same path: control names are flattened to one line
(Notepad's status bar is literally named `"Line 1,\nColumn 1"`, which forged an
extra row in a one-control-per-line listing) and whitespace-only names are
dropped.

---

## MCP server (memo §1)

`src/aradhya/mcp_server.py`, run over real stdio with a real MCP client
(`mcp` 1.27.1). **62 tools exposed**, including all five desktop tools and all
twelve browser tools.

Verified end to end against a server started **with no confirmation gate**:

| Call | Result |
|---|---|
| `list_windows` | ran, returned 8 windows |
| `list_window_controls("Calculator")` | ran, returned 83 controls |
| `run_command {"command": "echo pwned"}` | **denied, `isError: true`**, did not execute |
| `invoke_control(Calculator, Nine)` | **denied, `isError: true`**, did not execute |
| `write_file` | **denied, `isError: true`**, did not execute |
| `set_control_text` | **denied, `isError: true`**, did not execute |

Two design points worth keeping:

- **A denial is `isError: true`, not a successful result containing a refusal.**
  A harness reading `isError: false` reports the task done. The MCP SDK sets the
  flag from a raised exception, so the transport edge raises while the testable
  core still returns `(succeeded, output)`.
- **Constructing the server with `policy=None` raises.** `execute_tool` runs
  everything unchecked without a policy, and quietly exposing an ungated machine
  to whatever process is on the other end of the pipe is not a state worth
  supporting.

`tests/unit/test_mcp_server.py` also asserts the MCP tool set is **identical** to
`AradhyaAssistant._build_tool_registry_from_policy`'s, so a capability cannot
exist locally and silently vanish when the front end changes.
