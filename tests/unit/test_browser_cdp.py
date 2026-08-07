"""The CDP browser backend: element maps, endpoint discovery, tool contract.

The pure parts (parsing and formatting an element map) are tested without a
browser. The parts that need a real browser are marked ``@pytest.mark.effector``
so they skip-and-report rather than pass on a mock.
"""

from __future__ import annotations

import pytest

from src.aradhya.browser_cdp import (
    DEFAULT_DEBUG_PORT,
    NOT_PORTED_MESSAGE,
    CdpBrowserBackend,
    PageElement,
    PageSnapshot,
    cdp_endpoint,
    find_browser_executable,
    format_snapshot,
    parse_elements,
    set_browser_backend,
)
from src.aradhya.tools import browser_tools


# ── element map parsing ────────────────────────────────────────────────


def test_parse_elements_assigns_stable_refs():
    elements = parse_elements(
        [
            {"role": "button", "name": "Sign in", "id": "login"},
            {"role": "textbox", "name": "Email", "value": "a@b.c"},
        ]
    )
    assert [e.ref for e in elements] == ["e1", "e2"]
    assert elements[0].role == "button"
    assert elements[1].value == "a@b.c"


def test_parse_elements_tolerates_missing_fields():
    (element,) = parse_elements([{}])
    assert element.ref == "e1"
    assert element.role == "element"
    assert element.name == ""
    assert element.enabled is True


def test_parse_elements_keeps_disabled_state():
    (element,) = parse_elements([{"role": "button", "name": "Pay", "enabled": False}])
    assert element.enabled is False


# ── element map formatting ─────────────────────────────────────────────


def test_format_snapshot_is_a_map_not_prose():
    snapshot = PageSnapshot(
        title="Login",
        url="https://example.com/login",
        elements=(
            PageElement(ref="e1", role="textbox", name="Email", element_id="email"),
            PageElement(ref="e2", role="button", name="Sign in", enabled=False),
            PageElement(ref="e3", role="link", name="Help", href="/help"),
        ),
    )
    out = format_snapshot(snapshot)

    assert "Page: Login" in out
    assert "URL: https://example.com/login" in out
    assert "3 interactive element(s):" in out
    # role, accessible name and id are all addressable
    assert '[e1] textbox "Email" #email' in out
    assert "[disabled]" in out
    assert "-> /help" in out


def test_format_snapshot_reports_an_empty_page_honestly():
    out = format_snapshot(PageSnapshot(title="Blank", url="about:blank"))
    assert "No interactive elements found" in out


def test_format_snapshot_truncates_with_a_count():
    elements = tuple(
        PageElement(ref=f"e{i}", role="link", name=f"Item {i}") for i in range(1, 91)
    )
    out = format_snapshot(PageSnapshot("Big", "https://x", elements), limit=10)
    assert "and 80 more" in out


# ── endpoint discovery ─────────────────────────────────────────────────


def test_cdp_endpoint_returns_empty_when_nothing_listens():
    # Port 1 is never a DevTools endpoint; discovery must fail quietly.
    assert cdp_endpoint(port=1, timeout=0.2) == ""


def test_find_browser_executable_returns_a_pair():
    path, name = find_browser_executable()
    assert isinstance(path, str) and isinstance(name, str)
    if path:
        assert name in {"Edge", "Chrome"}


# ── tool contract: names, flags, and honest "not ported" ───────────────


EXPECTED_TOOLS = {
    "browser_open",
    "browser_navigate",
    "browser_click",
    "browser_type",
    "browser_read",
    "browser_screenshot",
    "browser_close",
    "browser_execute_js",
    "browser_submit",
    "browser_new_tab",
    "browser_list_tabs",
    "browser_switch_tab",
}

#: The flags the safety architecture is keyed on. Changing one silently
#: orphans the approved-rules allowlist and AgentLoop.DANGEROUS_TOOLS.
EXPECTED_CONFIRMATION = {
    "browser_open": True,
    "browser_navigate": True,
    "browser_click": True,
    "browser_type": True,
    "browser_read": False,
    "browser_screenshot": False,
    "browser_close": False,
    "browser_execute_js": True,
    "browser_submit": True,
    "browser_new_tab": True,
    "browser_list_tabs": False,
    "browser_switch_tab": False,
}


def test_backend_swap_kept_every_tool_name():
    names = {t._tool_def.name for t in browser_tools.ALL_BROWSER_TOOLS}
    assert names == EXPECTED_TOOLS


def test_backend_swap_kept_every_confirmation_flag():
    actual = {
        t._tool_def.name: t._tool_def.requires_confirmation
        for t in browser_tools.ALL_BROWSER_TOOLS
    }
    assert actual == EXPECTED_CONFIRMATION


@pytest.mark.parametrize(
    "tool, kwargs",
    [
        (browser_tools.browser_click, {"text": "Sign in"}),
        (browser_tools.browser_type, {"text": "hello"}),
        (browser_tools.browser_submit, {}),
        (browser_tools.browser_execute_js, {"script": "1+1"}),
        (browser_tools.browser_screenshot, {}),
    ],
)
def test_unported_tools_say_so_instead_of_pretending(tool, kwargs):
    """An unported tool must report, not silently no-op or half-work."""
    out = tool(**kwargs)
    assert "not yet ported" in out
    assert tool._tool_def.name in out


def test_unported_message_names_the_tool():
    assert "browser_click" in NOT_PORTED_MESSAGE.format(tool="browser_click")


# ── backend availability ───────────────────────────────────────────────


def test_backend_reports_unattached_state_clearly():
    backend = CdpBrowserBackend()
    assert backend.attached() is False
    ok, message = backend.navigate("https://example.com")
    assert ok is False
    assert "No browser session" in message
    assert "No browser session" in str(backend.snapshot())
    ok, message = backend.close()
    assert ok is False


def test_default_debug_port_is_the_documented_one():
    assert DEFAULT_DEBUG_PORT == 9222


@pytest.mark.effector("playwright")
def test_backend_available_when_playwright_is_installed():
    assert CdpBrowserBackend().available() is True


def teardown_module(module):  # pragma: no cover - hygiene
    set_browser_backend(None)
