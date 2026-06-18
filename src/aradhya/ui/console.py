"""Shared Rich console, theme, and primitive renderers for Aradhya.

This is the leaf of the UI layer: it owns the global ``console`` object and the
generic ``render_info``/``render_success``/``render_warning``/``render_error``
helpers. Every other UI module imports from here, so it must not import any of
them back.
"""

from __future__ import annotations

import io
import os
import sys

# Force UTF-8 on Windows terminals before Rich initializes.
if sys.platform == "win32":
    os.system("")  # enables ANSI escape codes on Windows 10+
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            sys.stdout = io.TextIOWrapper(
                sys.stdout.buffer, encoding="utf-8", errors="replace",
            )

from rich.console import Console
from rich.theme import Theme

# ── Global theme ──────────────────────────────────────────────────────
ARADHYA_THEME = Theme(
    {
        "aradhya": "bold #00d4aa",
        "user": "bold #61afef",
        "heading": "bold #c678dd",
        "success": "bold #98c379",
        "warning": "bold #e5c07b",
        "error": "bold #e06c75",
        "dim": "dim #7f848e",
        "accent": "#56b6c2",
        "highlight": "bold #d19a66",
    }
)

console = Console(theme=ARADHYA_THEME, highlight=False)


# ── Misc primitive renderers ──────────────────────────────────────────
def render_info(message: str) -> None:
    console.print(f"  [dim]>[/] {message}")

def render_success(message: str) -> None:
    console.print(f"  [success][+][/] {message}")

def render_warning(message: str) -> None:
    console.print(f"  [warning][~][/] {message}")

def render_error(message: str) -> None:
    console.print(f"  [error][!][/] {message}")
