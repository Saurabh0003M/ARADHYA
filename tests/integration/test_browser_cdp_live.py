"""Live CDP tests — a real Edge/Chrome, no mocks anywhere.

These are the tests that would have caught the Stage 0 problem: they fail if
the browser leg cannot actually act. They launch a real browser, so they live
in ``tests/integration/`` and are not part of the fast unit run:

    venv\\Scripts\\python.exe -m pytest tests/integration -q

Every test is marked ``@pytest.mark.effector("playwright")`` so a machine
without the driver skips-and-reports instead of passing.
"""

from __future__ import annotations

import pytest

from src.aradhya.browser_cdp import (
    CdpBrowserBackend,
    PageSnapshot,
    cdp_endpoint,
)

pytestmark = pytest.mark.effector("playwright")


FIXTURE_HTML = """<!doctype html><title>ARADHYA CDP fixture</title>
<h1>Sign in</h1>
<form>
  <label for="email">Email address</label>
  <input id="email" name="email" type="text" value="saurabh@example.com">
  <label for="pw">Password</label>
  <input id="pw" name="pw" type="password" value="hunter2">
  <select id="plan"><option>Free</option><option>Pro</option></select>
  <button id="submit-btn" type="button">Sign in</button>
  <button id="cancel-btn" type="button" disabled>Cancel</button>
</form>
<a href="/help" aria-label="Get help">Help</a>
<div role="alert">Session expired</div>
<ul role="list"><li role="listitem">structural noise</li></ul>
<input type="hidden" name="csrf" value="should-not-appear">
"""


@pytest.fixture(scope="module")
def fixture_page(tmp_path_factory):
    path = tmp_path_factory.mktemp("cdp") / "fixture.html"
    path.write_text(FIXTURE_HTML, encoding="utf-8")
    return path.as_uri()


@pytest.fixture(scope="module")
def live_backend():
    backend = CdpBrowserBackend()
    ok, message = backend.attach()
    if not ok:
        pytest.skip(f"could not attach a browser over CDP: {message}")
    yield backend
    backend.close()


def test_attach_reports_the_port_it_reached(live_backend):
    assert live_backend.attached() is True
    assert cdp_endpoint(9222, timeout=2.0) != ""


def test_navigate_reaches_the_page(live_backend, fixture_page):
    ok, message = live_backend.navigate(fixture_page)
    assert ok is True
    assert "ARADHYA CDP fixture" in message


def test_snapshot_is_a_structured_element_map(live_backend, fixture_page):
    live_backend.navigate(fixture_page)
    snapshot = live_backend.snapshot()
    assert isinstance(snapshot, PageSnapshot)

    by_id = {element.element_id: element for element in snapshot.elements}
    assert by_id["email"].role == "textbox"
    assert by_id["email"].name == "Email address"      # label, not innerText
    assert by_id["email"].value == "saurabh@example.com"
    assert by_id["submit-btn"].role == "button"
    assert by_id["cancel-btn"].enabled is False


def test_snapshot_never_exposes_a_password_value(live_backend, fixture_page):
    """Human-only line: a password field's value must not reach the model."""
    live_backend.navigate(fixture_page)
    snapshot = live_backend.snapshot()
    passwords = [e for e in snapshot.elements if e.role == "password"]
    assert passwords, "the password field should still be listed"
    assert all(element.value == "" for element in passwords)
    assert "hunter2" not in str(snapshot.to_dict())


def test_snapshot_omits_hidden_and_structural_elements(live_backend, fixture_page):
    live_backend.navigate(fixture_page)
    snapshot = live_backend.snapshot()
    roles = {element.role for element in snapshot.elements}
    assert "list" not in roles and "listitem" not in roles
    assert all("should-not-appear" not in element.value for element in snapshot.elements)
    # ...but a meaningful non-clickable role survives
    assert "alert" in roles


def test_select_is_not_named_after_its_options(live_backend, fixture_page):
    """A <select>'s innerText is its options; that is not its label."""
    live_backend.navigate(fixture_page)
    snapshot = live_backend.snapshot()
    plan = next(e for e in snapshot.elements if e.element_id == "plan")
    assert plan.role == "combobox"
    assert "Free" not in plan.name
    assert plan.value == "Free"


def test_snapshot_filter_narrows_by_role(live_backend, fixture_page):
    live_backend.navigate(fixture_page)
    snapshot = live_backend.snapshot("button")
    assert snapshot.elements
    assert all(element.role == "button" for element in snapshot.elements)


def test_element_names_are_single_line(live_backend, fixture_page):
    """format_snapshot prints one element per line; a newline would forge rows."""
    live_backend.navigate(fixture_page)
    snapshot = live_backend.snapshot()
    assert all("\n" not in element.name for element in snapshot.elements)
