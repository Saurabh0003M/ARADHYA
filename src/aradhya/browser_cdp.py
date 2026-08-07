"""CDP-attach browser driver — the backend under the ``browser_*`` tools.

Replaces the Selenium backend. Decision memo 2026-08-07 §4 amendment 1: both
P3 reports rate WebDriver "obsolete for agents", and repairing twelve browser
tools *on* Selenium was repairing the wrong stack. This attaches over the
Chrome DevTools Protocol to a real Edge/Chrome started with
``--remote-debugging-port``, which is also the anti-bot guidance both reports
give — a persistent authenticated profile beats fingerprint randomisation.

Three things this module is careful about:

**The tool names do not change.** The safety architecture is keyed on them: the
approved-rules allowlist persists per (tool, args), ``audit.jsonl`` records by
name, ``DANGEROUS_TOOLS`` lists ``browser_click``/``browser_type``/
``browser_execute_js``, and the tests reference them. Only the backend moved.

**Playwright's sync API cannot run inside an asyncio loop**, and ARADHYA calls
tools from both a sync CLI and (soon) an async MCP server. So the driver owns a
dedicated worker thread; every call is marshalled onto it. Callers stay sync
and an event loop in the calling thread is irrelevant.

**A page is read as a structured element map, never as truncated body text.**
``snapshot()`` returns roles, accessible names, ids, and values with stable
refs, because "read this window" has to produce something a model can act on
rather than 4,000 characters of prose.
"""

from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from loguru import logger

DEFAULT_DEBUG_PORT = 9222

#: Chrome 136+ and current Edge refuse ``--remote-debugging-port`` when the
#: browser is using its default user-data-dir, so attaching to the everyday
#: profile is not possible by design. ARADHYA gets its own persistent profile
#: instead: the user signs in once inside it and the logins stay.
AUTOMATION_PROFILE_DIR = Path.home() / ".aradhya" / "browser-profile"

NOT_PORTED_MESSAGE = (
    "{tool} is not yet ported to the CDP backend (Stage 0 ported browser_open, "
    "browser_navigate, browser_read, browser_close and the tab tools). Use "
    "browser_read to get the element map; the remaining tools land next."
)


# ── Data model ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PageElement:
    """One interactive element in a page's element map."""

    ref: str
    role: str
    name: str
    element_id: str = ""
    value: str = ""
    enabled: bool = True
    href: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ref": self.ref,
            "role": self.role,
            "name": self.name,
            "id": self.element_id,
            "value": self.value,
            "enabled": self.enabled,
            "href": self.href,
        }


@dataclass(frozen=True)
class PageSnapshot:
    """A page as roles, labels, ids and values — not as body text."""

    title: str
    url: str
    elements: tuple[PageElement, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "elements": [element.to_dict() for element in self.elements],
        }


# ── Pure formatting (unit-tested without a browser) ────────────────────


def format_snapshot(snapshot: PageSnapshot, limit: int = 80) -> str:
    """Render an element map for the model.

    One line per element: ref, role, accessible name, then id / value / href
    when present. A model can pick a target from this; it cannot from prose.
    """
    lines = [f"Page: {snapshot.title}", f"URL: {snapshot.url}"]
    if not snapshot.elements:
        lines.append("")
        lines.append("No interactive elements found on this page.")
        return "\n".join(lines)

    lines.append("")
    lines.append(f"{len(snapshot.elements)} interactive element(s):")
    for element in snapshot.elements[:limit]:
        parts = [f"  [{element.ref}] {element.role}"]
        if element.name:
            parts.append(f'"{element.name}"')
        if element.element_id:
            parts.append(f"#{element.element_id}")
        if element.value:
            parts.append(f"= {element.value!r}")
        if element.href:
            parts.append(f"-> {element.href}")
        if not element.enabled:
            parts.append("[disabled]")
        lines.append(" ".join(parts))
    if len(snapshot.elements) > limit:
        lines.append(f"  ... and {len(snapshot.elements) - limit} more")
    return "\n".join(lines)


