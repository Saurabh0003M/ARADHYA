"""Browser automation tools for the agent loop.

These tools give Aradhya the ability to control a web browser — navigating
to URLs, clicking elements, typing text, and reading page content.  This
enables scenarios like "ring Kautilya's phone via Find My Device" or
"reply on WhatsApp Web".

Uses Selenium with Chrome/Edge WebDriver to connect to the user's actual
browser profile (important: logged-in sessions like Google accounts are
available).  Falls back to a clean session if no profile is specified.

Dependencies:
- ``selenium`` — ``pip install selenium``
- Chrome or Edge browser installed
- ChromeDriver or EdgeDriver (auto-managed by selenium-manager)
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from loguru import logger

from src.aradhya.tools.tool_registry import tool_definition

# Global browser session — shared across tool calls within an agent turn
_active_driver: Any = None


def _get_chrome_profile_path() -> str | None:
    """Find the default Chrome user data directory on Windows."""
    if os.name != "nt":
        return None
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if not local_app_data:
        return None
    chrome_dir = Path(local_app_data) / "Google" / "Chrome" / "User Data"
    if chrome_dir.is_dir():
        return str(chrome_dir)
    return None


def _get_edge_profile_path() -> str | None:
    """Find the default Edge user data directory on Windows."""
    if os.name != "nt":
        return None
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if not local_app_data:
        return None
    edge_dir = Path(local_app_data) / "Microsoft" / "Edge" / "User Data"
    if edge_dir.is_dir():
        return str(edge_dir)
    return None


def _create_driver(
    profile_dir: str = "",
    profile_name: str = "Default",
    headless: bool = False,
) -> Any:
    """Create a Selenium WebDriver instance."""
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options as ChromeOptions
        from selenium.webdriver.chrome.service import Service as ChromeService
    except ImportError:
        raise RuntimeError(
            "Selenium is not installed. Install it with: pip install selenium"
        )

    options = ChromeOptions()

    if profile_dir:
        options.add_argument(f"--user-data-dir={profile_dir}")
        if profile_name:
            options.add_argument(f"--profile-directory={profile_name}")

    if headless:
        options.add_argument("--headless=new")

    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--disable-extensions")
    # Prevent "Chrome is being controlled by automated test software" bar
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    try:
        driver = webdriver.Chrome(options=options)
    except Exception:
        # Fallback: try Edge
        try:
            from selenium.webdriver.edge.options import Options as EdgeOptions
            from selenium.webdriver.edge.service import Service as EdgeService

            edge_options = EdgeOptions()
            if profile_dir:
                edge_profile = _get_edge_profile_path()
                if edge_profile:
                    edge_options.add_argument(f"--user-data-dir={edge_profile}")
            if headless:
                edge_options.add_argument("--headless=new")
            driver = webdriver.Edge(options=edge_options)
        except Exception as edge_error:
            raise RuntimeError(
                f"Could not start Chrome or Edge WebDriver: {edge_error}"
            )

    driver.implicitly_wait(10)
    return driver


@tool_definition(
    name="browser_open",
    description=(
        "Open a browser session. Optionally uses the user's Chrome profile "
        "so all logged-in accounts (Google, WhatsApp, etc.) are available. "
        "Must be called before other browser_* tools."
    ),
    parameters={
        "type": "object",
        "properties": {
            "use_profile": {
                "type": "boolean",
                "description": (
                    "If true, uses the user's Chrome profile with logged-in "
                    "sessions. If false, opens a clean browser. Default: true."
                ),
            },
            "profile_name": {
                "type": "string",
                "description": (
                    "Chrome profile name to use (e.g., 'Default', 'Profile 1'). "
                    "Only relevant when use_profile is true."
                ),
            },
            "headless": {
                "type": "boolean",
                "description": "Run browser without a visible window. Default: false.",
            },
        },
    },
    requires_confirmation=True,
)
def browser_open(
    use_profile: bool = True,
    profile_name: str = "Default",
    headless: bool = False,
) -> str:
    """Open a browser session."""
    global _active_driver

    if _active_driver is not None:
        return "Browser is already open. Call browser_close() first to start a new session."

    profile_dir = ""
    if use_profile:
        profile_dir = _get_chrome_profile_path() or ""

    try:
        _active_driver = _create_driver(
            profile_dir=profile_dir,
            profile_name=profile_name,
            headless=headless,
        )
        profile_msg = f" with profile '{profile_name}'" if profile_dir else " (clean session)"
        return f"Browser opened{profile_msg}."
    except Exception as error:
        return f"Failed to open browser: {error}"


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
    if _active_driver is None:
        return "No browser session. Call browser_open() first."
    try:
        _active_driver.get(url)
        time.sleep(2)  # Wait for page load
        return f"Navigated to {url}. Page title: {_active_driver.title}"
    except Exception as error:
        return f"Navigation failed: {error}"


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
    """Click an element on the page."""
    if _active_driver is None:
        return "No browser session. Call browser_open() first."

    from selenium.webdriver.common.by import By

    element = None

    # Try by visible text
    if text and element is None:
        try:
            element = _active_driver.find_element(
                By.XPATH, f"//*[contains(text(), '{text}')]"
            )
        except Exception:
            # Try link text
            try:
                element = _active_driver.find_element(By.LINK_TEXT, text)
            except Exception:
                pass

    # Try CSS selector
    if selector and element is None:
        try:
            element = _active_driver.find_element(By.CSS_SELECTOR, selector)
        except Exception:
            pass

    # Try XPath
    if xpath and element is None:
        try:
            element = _active_driver.find_element(By.XPATH, xpath)
        except Exception:
            pass

    if element is None:
        return (
            f"Could not find element to click. "
            f"Tried: text='{text}', selector='{selector}', xpath='{xpath}'"
        )

    try:
        element.click()
        time.sleep(1)
        return f"Clicked element. Page title: {_active_driver.title}"
    except Exception as error:
        return f"Click failed: {error}"


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
    """Type text into a form field."""
    if _active_driver is None:
        return "No browser session. Call browser_open() first."

    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys

    element = None

    if selector:
        try:
            element = _active_driver.find_element(By.CSS_SELECTOR, selector)
        except Exception:
            pass

    if name and element is None:
        try:
            element = _active_driver.find_element(By.NAME, name)
        except Exception:
            pass

    # Fallback: active element
    if element is None:
        element = _active_driver.switch_to.active_element

    try:
        element.clear()
        element.send_keys(text)
        if press_enter:
            element.send_keys(Keys.RETURN)
            time.sleep(1)
        return f"Typed '{text[:50]}...' into element."
    except Exception as error:
        return f"Typing failed: {error}"


@tool_definition(
    name="browser_read",
    description=(
        "Read the visible text content of the current page. "
        "Returns the page title and body text (truncated to 4000 chars). "
        "Use this to understand what's on screen before deciding what to click."
    ),
    parameters={
        "type": "object",
        "properties": {
            "selector": {
                "type": "string",
                "description": (
                    "Optional CSS selector to read only a specific element. "
                    "Omit to read the entire page body."
                ),
            },
        },
    },
)
def browser_read(selector: str = "") -> str:
    """Read text content from the current page."""
    if _active_driver is None:
        return "No browser session. Call browser_open() first."

    from selenium.webdriver.common.by import By

    try:
        title = _active_driver.title
        url = _active_driver.current_url

        if selector:
            element = _active_driver.find_element(By.CSS_SELECTOR, selector)
            text = element.text
        else:
            body = _active_driver.find_element(By.TAG_NAME, "body")
            text = body.text

        text = text[:4000]
        return f"Page: {title}\nURL: {url}\n\nContent:\n{text}"
    except Exception as error:
        return f"Failed to read page: {error}"


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
    """Take a screenshot of the browser window."""
    if _active_driver is None:
        return "No browser session. Call browser_open() first."

    if not filename:
        import tempfile
        stamp = time.strftime("%Y%m%d_%H%M%S")
        filename = str(
            Path(tempfile.gettempdir()) / f"aradhya_browser_{stamp}.png"
        )

    try:
        _active_driver.save_screenshot(filename)
        return f"Browser screenshot saved to {filename}"
    except Exception as error:
        return f"Screenshot failed: {error}"


@tool_definition(
    name="browser_close",
    description="Close the current browser session.",
    parameters={"type": "object", "properties": {}},
)
def browser_close() -> str:
    """Close the browser session."""
    global _active_driver

    if _active_driver is None:
        return "No browser session is active."

    try:
        _active_driver.quit()
    except Exception:
        pass
    _active_driver = None
    return "Browser session closed."


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
    """Execute JavaScript in the browser."""
    if _active_driver is None:
        return "No browser session. Call browser_open() first."

    try:
        result = _active_driver.execute_script(script)
        if result is None:
            return "JavaScript executed (no return value)."
        return f"JavaScript result: {str(result)[:2000]}"
    except Exception as error:
        return f"JavaScript execution failed: {error}"


ALL_BROWSER_TOOLS = [
    browser_open,
    browser_navigate,
    browser_click,
    browser_type,
    browser_read,
    browser_screenshot,
    browser_close,
    browser_execute_js,
]
