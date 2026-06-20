"""Desktop control tools via UI Automation (P1-8).

Let the agent read and command any desktop window's controls — the same
accessibility tree a screen reader uses. Listing is read-only; invoking or
typing into a control is confirmation-gated. All tools degrade to a clear
"install uiautomation" message when the backend is unavailable, so they never
break a turn.
"""

from __future__ import annotations

from src.aradhya.desktop_control import (
    UNAVAILABLE_MESSAGE,
    format_controls,
    format_windows,
    get_desktop_backend,
)
from src.aradhya.tools.tool_registry import tool_definition


@tool_definition(
    name="list_windows",
    description=(
        "List the titles of all open top-level desktop windows. Read-only. Use "
        "this to find the exact window title before reading or controlling it."
    ),
    parameters={"type": "object", "properties": {}},
)
def list_windows() -> str:
    """List open desktop windows."""
    backend = get_desktop_backend()
    if not backend.available():
        return UNAVAILABLE_MESSAGE
    return format_windows(backend.list_windows())


@tool_definition(
    name="list_window_controls",
    description=(
        "List the automatable controls (buttons, menu items, fields, links) in a "
        "window, by window title. Read-only. Use this to discover what you can "
        "click or type before invoking anything."
    ),
    parameters={
        "type": "object",
        "properties": {
            "window_title": {
                "type": "string",
                "description": "Title (or part of it) of the target window.",
            },
        },
        "required": ["window_title"],
    },
)
def list_window_controls(window_title: str) -> str:
    """List the controls inside a window."""
    backend = get_desktop_backend()
    if not backend.available():
        return UNAVAILABLE_MESSAGE
    controls = backend.list_controls(window_title)
    if not controls:
        return f"No window matching '{window_title}', or it exposes no named controls."
    return f"Controls in '{window_title}':\n" + format_controls(controls)


@tool_definition(
    name="invoke_control",
    description=(
        "Invoke (click/activate) a named control in a window via UI Automation — "
        "e.g. press a button or choose a menu item. Match the control by its "
        "visible name. Requires confirmation."
    ),
    parameters={
        "type": "object",
        "properties": {
            "window_title": {
                "type": "string",
                "description": "Title (or part of it) of the target window.",
            },
            "control_name": {
                "type": "string",
                "description": "Visible name of the control to invoke.",
            },
        },
        "required": ["window_title", "control_name"],
    },
    requires_confirmation=True,
)
def invoke_control(window_title: str, control_name: str) -> str:
    """Invoke a control by name in a window."""
    backend = get_desktop_backend()
    if not backend.available():
        return UNAVAILABLE_MESSAGE
    _success, message = backend.invoke(window_title, control_name)
    return message


@tool_definition(
    name="set_control_text",
    description=(
        "Type text into a named editable control (text box) in a window via UI "
        "Automation. Match the control by its visible name or label. Requires "
        "confirmation."
    ),
    parameters={
        "type": "object",
        "properties": {
            "window_title": {
                "type": "string",
                "description": "Title (or part of it) of the target window.",
            },
            "control_name": {
                "type": "string",
                "description": "Visible name/label of the editable control.",
            },
            "text": {
                "type": "string",
                "description": "Text to set into the control.",
            },
        },
        "required": ["window_title", "control_name", "text"],
    },
    requires_confirmation=True,
)
def set_control_text(window_title: str, control_name: str, text: str) -> str:
    """Set text into an editable control by name."""
    backend = get_desktop_backend()
    if not backend.available():
        return UNAVAILABLE_MESSAGE
    _success, message = backend.set_value(window_title, control_name, text)
    return message


@tool_definition(
    name="focus_window",
    description="Bring a desktop window to the foreground by its title.",
    parameters={
        "type": "object",
        "properties": {
            "window_title": {
                "type": "string",
                "description": "Title (or part of it) of the window to focus.",
            },
        },
        "required": ["window_title"],
    },
    requires_confirmation=True,
)
def focus_window(window_title: str) -> str:
    """Bring a window to the foreground."""
    backend = get_desktop_backend()
    if not backend.available():
        return UNAVAILABLE_MESSAGE
    _success, message = backend.focus_window(window_title)
    return message


ALL_DESKTOP_TOOLS = [
    list_windows,
    list_window_controls,
    invoke_control,
    set_control_text,
    focus_window,
]
