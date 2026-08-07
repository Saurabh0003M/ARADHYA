"""Live UI Automation tests — the real desktop, no fake backend.

These assert the desktop leg can actually read the machine, and they carry the
timing budget from the decision memo §4 amendment 2 (a scoped lookup should
stay well under ~1 s; if it does not, UIA CacheRequest batching is owed).

Read-only by design. Nothing here invokes a control or types into one — a test
suite must not click things in the user's session. The write paths were
verified by hand during Stage 0 and are recorded in the Stage 0 note.

    venv\\Scripts\\python.exe -m pytest tests/integration -q
"""

from __future__ import annotations

import time

import pytest

from src.aradhya.desktop_control import UIAutomationBackend, format_controls

pytestmark = pytest.mark.effector("uiautomation")

#: A scoped lookup over one window must stay inside this. Measured on a Core
#: Ultra 5 125H: 0.12-0.37 s across Notepad, Calculator, Edge, File Explorer
#: and WhatsApp, so the headroom is real rather than nominal.
LOOKUP_BUDGET_SECONDS = 1.0


@pytest.fixture(scope="module")
def backend():
    real = UIAutomationBackend()
    if not real.available():
        pytest.skip("uiautomation did not import on this machine")
    return real


@pytest.fixture(scope="module")
def a_window(backend):
    windows = backend.list_windows()
    if not windows:
        pytest.skip("no top-level windows to inspect")
    # Prefer a window with a decent control count so the assertions mean something.
    best = max(windows, key=lambda w: len(backend.list_controls(w.title, 400)))
    return best


def test_list_windows_sees_the_real_desktop(backend):
    windows = backend.list_windows()
    assert windows, "expected at least one top-level window"
    assert all(window.title.strip() for window in windows)


def test_list_windows_is_fast(backend):
    start = time.time()
    backend.list_windows()
    assert time.time() - start < LOOKUP_BUDGET_SECONDS


def test_scoped_control_lookup_is_within_budget(backend, a_window):
    start = time.time()
    controls = backend.list_controls(a_window.title, max_controls=100000)
    elapsed = time.time() - start
    assert controls, f"no controls found in {a_window.title!r}"
    assert elapsed < LOOKUP_BUDGET_SECONDS, (
        f"scoped lookup of {a_window.title!r} took {elapsed:.2f}s for "
        f"{len(controls)} controls — over the {LOOKUP_BUDGET_SECONDS}s budget. "
        "Decision memo §4 amendment 2: add UIA CacheRequest batching."
    )


def test_controls_without_an_invoke_pattern_are_still_listed(backend, a_window):
    """The regression: an EditControl has no GetInvokePattern attribute, and
    the AttributeError used to delete the control from the map entirely."""
    controls = backend.list_controls(a_window.title, max_controls=100000)
    types = {control.control_type for control in controls}
    non_invokable = [c for c in controls if not c.invokable]
    assert non_invokable, (
        f"every control in {a_window.title!r} came back invokable — the "
        f"pattern probe is dropping the rest again. Types seen: {sorted(types)}"
    )


def test_control_names_are_single_line(backend, a_window):
    """format_controls prints one control per line; Notepad's status bar is
    literally named "Line 1,\\nColumn 1"."""
    controls = backend.list_controls(a_window.title, max_controls=100000)
    assert all("\n" not in control.name for control in controls)
    rendered = format_controls(controls, limit=100000)
    # header + one line per control (capped by limit)
    assert len(rendered.splitlines()) == len(controls) + 1


def test_no_control_is_listed_with_a_blank_name(backend, a_window):
    controls = backend.list_controls(a_window.title, max_controls=100000)
    assert all(control.name.strip() for control in controls)


def test_missing_window_returns_empty_not_an_error(backend):
    assert backend.list_controls("no such window exists anywhere") == []
    ok, message = backend.focus_window("no such window exists anywhere")
    assert ok is False
    assert "No window matching" in message
