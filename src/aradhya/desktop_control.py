"""UI Automation backend for commanding any desktop window (P1-8).

This is the "terminal icon on every window" idea: Windows UI Automation exposes
any app's controls as a tree you can read and invoke — the same accessibility
channel a screen reader uses, which is why it fits the eyes-free mission better
than pixel clicks.

Design:
- The data models (UIWindow, UIControl) and the matching/formatting helpers are
  pure and unit-tested.
- The real backend (UIAutomationBackend) lazily imports the optional
  ``uiautomation`` package and degrades gracefully when it is missing or a
  window/control isn't found — it never raises into the agent loop.
- Tools resolve a backend via get_desktop_backend(); set_desktop_backend() lets
  tests inject a fake.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from loguru import logger


@dataclass(frozen=True)
class UIWindow:
    """A top-level desktop window."""

    title: str
    handle: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"title": self.title, "handle": self.handle}


@dataclass(frozen=True)
class UIControl:
    """An automatable control inside a window."""

    name: str
    control_type: str
    automation_id: str = ""
    enabled: bool = True
    invokable: bool = False
    editable: bool = False
    """True when the control exposes the UIA Value pattern — i.e. when
    ``set_control_text`` can actually type into it. Surfacing this is the
    difference between a model guessing at a target and knowing one."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "control_type": self.control_type,
            "automation_id": self.automation_id,
            "enabled": self.enabled,
            "invokable": self.invokable,
            "editable": self.editable,
        }


# ── Pure matching / formatting ─────────────────────────────────────────

def find_control(controls: list[UIControl], query: str) -> UIControl | None:
    """Find the best control matching ``query`` (pure).

    Preference order: exact case-insensitive name, then a substring match.
    Within each, prefer enabled+invokable controls so a clickable button wins
    over an inert label with the same text.
    """
    if not query:
        return None
    wanted = query.strip().lower()

    def rank(control: UIControl) -> tuple[int, int]:
        return (1 if control.invokable else 0, 1 if control.enabled else 0)

    exact = [c for c in controls if c.name.strip().lower() == wanted]
    if exact:
        return max(exact, key=rank)

    partial = [c for c in controls if wanted in c.name.strip().lower()]
    if partial:
        return max(partial, key=rank)

    return None


def find_window(windows: list[UIWindow], query: str) -> UIWindow | None:
    """Find the best window matching ``query`` (exact title, then substring)."""
    if not query:
        return None
    wanted = query.strip().lower()
    for window in windows:
        if window.title.strip().lower() == wanted:
            return window
    for window in windows:
        if wanted in window.title.strip().lower():
            return window
    return None


def format_windows(windows: list[UIWindow]) -> str:
    if not windows:
        return "No top-level windows detected."
    lines = [f"{len(windows)} window(s):"]
    for window in windows:
        lines.append(f"  - {window.title}")
    return "\n".join(lines)


def format_controls(controls: list[UIControl], limit: int = 60) -> str:
    if not controls:
        return "No named controls found in that window."
    lines = [f"{len(controls)} control(s):"]
    for control in controls[:limit]:
        flags = []
        if control.invokable:
            flags.append("invokable")
        if control.editable:
            flags.append("editable")
        if not control.enabled:
            flags.append("disabled")
        suffix = f" [{', '.join(flags)}]" if flags else ""
        lines.append(f"  - {control.control_type}: \"{control.name}\"{suffix}")
    if len(controls) > limit:
        lines.append(f"  ... and {len(controls) - limit} more")
    return "\n".join(lines)


# ── Backend protocol ───────────────────────────────────────────────────

class UIABackend(Protocol):
    def available(self) -> bool: ...
    def list_windows(self) -> list[UIWindow]: ...
    def list_controls(self, window_title: str, max_controls: int = 200) -> list[UIControl]: ...
    def invoke(self, window_title: str, control_name: str) -> tuple[bool, str]: ...
    def set_value(self, window_title: str, control_name: str, text: str) -> tuple[bool, str]: ...
    def focus_window(self, window_title: str) -> tuple[bool, str]: ...


UNAVAILABLE_MESSAGE = (
    "UI Automation is unavailable. Install it on Windows with "
    "`pip install uiautomation` (see requirements-windows.txt)."
)


