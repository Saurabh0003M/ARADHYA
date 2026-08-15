"""P1-5: multi-tab browser tools, on the CDP backend.

Uses a fake backend (no real browser) to exercise new_tab / list_tabs /
switch_tab and the no-session and bad-index paths. The fake models what a real
Playwright ``BrowserContext`` gives us — an ordered list of pages and one
current page — so the tabs really are 1-based in open order.
"""

from __future__ import annotations

import pytest

from src.aradhya.browser_cdp import set_browser_backend
from src.aradhya.tools import browser_tools
from src.aradhya.tools.browser_tools import (
    browser_list_tabs,
    browser_new_tab,
    browser_switch_tab,
)


class FakeBackend:
    """Enough of CdpBrowserBackend to drive the tab tools."""

    NO_SESSION = "No browser session. Call browser_open() first."

    def __init__(self, attached: bool = True) -> None:
        self.attached_flag = attached
        self.pages = [{"title": "Start", "url": "https://start"}]
        self.current = 0

    def available(self) -> bool:
        return True

    def attached(self) -> bool:
        return self.attached_flag

    def list_pages(self):
        if not self.attached_flag:
            return self.NO_SESSION
        return [
            (page["title"], page["url"], index == self.current)
            for index, page in enumerate(self.pages)
        ]

    def new_page(self, url: str = ""):
        if not self.attached_flag:
            return False, self.NO_SESSION
        page = {"title": "New Tab", "url": "about:blank"}
        if url:
            page = {"title": f"Title of {url}", "url": url}
        self.pages.append(page)
        self.current = len(self.pages) - 1
        suffix = f" at {url} (title: {page['title']!r})" if url else ""
        return True, f"Opened tab {self.current + 1}{suffix}."

    def switch_page(self, index: int):
        if not self.attached_flag:
            return False, self.NO_SESSION
        if index < 1 or index > len(self.pages):
            return False, f"Tab {index} does not exist. There are {len(self.pages)} tab(s)."
        self.current = index - 1
        page = self.pages[self.current]
        return True, f"Switched to tab {index}: {page['title']!r} — {page['url']}"


@pytest.fixture
def fake_backend():
    backend = FakeBackend()
    set_browser_backend(backend)
    yield backend
    set_browser_backend(None)


# ── no session ─────────────────────────────────────────────────────────

def test_tools_need_a_session():
    set_browser_backend(FakeBackend(attached=False))
    try:
        assert "No browser session" in browser_new_tab()
        assert "No browser session" in browser_list_tabs()
        assert "No browser session" in browser_switch_tab(1)
    finally:
        set_browser_backend(None)


# ── new tab ────────────────────────────────────────────────────────────

def test_new_tab_opens_and_switches(fake_backend):
    out = browser_new_tab()
    assert "Opened tab 2" in out
    assert fake_backend.current == 1


def test_new_tab_navigates_when_url_given(fake_backend):
    out = browser_new_tab("https://example.com")
    assert "https://example.com" in out
    assert fake_backend.pages[fake_backend.current]["url"] == "https://example.com"


# ── list tabs ──────────────────────────────────────────────────────────

def test_list_tabs_shows_all_and_marks_current(fake_backend):
    browser_new_tab("https://example.com")  # now on tab 2
    browser_new_tab("https://other.com")    # now on tab 3
    focus_before = fake_backend.current

    out = browser_list_tabs()

    assert "3 open tab(s):" in out
    assert "1. Start" in out
    assert "https://example.com" in out
    assert "https://other.com" in out
    assert "(current)" in out
    # listing must not change which tab is focused
    assert fake_backend.current == focus_before


# ── switch tab ─────────────────────────────────────────────────────────

def test_switch_tab_changes_focus(fake_backend):
    browser_new_tab("https://example.com")  # tab 2
    out = browser_switch_tab(1)
    assert "Switched to tab 1" in out
    assert fake_backend.current == 0
    assert fake_backend.pages[fake_backend.current]["url"] == "https://start"


def test_switch_tab_rejects_bad_index(fake_backend):
    out = browser_switch_tab(9)
    assert "does not exist" in out
    assert fake_backend.current == 0  # unchanged


def test_tabs_registered_in_all_browser_tools():
    names = {t._tool_def.name for t in browser_tools.ALL_BROWSER_TOOLS}
    assert {"browser_new_tab", "browser_list_tabs", "browser_switch_tab"} <= names