def parse_elements(raw: list[dict[str, Any]]) -> tuple[PageElement, ...]:
    """Convert the in-page extraction result into PageElements (pure).

    Names are flattened to one line: ``format_snapshot`` prints one element per
    line, and a name carrying a newline would silently forge a second entry.
    """
    elements: list[PageElement] = []
    for index, item in enumerate(raw, start=1):
        elements.append(
            PageElement(
                ref=f"e{index}",
                role=str(item.get("role") or "element"),
                name=" ".join(str(item.get("name") or "").split()),
                element_id=str(item.get("id") or ""),
                value=str(item.get("value") or ""),
                enabled=bool(item.get("enabled", True)),
                href=str(item.get("href") or ""),
            )
        )
    return tuple(elements)


# ── In-page element extraction ─────────────────────────────────────────

#: Runs in the page. Collects the interactive elements with the accessible
#: name a screen reader would announce, which is the same channel the desktop
#: leg reads — deliberately, so both legs describe the world the same way.
_ELEMENT_MAP_JS = """
() => {
  const SELECTOR = [
    'a[href]', 'button', 'input:not([type=hidden])', 'select', 'textarea',
    'summary', '[contenteditable="true"]', '[role]', '[onclick]',
  ].join(',');

  const roleFor = (el) => {
    const explicit = el.getAttribute('role');
    if (explicit) return explicit;
    const tag = el.tagName.toLowerCase();
    if (tag === 'a') return 'link';
    if (tag === 'button' || tag === 'summary') return 'button';
    if (tag === 'select') return 'combobox';
    if (tag === 'textarea') return 'textbox';
    if (tag === 'input') {
      const type = (el.getAttribute('type') || 'text').toLowerCase();
      if (type === 'checkbox') return 'checkbox';
      if (type === 'radio') return 'radio';
      if (type === 'submit' || type === 'button' || type === 'reset') return 'button';
      if (type === 'password') return 'password';
      return 'textbox';
    }
    return tag;
  };

  const nameFor = (el) => {
    const aria = el.getAttribute('aria-label');
    if (aria) return aria.trim();
    const labelledby = el.getAttribute('aria-labelledby');
    if (labelledby) {
      const parts = labelledby.split(/\\s+/)
        .map((id) => document.getElementById(id))
        .filter(Boolean)
        .map((node) => node.innerText || node.textContent || '');
      if (parts.length) return parts.join(' ').trim();
    }
    if (el.labels && el.labels.length) {
      const text = el.labels[0].innerText || el.labels[0].textContent || '';
      if (text.trim()) return text.trim();
    }
    for (const attr of ['placeholder', 'alt', 'title', 'name']) {
      const v = el.getAttribute(attr);
      if (v && v.trim()) return v.trim();
    }
    // Do NOT fall back to innerText for form controls: a <select>'s text is
    // its options, and reporting "Free\\nPro" as a label misleads the model
    // about what the control is called.
    const tag = el.tagName.toLowerCase();
    if (tag === 'select' || tag === 'textarea' || tag === 'input') return '';
    return (el.innerText || el.textContent || '').trim();
  };

  // One element per line downstream, so names must not carry newlines.
  const flatten = (s) => s.replace(/\\s+/g, ' ').trim();

  const visible = (el) => {
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 && rect.height === 0) return false;
    const style = window.getComputedStyle(el);
    return style.visibility !== 'hidden' && style.display !== 'none';
  };

  // Landmarks and containers match [role] but are never a click target, and
  // their accessible name is the concatenated text of everything inside them.
  // Listing them buries the real controls. Roles that carry meaning a caller
  // acts on (alert, status, dialog, tab, menuitem, radiogroup...) stay.
  const STRUCTURAL = new Set([
    'presentation', 'none', 'generic', 'list', 'listitem', 'main', 'banner',
    'contentinfo', 'navigation', 'region', 'article', 'document', 'group',
    'table', 'row', 'rowgroup', 'cell', 'columnheader', 'rowheader',
  ]);

  const out = [];
  const seen = new Set();
  for (const el of document.querySelectorAll(SELECTOR)) {
    if (seen.has(el) || !visible(el)) continue;
    seen.add(el);
    const role = roleFor(el);
    if (STRUCTURAL.has(role)) continue;
    // Never surface the value of a password field. Human-only line.
    const isSecret = role === 'password'
      || (el.getAttribute('type') || '').toLowerCase() === 'password';
    let value = '';
    if (!isSecret && 'value' in el && typeof el.value === 'string') {
      value = el.value.slice(0, 120);
    }
    out.push({
      role: role,
      name: flatten(nameFor(el)).slice(0, 120),
      id: el.id || '',
      value: value,
      enabled: !el.disabled,
      href: el.tagName.toLowerCase() === 'a' ? (el.getAttribute('href') || '').slice(0, 200) : '',
    });
    if (out.length >= 300) break;
  }
  return out;
}
"""


