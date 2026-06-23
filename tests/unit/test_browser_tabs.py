"""P1-5: multi-tab browser tools.

Uses a fake Selenium driver (no real browser) to exercise new_tab / list_tabs /
switch_tab and the no-session and bad-index paths."""

from __future__ import annotations

import pytest

from src.aradhya.tools import browser_tools
from src.aradhya.tools.browser_tools import (
    browser_list_tabs,
    browser_new_tab,
    browser_switch_tab,
)


class _FakeSwitchTo:
    def __init__(self, driver: "FakeDriver") -> None:
        self.driver = driver

    def new_window(self, _kind: str) -> None:
        handle = f"h{len(self.driver.tabs) + 1}"
        self.driver.tabs.append({"handle": handle, "url": "about:blank", "title": "New Tab"})
        self.driver.current = handle

    def window(self, handle: str) -> None:
        self.driver.current = handle


class FakeDriver:
    def __init__(self) -> None:
        self.tabs = [{"handle": "h1", "url": "https://start", "title": "Start"}]
        self.current = "h1"
        self.switch_to = _FakeSwitchTo(self)

    @property
    def window_handles(self):
        return [t["handle"] for t in self.tabs]

    @property
    def current_window_handle(self):
        return self.current

    def _cur(self):
        return next(t for t in self.tabs if t["handle"] == self.current)

    @property
    def title(self):
        return self._cur()["title"]

    @property
    def current_url(self):
        return self._cur()["url"]

    def get(self, url: str) -> None:
        cur = self._cur()
        cur["url"] = url
        cur["title"] = f"Title of {url}"


@pytest.fixture
def fake_driver(monkeypatch):
    driver = FakeDriver()
    monkeypatch.setattr(browser_tools, "_active_driver", driver)
    monkeypatch.setattr(browser_tools.time, "sleep", lambda *_: None)
    return driver


# ── no session ─────────────────────────────────────────────────────────

def test_tools_need_a_session(monkeypatch):
    monkeypatch.setattr(browser_tools, "_active_driver", None)
    assert "No browser session" in browser_new_tab()
    assert "No browser session" in browser_list_tabs()
    assert "No browser session" in browser_switch_tab(1)


# ── new tab ────────────────────────────────────────────────────────────

def test_new_tab_opens_and_switches(fake_driver):
    out = browser_new_tab()
    assert "Opened tab 2 of 2" in out
    assert fake_driver.current == "h2"


def test_new_tab_navigates_when_url_given(fake_driver):
    out = browser_new_tab("https://example.com")
    assert "https://example.com" in out
    assert fake_driver.current_url == "https://example.com"


# ── list tabs ──────────────────────────────────────────────────────────

def test_list_tabs_shows_all_and_restores_focus(fake_driver):
    browser_new_tab("https://example.com")  # now on tab 2
    browser_new_tab("https://other.com")    # now on tab 3
    focus_before = fake_driver.current

    out = browser_list_tabs()

    assert "3 open tab(s):" in out
    assert "1. Start" in out
    assert "https://example.com" in out
    assert "https://other.com" in out
    assert "(current)" in out
    # listing must not change which tab is focused
    assert fake_driver.current == focus_before


# ── switch tab ─────────────────────────────────────────────────────────

def test_switch_tab_changes_focus(fake_driver):
    browser_new_tab("https://example.com")  # tab 2
    out = browser_switch_tab(1)
    assert "Switched to tab 1" in out
    assert fake_driver.current == "h1"
    assert fake_driver.current_url == "https://start"


def test_switch_tab_rejects_bad_index(fake_driver):
    out = browser_switch_tab(9)
    assert "does not exist" in out
    assert fake_driver.current == "h1"  # unchanged


def test_tabs_registered_in_all_browser_tools():
    names = {t._tool_def.name for t in browser_tools.ALL_BROWSER_TOOLS}
    assert {"browser_new_tab", "browser_list_tabs", "browser_switch_tab"} <= names
