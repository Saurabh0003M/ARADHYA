"""Test configuration — honest about what is installed.

Two rules are in tension here, and this file resolves them:

1. A unit test must not require the whole optional stack to be installed.
2. **The suite must never be green while the product cannot act.**

Rule 1 used to be served by installing ``MagicMock()`` into ``sys.modules`` for
every effector — ``selenium``, ``sounddevice``, ``uiautomation`` and friends.
That satisfied rule 1 by destroying rule 2: ``import uiautomation`` succeeded
inside the test process no matter what was on the machine, so a completely
uninstalled effector stack still produced a green run while every desktop tool
returned "install uiautomation" to the user at runtime.  That is exactly how
ARADHYA arrived at a green suite it could not act behind.

So there are now two categories, and only one of them may ever be faked:

``CORE_LIBRARIES``
    Pure-Python libraries declared in ``requirements.txt``.  They are imported
    for real.  A mock is installed **only** if the real import genuinely fails,
    and every such substitution is reported in the terminal summary.  Faking
    these hides an incomplete dev environment; it cannot hide an inability to
    act, because they do not touch the machine.

``EFFECTORS``
    The packages through which ARADHYA actually acts on the machine — UI
    Automation, the browser driver, the microphone, audio out.  **These are
    never mocked.**  A missing effector skips the tests that need it and is
    reported, loudly, at the end of the run.

Tests declare an effector need with the marker::

    @pytest.mark.effector("uiautomation")
    def test_against_a_real_window(): ...

or, inside a test, with the ``require_effector`` fixture::

    def test_something(require_effector):
        require_effector("playwright")

Set ``ARADHYA_REQUIRE_EFFECTORS=1`` to turn those skips into hard failures —
the mode a machine that is supposed to be able to act should run in.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import sys
from dataclasses import dataclass, field
from unittest.mock import MagicMock

import pytest


# ── Dependency registry ────────────────────────────────────────────────


@dataclass(frozen=True)
class Dependency:
    """A package the suite cares about, and why."""

    module: str
    purpose: str
    install: str


#: Pure-Python libraries from ``requirements.txt``.  Mockable as a last resort
#: because they cannot make the product act, only make it talk.
CORE_LIBRARIES: tuple[Dependency, ...] = (
    Dependency("loguru", "structured logging", "pip install -r requirements.txt"),
    Dependency("rich", "terminal rendering", "pip install -r requirements.txt"),
    Dependency("requests", "HTTP for model providers", "pip install -r requirements.txt"),
    Dependency("yaml", "skill and topology parsing", "pip install -r requirements.txt"),
    Dependency("numpy", "audio buffers", "pip install -r requirements.txt"),
    Dependency("mcp", "Model Context Protocol client/server", "pip install -r requirements.txt"),
)

#: The packages ARADHYA acts *through*.  Never mocked — a missing one is
#: reported and the tests that need it are skipped.
EFFECTORS: tuple[Dependency, ...] = (
    Dependency(
        "uiautomation",
        "desktop leg: list_windows, list_window_controls, invoke_control, "
        "set_control_text, focus_window",
        "pip install -r requirements-windows.txt",
    ),
    Dependency(
        "playwright",
        "browser leg: CDP-attach driver behind the browser_* tools",
        "pip install playwright  (no browser download needed — it attaches to "
        "your real Edge/Chrome over CDP)",
    ),
    Dependency(
        "sounddevice",
        "microphone capture for the voice loop",
        "pip install -r requirements-voice-activation.txt",
    ),
    Dependency(
        "pyttsx3",
        "spoken replies (monitor-off operation)",
        "pip install -r requirements-voice-activation.txt",
    ),
)

#: Packages that must NOT come back. ``selenium`` is out of the plan entirely
#: (decision memo 2026-08-07 §4 amendment 1 — "obsolete for agents"); the
#: browser tools attach over CDP instead.  Mocking it into ``sys.modules`` is
#: what let 12 broken browser tools look tested.
BANNED_MODULES: tuple[str, ...] = ("selenium",)


# ── Probing ────────────────────────────────────────────────────────────


@dataclass
class _ProbeResults:
    """What the real environment turned out to contain."""

    missing_effectors: list[tuple[Dependency, str]] = field(default_factory=list)
    mocked_core: list[tuple[Dependency, str]] = field(default_factory=list)


RESULTS = _ProbeResults()


def _real_import(module: str) -> tuple[bool, str]:
    """Import ``module`` for real. Returns (ok, error message).

    Uses a genuine import rather than ``find_spec`` because the effectors fail
    in ways a spec lookup cannot see — ``uiautomation`` can find its spec and
    still blow up on COM initialisation, which is a machine that cannot act.
    """
    try:
        importlib.import_module(module)
        return True, ""
    except Exception as error:  # ImportError, COM init, missing native lib
        return False, f"{type(error).__name__}: {error}"


def _probe_effectors() -> None:
    for dependency in EFFECTORS:
        ok, error = _real_import(dependency.module)
        if not ok:
            RESULTS.missing_effectors.append((dependency, error))


def _probe_core_libraries() -> None:
    """Import the core libraries; mock only what genuinely will not load."""
    for dependency in CORE_LIBRARIES:
        ok, error = _real_import(dependency.module)
        if ok:
            continue
        RESULTS.mocked_core.append((dependency, error))
        sys.modules[dependency.module] = MagicMock()


def is_available(module: str) -> bool:
    """True if the named effector imported for real in this process."""
    return all(dep.module != module for dep, _error in RESULTS.missing_effectors)


_probe_core_libraries()
_probe_effectors()


# ── Pytest wiring ──────────────────────────────────────────────────────


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "effector(name): test needs a real effector package (uiautomation, "
        "playwright, sounddevice, pyttsx3). Skipped-and-reported when missing, "
        "or failed when ARADHYA_REQUIRE_EFFECTORS=1.",
    )


def _strict() -> bool:
    return os.environ.get("ARADHYA_REQUIRE_EFFECTORS", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def _describe(module: str) -> Dependency | None:
    for dependency in (*EFFECTORS, *CORE_LIBRARIES):
        if dependency.module == module:
            return dependency
    return None


def _unavailable_reason(module: str) -> str:
    dependency = _describe(module)
    if dependency is None:
        return f"effector '{module}' is not a known dependency"
    return (
        f"effector '{dependency.module}' is not installed — "
        f"{dependency.purpose} cannot run. Install: {dependency.install}"
    )


def pytest_sessionstart(session: pytest.Session) -> None:
    """In strict mode, refuse to run at all with a missing effector.

    A machine that is supposed to be able to act should run this way: there is
    no useful "mostly green" when the thing under test is whether the product
    can touch the machine.
    """
    if not (_strict() and RESULTS.missing_effectors):
        return
    lines = ["ARADHYA_REQUIRE_EFFECTORS=1 and these effectors are missing:"]
    for dependency, error in RESULTS.missing_effectors:
        lines.append(f"  - {dependency.module} ({dependency.purpose})")
        lines.append(f"      {error}")
        lines.append(f"      install: {dependency.install}")
    raise pytest.UsageError("\n".join(lines))


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Skip tests marked for an effector that is not really installed."""
    for item in items:
        for marker in item.iter_markers(name="effector"):
            for module in marker.args:
                if not is_available(module):
                    item.add_marker(pytest.mark.skip(reason=_unavailable_reason(module)))