# ── CDP endpoint discovery / launch ────────────────────────────────────


def cdp_endpoint(port: int = DEFAULT_DEBUG_PORT, timeout: float = 1.0) -> str:
    """Return the ws endpoint of a browser listening on ``port``, else "".

    Probes ``/json/version`` rather than opening a socket, because a listening
    socket that is not a DevTools endpoint is a worse failure than no socket.
    """
    url = f"http://127.0.0.1:{port}/json/version"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
        return str(payload.get("webSocketDebuggerUrl") or f"http://127.0.0.1:{port}")
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError):
        return ""


def find_browser_executable() -> tuple[str, str]:
    """Locate Edge, then Chrome. Returns (path, friendly name) or ("", "")."""
    candidates: list[tuple[str, str]] = []
    for env_var in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
        base = os.environ.get(env_var)
        if not base:
            continue
        candidates.append((str(Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe"), "Edge"))
        candidates.append((str(Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe"), "Chrome"))
    for path, name in candidates:
        if Path(path).is_file():
            return path, name
    for command, name in (("msedge", "Edge"), ("chrome", "Chrome"), ("google-chrome", "Chrome")):
        found = shutil.which(command)
        if found:
            return found, name
    return "", ""


def launch_browser_with_cdp(
    port: int = DEFAULT_DEBUG_PORT,
    profile_dir: Path | None = None,
    headless: bool = False,
) -> tuple[bool, str]:
    """Start Edge/Chrome with remote debugging on ``port``.

    Uses ARADHYA's own persistent profile directory. Current Chrome and Edge
    refuse ``--remote-debugging-port`` against the default user-data-dir, so
    "attach to the everyday browser" is not available at any price — the honest
    equivalent is a profile that persists, which the user signs into once.
    """
    executable, name = find_browser_executable()
    if not executable:
        return False, "Could not find Edge or Chrome to launch."

    target = profile_dir or AUTOMATION_PROFILE_DIR
    target.mkdir(parents=True, exist_ok=True)

    arguments = [
        executable,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={target}",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    if headless:
        arguments.append("--headless=new")
    try:
        subprocess.Popen(
            arguments,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
    except Exception as error:
        return False, f"Failed to launch {name}: {error}"
    return True, f"Launched {name} with remote debugging on port {port}."


# ── Worker thread (keeps sync Playwright away from any asyncio loop) ────


class _DriverThread:
    """Runs every Playwright call on one dedicated thread.

    Playwright's sync API raises if it is used from a thread running an asyncio
    event loop, and it also requires that all calls come from the thread that
    created the ``Playwright`` object. Both constraints are satisfied by owning
    a thread and posting closures to it.
    """

    def __init__(self) -> None:
        self._jobs: queue.Queue[tuple[Callable[[], Any], queue.Queue] | None] = queue.Queue()
        self._thread = threading.Thread(
            target=self._run, name="aradhya-cdp-driver", daemon=True
        )
        self._started = False
        self._lock = threading.Lock()

    def _run(self) -> None:
        while True:
            job = self._jobs.get()
            if job is None:
                return
            work, reply = job
            try:
                reply.put(("ok", work()))
            except Exception as error:  # returned to the caller, never raised here
                reply.put(("error", error))

    def submit(self, work: Callable[[], Any], timeout: float = 60.0) -> Any:
        with self._lock:
            if not self._started:
                self._thread.start()
                self._started = True
        reply: queue.Queue = queue.Queue()
        self._jobs.put((work, reply))
        status, payload = reply.get(timeout=timeout)
        if status == "error":
            raise payload
        return payload

    def shutdown(self) -> None:
        with self._lock:
            if self._started:
                self._jobs.put(None)
                self._started = False


# ── Backend ────────────────────────────────────────────────────────────


class CdpBrowserBackend:
    """Attach to a real browser over CDP and drive the current page.

    Every method returns a value or a message; nothing raises into the agent
    loop, matching ``desktop_control.UIAutomationBackend``'s contract.
    """

    def __init__(self) -> None:
        self._driver = _DriverThread()
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None
        self._port: int = DEFAULT_DEBUG_PORT

    # -- availability -----------------------------------------------

    def available(self) -> bool:
        """True when Playwright is importable — the driver's only hard dep."""
        try:
            import playwright  # noqa: F401
        except Exception as error:
            logger.debug("playwright unavailable: {}", error)
            return False
        return True

    def attached(self) -> bool:
        return self._page is not None

    # -- lifecycle --------------------------------------------------

    def attach(
        self,
        port: int = DEFAULT_DEBUG_PORT,
        launch_if_needed: bool = True,
        headless: bool = False,
        profile_dir: Path | None = None,
    ) -> tuple[bool, str]:
        """Attach to a CDP endpoint, launching a browser first if needed."""
        if not self.available():
            return False, (
                "Playwright is not installed. Install it with `pip install playwright` "
                "— no browser download is needed, it attaches to your real "
                "Edge/Chrome over CDP."
            )
        if self._page is not None:
            return False, "Browser is already attached. Call browser_close() first."

        self._port = port
        endpoint = cdp_endpoint(port)
        launch_note = ""
        if not endpoint:
            if not launch_if_needed:
                return False, (
                    f"No browser is listening on CDP port {port}. Start one with "
                    f"`msedge.exe --remote-debugging-port={port} "
                    f'--user-data-dir="{AUTOMATION_PROFILE_DIR}"`, or call '
                    "browser_open again to let ARADHYA launch it."
                )
            launched, launch_note = launch_browser_with_cdp(
                port, profile_dir=profile_dir, headless=headless
            )
            if not launched:
                return False, launch_note
            endpoint = self._wait_for_endpoint(port)
            if not endpoint:
                return False, (
                    f"{launch_note} But no CDP endpoint appeared on port {port} "
                    "within 15s. If a browser was already running with this "
                    "profile, the new process may have handed off to it without "
                    "the debugging flag — close it and try again."
                )

        try:
            return self._driver.submit(lambda: self._connect(endpoint, launch_note))
        except Exception as error:
            return False, f"CDP attach failed: {error}"

    @staticmethod
    def _wait_for_endpoint(port: int, attempts: int = 30) -> str:
        import time

        for _ in range(attempts):
            endpoint = cdp_endpoint(port, timeout=0.5)
            if endpoint:
                return endpoint
            time.sleep(0.5)
        return ""

    def _connect(self, endpoint: str, launch_note: str) -> tuple[bool, str]:
        """Runs on the driver thread."""
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.connect_over_cdp(
            f"http://127.0.0.1:{self._port}"
        )
        contexts = self._browser.contexts
        self._context = contexts[0] if contexts else self._browser.new_context()
        pages = [page for page in self._context.pages if not page.is_closed()]
        self._page = pages[0] if pages else self._context.new_page()

        prefix = f"{launch_note} " if launch_note else ""
        return True, (
            f"{prefix}Attached over CDP on port {self._port}. "
            f"{len(self._context.pages)} tab(s) open; current: {self._page.title()!r}."
        )

    def close(self) -> tuple[bool, str]:
        """Detach from the browser. Does not kill the user's browser."""
        if self._page is None:
            return False, "No browser session is attached."

        def _work() -> None:
            if self._browser is not None:
                self._browser.close()  # detaches the CDP connection only
            if self._playwright is not None:
                self._playwright.stop()

        try:
            self._driver.submit(_work)
        except Exception as error:
            logger.debug("CDP detach raised (ignored): {}", error)
        finally:
            self._page = None
            self._context = None
            self._browser = None
            self._playwright = None
        return True, "Detached from the browser. The browser itself is still running."

    # -- actions ----------------------------------------------------

    def navigate(self, url: str, timeout_ms: int = 30000) -> tuple[bool, str]:
        if self._page is None:
            return False, "No browser session. Call browser_open() first."

        def _work() -> tuple[bool, str]:
            self._page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            return True, f"Navigated to {self._page.url}. Title: {self._page.title()!r}"

        try:
            return self._driver.submit(_work, timeout=timeout_ms / 1000 + 10)
        except Exception as error:
            return False, f"Navigation failed: {error}"

    def snapshot(self, selector: str = "") -> PageSnapshot | str:
        """Return the page's element map, or an error string."""
        if self._page is None:
            return "No browser session. Call browser_open() first."

        def _work() -> PageSnapshot:
            raw = self._page.evaluate(_ELEMENT_MAP_JS)
            elements = parse_elements(raw)
            if selector:
                lowered = selector.strip().lower()
                elements = tuple(
                    element
                    for element in elements
                    if lowered in element.name.lower()
                    or lowered in element.element_id.lower()
                    or lowered == element.role.lower()
                )
            return PageSnapshot(
                title=self._page.title(), url=self._page.url, elements=elements
            )

        try:
            return self._driver.submit(_work)
        except Exception as error:
            return f"Failed to read page: {error}"

    # -- tabs -------------------------------------------------------

    def list_pages(self) -> list[tuple[str, str, bool]] | str:
        if self._page is None:
            return "No browser session. Call browser_open() first."

        def _work() -> list[tuple[str, str, bool]]:
            rows = []
            for page in self._context.pages:
                if page.is_closed():
                    continue
                rows.append((page.title(), page.url, page is self._page))
            return rows

        try:
            return self._driver.submit(_work)
        except Exception as error:
            return f"Failed to list tabs: {error}"

    def new_page(self, url: str = "") -> tuple[bool, str]:
        if self._page is None:
            return False, "No browser session. Call browser_open() first."

        def _work() -> tuple[bool, str]:
            page = self._context.new_page()
            if url:
                page.goto(url, wait_until="domcontentloaded")
            self._page = page
            index = [p for p in self._context.pages if not p.is_closed()].index(page) + 1
            suffix = f" at {page.url} (title: {page.title()!r})" if url else ""
            return True, f"Opened tab {index}{suffix}."

        try:
            return self._driver.submit(_work)
        except Exception as error:
            return False, f"Failed to open tab: {error}"

    def switch_page(self, index: int) -> tuple[bool, str]:
        if self._page is None:
            return False, "No browser session. Call browser_open() first."

        def _work() -> tuple[bool, str]:
            pages = [p for p in self._context.pages if not p.is_closed()]
            if index < 1 or index > len(pages):
                return False, f"Tab {index} does not exist. There are {len(pages)} tab(s)."
            self._page = pages[index - 1]
            self._page.bring_to_front()
            return True, f"Switched to tab {index}: {self._page.title()!r} — {self._page.url}"

        try:
            return self._driver.submit(_work)
        except Exception as error:
            return False, f"Failed to switch tab: {error}"


# ── Backend resolution (with test override) ────────────────────────────

_backend_override: CdpBrowserBackend | None = None
_real_backend: CdpBrowserBackend | None = None


def set_browser_backend(backend: Any | None) -> None:
    """Override the backend (used by tests). Pass None to clear."""
    global _backend_override
    _backend_override = backend


def get_browser_backend() -> Any:
    """Return the active backend — the test override, else the real one."""
    global _real_backend
    if _backend_override is not None:
        return _backend_override
    if _real_backend is None:
        _real_backend = CdpBrowserBackend()
    return _real_backend
