"""P1-8: desktop control via UI Automation.

Pure matching/formatting plus tool behavior through a fake backend (no real
desktop). Also checks the real backend degrades when uiautomation is absent.
"""

from __future__ import annotations

import pytest

from src.aradhya import desktop_control
from src.aradhya.desktop_control import (
    UIAutomationBackend,
    UIControl,
    UIWindow,
    find_control,
    find_window,
    format_controls,
    format_windows,
    set_desktop_backend,
)
from src.aradhya.tools import desktop_tools


def _control(name, ctype="Button", enabled=True, invokable=True):
    return UIControl(name=name, control_type=ctype, enabled=enabled, invokable=invokable)


# ── pure matching ──────────────────────────────────────────────────────

def test_find_control_exact_case_insensitive():
    controls = [_control("Save"), _control("Save As")]
    assert find_control(controls, "save").name == "Save"


def test_find_control_substring_fallback():
    controls = [_control("Save As")]
    assert find_control(controls, "save").name == "Save As"


def test_find_control_prefers_invokable_enabled():
    controls = [
        _control("OK", ctype="Text", invokable=False),  # inert label
        _control("OK", ctype="Button", invokable=True),  # real button
    ]
    match = find_control(controls, "OK")
    assert match.control_type == "Button"


def test_find_control_none_when_no_match():
    assert find_control([_control("Cancel")], "submit") is None
    assert find_control([_control("Cancel")], "") is None


def test_find_window_exact_then_substring():
    windows = [UIWindow("Untitled - Notepad"), UIWindow("Calculator")]
    assert find_window(windows, "calculator").title == "Calculator"
    assert find_window(windows, "notepad").title == "Untitled - Notepad"
    assert find_window(windows, "photoshop") is None


# ── formatting ─────────────────────────────────────────────────────────

def test_format_windows():
    assert "No top-level windows" in format_windows([])
    out = format_windows([UIWindow("Calculator")])
    assert "1 window(s):" in out
    assert "Calculator" in out


def test_format_controls_flags_and_limit():
    controls = [_control(f"b{i}") for i in range(70)]
    controls.append(_control("Disabled", enabled=False, invokable=False))
    out = format_controls(controls, limit=60)
    assert "control(s):" in out
    assert "... and" in out  # truncated


# ── tools via fake backend ─────────────────────────────────────────────

class FakeBackend:
    def __init__(self, available=True, windows=None, controls=None):
        self._available = available
        self._windows = windows or []
        self._controls = controls or {}
        self.invoked = []
        self.values = []
        self.focused = []

    def available(self):
        return self._available

    def list_windows(self):
        return self._windows

    def list_controls(self, window_title, max_controls=200):
        return self._controls.get(window_title, [])

    def invoke(self, window_title, control_name):
        self.invoked.append((window_title, control_name))
        return True, f"Invoked '{control_name}' in '{window_title}'."

    def set_value(self, window_title, control_name, text):
        self.values.append((window_title, control_name, text))
        return True, f"Set '{control_name}'."

    def focus_window(self, window_title):
        self.focused.append(window_title)
        return True, f"Focused '{window_title}'."


@pytest.fixture(autouse=True)
def _clear_backend():
    set_desktop_backend(None)
    yield
    set_desktop_backend(None)


def test_list_windows_tool():
    set_desktop_backend(FakeBackend(windows=[UIWindow("Calculator")]))
    out = desktop_tools.list_windows()
    assert "Calculator" in out


def test_list_window_controls_tool():
    backend = FakeBackend(controls={"Calc": [_control("Equals")]})
    set_desktop_backend(backend)
    out = desktop_tools.list_window_controls("Calc")
    assert "Equals" in out


def test_list_controls_tool_when_window_missing():
    set_desktop_backend(FakeBackend(controls={}))
    out = desktop_tools.list_window_controls("Nope")
    assert "No window matching" in out


def test_invoke_control_tool():
    backend = FakeBackend()
    set_desktop_backend(backend)
    out = desktop_tools.invoke_control("Calc", "Equals")
    assert backend.invoked == [("Calc", "Equals")]
    assert "Invoked" in out


def test_set_control_text_tool():
    backend = FakeBackend()
    set_desktop_backend(backend)
    desktop_tools.set_control_text("Form", "Email", "me@example.com")
    assert backend.values == [("Form", "Email", "me@example.com")]


def test_focus_window_tool():
    backend = FakeBackend()
    set_desktop_backend(backend)
    desktop_tools.focus_window("Calculator")
    assert backend.focused == ["Calculator"]


def test_tools_report_unavailable_backend():
    set_desktop_backend(FakeBackend(available=False))
    assert "uiautomation" in desktop_tools.list_windows()
    assert "uiautomation" in desktop_tools.invoke_control("w", "c")
    assert "uiautomation" in desktop_tools.set_control_text("w", "c", "t")


def test_all_desktop_tools_registered():
    names = {t._tool_def.name for t in desktop_tools.ALL_DESKTOP_TOOLS}
    assert names == {
        "list_windows",
        "list_window_controls",
        "invoke_control",
        "set_control_text",
        "focus_window",
    }


# ── real backend degrades without uiautomation ─────────────────────────

def test_real_backend_unavailable_without_dependency():
    # uiautomation is not installed in CI/dev here; the backend must say so
    # and never raise.
    backend = UIAutomationBackend()
    if not backend.available():
        assert backend.list_windows() == []
        ok, msg = backend.invoke("any", "thing")
        assert ok is False
        assert "uiautomation" in msg