class UIAutomationBackend:
    """Real backend over the optional ``uiautomation`` package (Windows-only).

    Every UIA call is wrapped so a missing package, a closed window, or an
    unsupported control degrades to a returned message instead of an exception.
    """

    def __init__(self) -> None:
        self._auto: Any = None
        self._import_failed = False

    def _mod(self) -> Any:
        if self._auto is None and not self._import_failed:
            try:
                import uiautomation as auto  # type: ignore[import-untyped]

                self._auto = auto
            except Exception as error:  # ImportError or COM init failure
                self._import_failed = True
                logger.debug("uiautomation unavailable: {}", error)
        return self._auto

    def available(self) -> bool:
        return self._mod() is not None

    def list_windows(self) -> list[UIWindow]:
        auto = self._mod()
        if auto is None:
            return []
        windows: list[UIWindow] = []
        try:
            root = auto.GetRootControl()
            for child in root.GetChildren():
                try:
                    if child.ControlTypeName != "WindowControl":
                        continue
                    name = child.Name
                    if name:
                        windows.append(
                            UIWindow(title=name, handle=int(getattr(child, "NativeWindowHandle", 0) or 0))
                        )
                except Exception:
                    continue
        except Exception as error:
            logger.debug("list_windows failed: {}", error)
        return windows

    def _live_window(self, auto: Any, window_title: str) -> Any:
        root = auto.GetRootControl()
        children = [c for c in root.GetChildren() if c.Name]
        wanted = window_title.strip().lower()
        for child in children:
            if child.Name.strip().lower() == wanted:
                return child
        for child in children:
            if wanted in child.Name.strip().lower():
                return child
        return None

    @staticmethod
    def _supports_pattern(control: Any, pattern_getter: str) -> bool:
        """True if ``control`` exposes the named UIA pattern.

        ``uiautomation`` only defines ``GetInvokePattern`` / ``GetValuePattern``
        on the control classes that support them, so calling one unguarded
        raises ``AttributeError`` on an ``EditControl``, ``TextControl``,
        ``PaneControl``, ``GroupControl`` or ``ImageControl``. That mattered:
        the exception was swallowed by the per-control ``except`` below and
        took the whole control out of the map with it — measured at **188 of
        299 controls silently dropped** from one File Explorer window, every
        text field among them. A model cannot type into a box it was never
        shown.
        """
        getter = getattr(control, pattern_getter, None)
        if getter is None:
            return False
        try:
            return getter() is not None
        except Exception:
            return False

    def list_controls(self, window_title: str, max_controls: int = 200) -> list[UIControl]:
        auto = self._mod()
        if auto is None:
            return []
        controls: list[UIControl] = []
        try:
            window = self._live_window(auto, window_title)
            if window is None:
                return []
            for control, _depth in auto.WalkControl(window, includeTop=False):
                try:
                    # Flatten to one line: format_controls prints one control
                    # per line, and names really do contain newlines in the
                    # wild (Notepad's status bar is "Line 1,\nColumn 1").
                    name = " ".join((control.Name or "").split())
                    if not name:
                        continue
                    controls.append(
                        UIControl(
                            name=name,
                            control_type=control.ControlTypeName,
                            automation_id=getattr(control, "AutomationId", "") or "",
                            enabled=bool(getattr(control, "IsEnabled", True)),
                            invokable=self._supports_pattern(control, "GetInvokePattern"),
                            editable=self._supports_pattern(control, "GetValuePattern"),
                        )
                    )
                except Exception:
                    continue
                if len(controls) >= max_controls:
                    break
        except Exception as error:
            logger.debug("list_controls failed: {}", error)
        return controls

    def _live_control(self, auto: Any, window: Any, control_name: str) -> Any:
        wanted = control_name.strip().lower()
        exact = None
        partial = None
        for control, _depth in auto.WalkControl(window, includeTop=False):
            try:
                name = control.Name
            except Exception:
                continue
            if not name:
                continue
            lowered = name.strip().lower()
            if lowered == wanted:
                exact = control
                break
            if partial is None and wanted in lowered:
                partial = control
        return exact or partial

    def invoke(self, window_title: str, control_name: str) -> tuple[bool, str]:
        auto = self._mod()
        if auto is None:
            return False, UNAVAILABLE_MESSAGE
        try:
            window = self._live_window(auto, window_title)
            if window is None:
                return False, f"No window matching '{window_title}'."
            control = self._live_control(auto, window, control_name)
            if control is None:
                return False, f"No control matching '{control_name}' in '{window_title}'."
            getter = getattr(control, "GetInvokePattern", None)
            pattern = getter() if getter is not None else None
            if pattern is not None:
                pattern.Invoke()
            else:
                control.Click()
            return True, f"Invoked '{control.Name}' in '{window.Name}'."
        except Exception as error:
            return False, f"Invoke failed: {error}"

    def set_value(self, window_title: str, control_name: str, text: str) -> tuple[bool, str]:
        auto = self._mod()
        if auto is None:
            return False, UNAVAILABLE_MESSAGE
        try:
            window = self._live_window(auto, window_title)
            if window is None:
                return False, f"No window matching '{window_title}'."
            control = self._live_control(auto, window, control_name)
            if control is None:
                return False, f"No control matching '{control_name}' in '{window_title}'."
            getter = getattr(control, "GetValuePattern", None)
            pattern = getter() if getter is not None else None
            if pattern is None:
                return False, (
                    f"'{control.Name}' does not accept a text value "
                    f"(no UIA Value pattern). Use list_window_controls to find "
                    f"one marked [editable]."
                )
            pattern.SetValue(text)
            return True, f"Set '{control.Name}' to the provided text."
        except Exception as error:
            return False, f"Set value failed: {error}"

    def focus_window(self, window_title: str) -> tuple[bool, str]:
        auto = self._mod()
        if auto is None:
            return False, UNAVAILABLE_MESSAGE
        try:
            window = self._live_window(auto, window_title)
            if window is None:
                return False, f"No window matching '{window_title}'."
            window.SetActive()
            return True, f"Focused '{window.Name}'."
        except Exception as error:
            return False, f"Focus failed: {error}"


# ── Backend resolution (with test override) ────────────────────────────

_backend_override: UIABackend | None = None
_real_backend: UIAutomationBackend | None = None


def set_desktop_backend(backend: UIABackend | None) -> None:
    """Override the backend (used by tests). Pass None to clear."""
    global _backend_override
    _backend_override = backend


def get_desktop_backend() -> UIABackend:
    """Return the active backend — the test override, else the real one."""
    global _real_backend
    if _backend_override is not None:
        return _backend_override
    if _real_backend is None:
        _real_backend = UIAutomationBackend()
    return _real_backend