@pytest.fixture
def require_effector():
    """Skip the calling test unless the named effector really imported."""

    def _require(module: str):
        if not is_available(module):
            pytest.skip(_unavailable_reason(module))
        return importlib.import_module(module)

    return _require


def pytest_terminal_summary(terminalreporter, exitstatus, config) -> None:
    """Report every dependency the run had to work around.

    This is the whole point of the file: a run with missing effectors must not
    look identical to a run with all of them.  Anyone reading the tail of a
    green suite sees exactly which parts of the product could not be exercised.
    """
    if not RESULTS.missing_effectors and not RESULTS.mocked_core:
        terminalreporter.write_sep(
            "-", "effectors: all installed — the product can act", green=True
        )
        return

    if RESULTS.missing_effectors:
        terminalreporter.write_sep("=", "MISSING EFFECTORS — the product cannot act", red=True)
        for dependency, error in RESULTS.missing_effectors:
            terminalreporter.write_line(f"  {dependency.module}: {dependency.purpose}")
            terminalreporter.write_line(f"      {error}")
            terminalreporter.write_line(f"      install: {dependency.install}")
        terminalreporter.write_line("")
        terminalreporter.write_line(
            "  Tests needing these were SKIPPED, not passed. A green run above "
            "does not mean these work."
        )
        if not _strict():
            terminalreporter.write_line(
                "  Set ARADHYA_REQUIRE_EFFECTORS=1 to make missing effectors fail the run."
            )

    if RESULTS.mocked_core:
        terminalreporter.write_sep("=", "MOCKED CORE LIBRARIES — incomplete dev env", yellow=True)
        for dependency, error in RESULTS.mocked_core:
            terminalreporter.write_line(f"  {dependency.module}: {error}")
            terminalreporter.write_line(f"      install: {dependency.install}")
