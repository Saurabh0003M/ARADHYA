"""Guard: the suite may never be green while the product cannot act.

The regression these tests exist for is real and shipped: ``tests/conftest.py``
used to install ``MagicMock()`` into ``sys.modules`` for ``selenium``,
``uiautomation``, ``sounddevice`` and friends.  Every import of an effector
succeeded inside the test process regardless of what was on the machine, so a
fully green run coexisted with a product whose every desktop and browser tool
returned "install <package>" to the user.

These tests fail if that shortcut comes back.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest

from tests.conftest import (
    BANNED_MODULES,
    CORE_LIBRARIES,
    EFFECTORS,
    RESULTS,
    is_available,
)


def _installed_mock_modules() -> list[str]:
    return [
        name
        for name, module in list(sys.modules.items())
        if isinstance(module, MagicMock)
    ]


def test_no_effector_is_faked_in_sys_modules() -> None:
    """No effector may be satisfied by a mock — present for real, or absent."""
    faked = [d.module for d in EFFECTORS if isinstance(sys.modules.get(d.module), MagicMock)]
    assert not faked, (
        f"Effector(s) {faked} are MagicMock in sys.modules. A mocked effector "
        "makes the suite green while the product cannot act. Install them, or "
        "let the tests that need them skip."
    )


def test_available_effectors_really_import() -> None:
    """``is_available`` must mean the real package, not a stand-in."""
    for dependency in EFFECTORS:
        if not is_available(dependency.module):
            continue
        module = sys.modules.get(dependency.module)
        assert module is not None, f"{dependency.module} reported available but is not imported"
        assert not isinstance(module, MagicMock), (
            f"{dependency.module} reported available but is a MagicMock"
        )


@pytest.mark.parametrize("banned", BANNED_MODULES)
def test_banned_module_is_not_installed_or_mocked(banned: str) -> None:
    """selenium is out of the plan; it must not creep back via a mock.

    Decision memo 2026-08-07 §4 amendment 1: selenium is "obsolete for agents".
    The browser tools attach over CDP instead. Mocking selenium is what let 12
    broken browser tools look tested.
    """
    module = sys.modules.get(banned)
    assert not isinstance(module, MagicMock), (
        f"'{banned}' is mocked into sys.modules. It is a banned dependency — "
        "remove the mock rather than pretending the package is there."
    )


def test_missing_effectors_are_recorded_not_swallowed() -> None:
    """Whatever is missing must be *named*, so the run can report it."""
    for dependency, error in RESULTS.missing_effectors:
        assert dependency.module, "a missing effector was recorded without a name"
        assert error, f"{dependency.module} was recorded missing with no reason"
        assert dependency.install, f"{dependency.module} was recorded with no install hint"


def test_every_effector_declares_why_it_matters() -> None:
    """A dependency with no stated purpose cannot be triaged when it breaks."""
    for dependency in (*EFFECTORS, *CORE_LIBRARIES):
        assert dependency.purpose, f"{dependency.module} has no stated purpose"
        assert dependency.install, f"{dependency.module} has no install instruction"


@pytest.mark.effector("uiautomation")
def test_uiautomation_can_enumerate_real_windows() -> None:
    """The desktop leg's floor: UIA answers about the real desktop.

    Skipped-and-reported when uiautomation is absent — which is the honest
    outcome, not a pass.
    """
    import uiautomation as auto

    root = auto.GetRootControl()
    assert root is not None
    children = root.GetChildren()
    assert isinstance(children, list)
