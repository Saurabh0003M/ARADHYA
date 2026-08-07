"""Browser automation tools for the agent loop.

These tools give Aradhya the ability to control a web browser — navigating to
URLs, reading page structure, clicking elements, typing text — so it can do
things like "ring Kautilya's phone via Find My Device" or "reply on WhatsApp
Web".

**Backend: CDP attach, not Selenium.** Decision memo 2026-08-07 §4 amendment 1
rules WebDriver out of the plan ("obsolete for agents" in both P3 reports); the
driver lives in ``src/aradhya/browser_cdp.py`` and attaches over the Chrome
DevTools Protocol to a real Edge/Chrome. Tool **names and
``requires_confirmation`` flags are unchanged on purpose** — the approved-rules
allowlist persists per (tool, args), ``audit.jsonl`` records by name, and
``AgentLoop.DANGEROUS_TOOLS`` lists ``browser_click``/``browser_type``/
``browser_execute_js``. Only the backend moved.

Stage 0 ported ``browser_open``, ``browser_navigate``, ``browser_read``,
``browser_close`` and the three tab tools. ``browser_click``, ``browser_type``,
``browser_submit``, ``browser_execute_js`` and ``browser_screenshot`` still
exist, stay registered, stay confirmation-gated, and report that they are not
yet ported rather than silently doing nothing.

Dependencies:
- ``playwright`` — ``pip install playwright`` (no browser download; it attaches
  to the browser you already have)
- Edge or Chrome, started with ``--remote-debugging-port`` (``browser_open``
  starts one for you)
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from src.aradhya.browser_cdp import (
    DEFAULT_DEBUG_PORT,
    NOT_PORTED_MESSAGE,
    AUTOMATION_PROFILE_DIR,
    PageSnapshot,
    format_snapshot,
    get_browser_backend,
)
from src.aradhya.tools.tool_registry import tool_definition


def xpath_literal(value: str) -> str:
    """Return ``value`` as a safely quoted XPath 1.0 string literal.

    XPath 1.0 has no escape character, so a string containing both quote
    kinds cannot be expressed as a single literal.  The standard workaround
    is ``concat()``.  Without this, model- or page-supplied text is
    interpolated straight into an expression and can break out of the
    predicate — e.g. ``text = "' or '1'='1"`` turns a targeted lookup into
    a match-anything selector, so a click lands on an arbitrary element.

    Still needed on the CDP backend: the ``xpath`` parameter survives on
    ``browser_click``, and Playwright locators take XPath just as WebDriver did.
    ``tests/unit/test_xpath_escaping.py`` guards the 2026-06-15 injection.

    >>> xpath_literal("Sign in")
    "'Sign in'"
    >>> xpath_literal("it's")
    '"it\\'s"'
    >>> xpath_literal("' or '1'='1")
    '"\\' or \\'1\\'=\\'1"'
    """
    if "'" not in value:
        return f"'{value}'"
    if '"' not in value:
        return f'"{value}"'
    # Both quote kinds present — split on single quotes and rejoin via concat().
    parts = value.split("'")
    pieces: list[str] = []
    for index, part in enumerate(parts):
        if part:
            pieces.append(f"'{part}'")
        if index < len(parts) - 1:
            pieces.append('"\'"')
    return "concat(" + ", ".join(pieces) + ")"


@tool_definition(
    name="browser_open",
    description=(
        "Open a browser session by attaching to a real Edge/Chrome over the "
        "DevTools Protocol, starting one if none is listening. Uses Aradhya's "
        "own persistent browser profile, so accounts you sign into stay signed "
        "in across sessions. Must be called before other browser_* tools."
    ),
    parameters={
        "type": "object",
        "properties": {
            "use_profile": {
                "type": "boolean",
                "description": (
                    "If true (default), use Aradhya's persistent browser profile "
                    "so logged-in sessions carry over. If false, use a clean "
                    "throwaway profile."
                ),
            },
            "profile_name": {
                "type": "string",
                "description": (
                    "Profile directory name under ~/.aradhya/ to use. "
                    "Default: 'browser-profile'."
                ),
            },
            "headless": {
                "type": "boolean",
                "description": "Run browser without a visible window. Default: false.",
            },
            "debug_port": {
                "type": "integer",
                "description": (
                    "DevTools Protocol port to attach to. Default: 9222. An "
                    "already-running browser on this port is reused."
                ),
            },
        },
    },
    requires_confirmation=True,
)
def browser_open(
    use_profile: bool = True,
    profile_name: str = "browser-profile",
    headless: bool = False,
    debug_port: int = DEFAULT_DEBUG_PORT,
) -> str:
    """Attach to (or start) a browser with remote debugging enabled."""
    backend = get_browser_backend()

    profile_dir = None
    if not use_profile:
        profile_dir = Path(tempfile.mkdtemp(prefix="aradhya-browser-"))
    elif profile_name and profile_name != AUTOMATION_PROFILE_DIR.name:
        profile_dir = AUTOMATION_PROFILE_DIR.parent / profile_name

    _success, message = backend.attach(
        port=debug_port,
        launch_if_needed=True,
        headless=headless,
        profile_dir=profile_dir,
    )
    return message


@tool_definition(
    name="browser_navigate",
    description="Navigate the browser to a URL.",
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to navigate to.",
            },
        },
        "required": ["url"],
    },
    requires_confirmation=True,
)
def browser_navigate(url: str) -> str:
    """Navigate to a URL."""
    _success, message = get_browser_backend().navigate(url)
    return message


@tool_definition(
    name="browser_click",
    description=(
        "Click an element on the page by its visible text, CSS selector, "
        "or XPath. Tries text match first, then selector."
    ),
    parameters={
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "Visible text of the element to click.",
            },
            "selector": {
                "type": "string",
                "description": "CSS selector (used if text match fails).",
            },
            "xpath": {
                "type": "string",
                "description": "XPath expression (used if selector fails).",
            },
        },
    },
    requires_confirmation=True,
)
def browser_click(
    text: str = "",
    selector: str = "",
    xpath: str = "",
) -> str:
    """Click an element on the page (not yet ported to the CDP backend)."""
    return NOT_PORTED_MESSAGE.format(tool="browser_click")


@tool_definition(
    name="browser_type",
    description=(
        "Type text into an input field on the page. "
        "Finds the element by selector, name, or the currently focused element."
    ),
    parameters={
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "The text to type.",
            },
            "selector": {
                "type": "string",
                "description": "CSS selector of the input field.",
            },
            "name": {
                "type": "string",
                "description": "Name attribute of the input field.",
            },
            "press_enter": {
                "type": "boolean",
                "description": "Press Enter after typing. Default: false.",
            },
        },
        "required": ["text"],
    },
    requires_confirmation=True,
)
def browser_type(
    text: str,
    selector: str = "",
    name: str = "",
    press_enter: bool = False,
) -> str:
    """Type text into a form field (not yet ported to the CDP backend)."""
    return NOT_PORTED_MESSAGE.format(tool="browser_type")


@tool_definition(
    name="browser_read",
    description=(
        "Read the current page as a structured element map: every interactive "
        "element with its role, accessible name, id and value, each with a "
        "stable ref. Use this to understand what is on screen before deciding "
        "what to click — it is the browser equivalent of list_window_controls."
    ),
    parameters={
        "type": "object",
        "properties": {
            "selector": {
                "type": "string",
                "description": (
                    "Optional filter — keep only elements whose name or id "
                    "contains this text, or whose role equals it. Omit to read "
                    "the whole page."
                ),
            },
        },
    },
)
def browser_read(selector: str = "") -> str:
    """Read the current page as an element map, not as truncated body text."""
    result = get_browser_backend().snapshot(selector)
    if isinstance(result, PageSnapshot):
        return format_snapshot(result)
    return str(result)


@tool_definition(
    name="browser_screenshot",
    description="Take a screenshot of the current browser page.",
    parameters={
        "type": "object",
        "properties": {
            "filename": {
                "type": "string",
                "description": "Path to save the screenshot. Defaults to temp file.",
            },
        },
    },
)
def browser_screenshot(filename: str = "") -> str:
    """Screenshot the browser window (not yet ported to the CDP backend)."""
    return NOT_PORTED_MESSAGE.format(tool="browser_screenshot")


@tool_definition(
    name="browser_close",
    description="Close the current browser session.",
    parameters={"type": "object", "properties": {}},
)
def browser_close() -> str:
    """Detach from the browser."""
    _success, message = get_browser_backend().close()
    return message


@tool_definition(
    name="browser_execute_js",
    description=(
        "Execute JavaScript code in the browser and return the result. "
        "Use for advanced interactions like scrolling, waiting for elements, "
        "or extracting specific data from the page."
    ),
    parameters={
        "type": "object",
        "properties": {
            "script": {
                "type": "string",
                "description": "JavaScript code to execute.",
            },
        },
        "required": ["script"],
    },
    requires_confirmation=True,
)
def browser_execute_js(script: str) -> str:
    """Execute JavaScript in the browser (not yet ported to the CDP backend)."""
    return NOT_PORTED_MESSAGE.format(tool="browser_execute_js")


@tool_definition(
    name="browser_submit",
    description=(
        "Submit a form on the page. This is the explicit, confirmation-gated "
        "checkpoint before sending a form (search, login, job application). "
        "Finds the form by selector or name, otherwise submits the form "
        "containing the currently focused element."
    ),
    parameters={
        "type": "object",
        "properties": {
            "selector": {
                "type": "string",
                "description": "CSS selector of the form or a field inside it.",
            },
            "name": {
                "type": "string",
                "description": "Name attribute of the form or a field inside it.",
            },
        },
    },
    requires_confirmation=True,
)
def browser_submit(selector: str = "", name: str = "") -> str:
    """Submit a form (not yet ported to the CDP backend)."""
    return NOT_PORTED_MESSAGE.format(tool="browser_submit")


@tool_definition(
    name="browser_new_tab",
    description=(
        "Open a new browser tab, optionally navigating it to a URL, and switch "
        "to it. Use this to open several sources at once for comparison. Tabs "
        "are numbered (1-based) in open order."
    ),
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Optional URL to open in the new tab.",
            },
        },
    },
    requires_confirmation=True,
)
def browser_new_tab(url: str = "") -> str:
    """Open (and switch to) a new tab, optionally navigating to a URL."""
    _success, message = get_browser_backend().new_page(url)
    return message


@tool_definition(
    name="browser_list_tabs",
    description=(
        "List all open browser tabs with their 1-based index, title, and URL. "
        "Read-only. Use this to see what's open before switching or comparing."
    ),
    parameters={"type": "object", "properties": {}},
)
def browser_list_tabs() -> str:
    """List open tabs with index, title, and URL."""
    rows = get_browser_backend().list_pages()
    if isinstance(rows, str):
        return rows
    lines = [f"{len(rows)} open tab(s):"]
    for index, (title, url, is_current) in enumerate(rows, start=1):
        marker = " (current)" if is_current else ""
        lines.append(f"  {index}. {title} — {url}{marker}")
    return "\n".join(lines)


@tool_definition(
    name="browser_switch_tab",
    description=(
        "Switch focus to an open tab by its 1-based index (see browser_list_tabs). "
        "Subsequent read/click/type tools act on the focused tab."
    ),
    parameters={
        "type": "object",
        "properties": {
            "index": {
                "type": "integer",
                "description": "1-based tab number to switch to.",
            },
        },
        "required": ["index"],
    },
)
def browser_switch_tab(index: int) -> str:
    """Switch focus to the tab at the given 1-based index."""
    _success, message = get_browser_backend().switch_page(index)
    return message


ALL_BROWSER_TOOLS = [
    browser_open,
    browser_navigate,
    browser_click,
    browser_type,
    browser_read,
    browser_screenshot,
    browser_close,
    browser_execute_js,
    browser_submit,
    browser_new_tab,
    browser_list_tabs,
    browser_switch_tab,
]
