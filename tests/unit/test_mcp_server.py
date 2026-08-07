"""The MCP boundary must not be a way around the policy gate.

Decision memo 2026-08-07 §1 makes ARADHYA an MCP server first, which means an
external harness — OpenCode, Claude Code, Microsoft's shell — becomes a caller
of these tools. The tests below exist to pin the one property that makes that
safe: **a tool call arriving over MCP is gated exactly like a local one.**

The headline case is ``test_dangerous_tool_is_denied_when_no_gate_is_configured``:
a caller must not obtain a confirmation-gated tool by simply not supplying a
confirmation gate.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.aradhya.mcp_server import (
    GATE_DENIAL,
    NO_GATE_DENIAL,
    AradhyaMCPServer,
    build_tool_registry,
)
from src.aradhya.tools.runtime_policy import ToolRuntimePolicy
from src.aradhya.tools.tool_registry import ToolDefinition, ToolRegistry


# ── a tiny tool table with one safe and one dangerous tool ─────────────

CALLS: list[tuple[str, dict]] = []


def _safe_handler(**kwargs) -> str:
    CALLS.append(("safe", kwargs))
    return "safe tool ran"


def _dangerous_handler(**kwargs) -> str:
    CALLS.append(("dangerous", kwargs))
    return "DANGEROUS TOOL RAN"


def _registry(policy: ToolRuntimePolicy | None) -> ToolRegistry:
    registry = ToolRegistry(policy=policy)
    registry.register(
        ToolDefinition(
            name="read_thing",
            description="A read-only tool.",
            parameters={"type": "object", "properties": {}},
            handler=_safe_handler,
            requires_confirmation=False,
        )
    )
    registry.register(
        ToolDefinition(
            name="break_thing",
            description="A tool that changes the machine.",
            parameters={"type": "object", "properties": {}},
            handler=_dangerous_handler,
            requires_confirmation=True,
        )
    )
    return registry


def _live_policy() -> ToolRuntimePolicy:
    """A permissive policy — so a denial can only come from the gate."""
    return ToolRuntimePolicy(
        allowed_roots=(Path.home(),),
        live_execution_enabled=True,
        mutation_granted=False,
    )


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    CALLS.clear()
    # Never touch the user's real allowlist or audit log from a unit test.
    from src.aradhya.tools import approved_rules

    class _NoApprovals:
        def is_approved(self, *_a, **_k) -> bool:
            return False

        def record_approval(self, *_a, **_k) -> None:
            self.recorded = True

    stub = _NoApprovals()
    monkeypatch.setattr(approved_rules, "get_approved_rules", lambda *a, **k: stub)
    yield stub
    CALLS.clear()


class _Audit:
    def __init__(self) -> None:
        self.entries: list[dict] = []

    def log_tool_call(self, **kwargs) -> None:
        self.entries.append(kwargs)


def _server(gate=None, policy=None, audit=None) -> AradhyaMCPServer:
    return AradhyaMCPServer(
        registry=_registry(policy or _live_policy()),
        confirmation_gate=gate,
        audit=audit or _Audit(),
    )


# ── the headline invariant ─────────────────────────────────────────────


def test_dangerous_tool_is_denied_when_no_gate_is_configured():
    """A caller must not get a gated tool by omitting the gate."""
    server = _server(gate=None)

    output = server.call_tool("break_thing", {"target": "everything"})

    assert output == NO_GATE_DENIAL.format(tool="break_thing")
    assert CALLS == [], "the dangerous tool executed despite being denied"


def test_denial_explains_it_is_policy_not_a_missing_feature():
    """Wording matters: a model told 'not supported' retries forever."""
    message = NO_GATE_DENIAL.format(tool="break_thing")
    assert "denied without executing" in message
    assert "requires confirmation" in message


def test_safe_tool_still_runs_with_no_gate():
    """Fail-closed must not mean fail-useless."""
    server = _server(gate=None)
    assert server.call_tool("read_thing", {}) == "safe tool ran"
    assert CALLS == [("safe", {})]


# ── the gate, when there is one ────────────────────────────────────────


def test_dangerous_tool_is_denied_when_the_user_says_no():
    server = _server(gate=lambda name, args: (False, False))
    output = server.call_tool("break_thing", {})
    assert output == GATE_DENIAL.format(tool="break_thing")
    assert CALLS == []


def test_dangerous_tool_runs_when_the_user_approves():
    server = _server(gate=lambda name, args: (True, False))
    assert server.call_tool("break_thing", {}) == "DANGEROUS TOOL RAN"
    assert CALLS == [("dangerous", {})]


def test_approval_is_recorded_for_the_allowlist(_reset):
    server = _server(gate=lambda name, args: (True, True))
    server.call_tool("break_thing", {})
    assert getattr(_reset, "recorded", False), "persist=True was not recorded"


def test_approval_is_scoped_to_the_one_call():
    """The grant must not leak into the long-lived registry."""
    server = _server(gate=lambda name, args: (True, False))
    server.call_tool("break_thing", {})
    assert server.registry.policy.mutation_granted is False


# ── the runtime policy still runs underneath ───────────────────────────


def test_policy_still_blocks_when_live_execution_is_off():
    """Approving a call is not a way around allow_live_execution: false."""
    dry_run = ToolRuntimePolicy(
        allowed_roots=(Path.home(),),
        live_execution_enabled=False,
        mutation_granted=False,
    )
    server = _server(gate=lambda name, args: (True, False), policy=dry_run)

    output = server.call_tool("break_thing", {})

    assert "allow_live_execution" in output
    assert CALLS == [], "a dry-run policy let a mutating tool execute"


def test_server_refuses_a_registry_with_no_policy():
    """policy=None makes execute_tool run everything unchecked."""
    with pytest.raises(ValueError, match="no ToolRuntimePolicy"):
        AradhyaMCPServer(registry=_registry(None))


def test_unknown_tool_is_reported_not_raised():
    server = _server(gate=None)
    assert "Unknown tool" in server.call_tool("no_such_tool", {})


# ── dispatch reports failure as failure ────────────────────────────────
#
# The MCP wrapper turns this boolean into isError. A denial that comes back as
# isError=False gets reported by the calling harness as a completed action.


@pytest.mark.parametrize(
    "name, gate",
    [
        ("break_thing", None),                          # no gate configured
        ("break_thing", lambda n, a: (False, False)),    # user said no
        ("no_such_tool", None),                          # unknown tool
    ],
)
def test_dispatch_reports_denials_as_failures(name, gate):
    succeeded, _output = _server(gate=gate).dispatch(name, {})
    assert succeeded is False


def test_dispatch_reports_success_as_success():
    succeeded, output = _server(gate=None).dispatch("read_thing", {})
    assert succeeded is True
    assert output == "safe tool ran"


def test_dispatch_reports_a_dry_run_block_as_failure():
    dry_run = ToolRuntimePolicy(
        allowed_roots=(Path.home(),), live_execution_enabled=False
    )
    succeeded, output = _server(
        gate=lambda n, a: (True, False), policy=dry_run
    ).dispatch("break_thing", {})
    assert succeeded is False
    assert "allow_live_execution" in output


# ── audit ──────────────────────────────────────────────────────────────


def test_every_mcp_call_is_audited_as_mcp():
    audit = _Audit()
    server = _server(gate=lambda name, args: (True, False), audit=audit)
    server.call_tool("read_thing", {})
    server.call_tool("break_thing", {})

    assert len(audit.entries) == 2
    assert {entry["source"] for entry in audit.entries} == {"mcp"}
    assert [entry["tool_name"] for entry in audit.entries] == ["read_thing", "break_thing"]


def test_denials_are_audited_too():
    """A refusal is a security event; it has to be in the record."""
    audit = _Audit()
    server = _server(gate=None, audit=audit)
    server.call_tool("break_thing", {})

    assert len(audit.entries) == 1
    assert audit.entries[0]["success"] is False
    assert audit.entries[0]["source"] == "mcp"


# ── the gate a stdio server picks ──────────────────────────────────────
#
# A stdio server's stdin IS the protocol stream, so there is no interactive
# option: a gate that read stdin to ask y/n would eat the client's next
# request. What is left is fail-closed, or an explicit session unlock.


@pytest.mark.parametrize("value", ["", "deny", "off", "none", "DENY", "nonsense", "yes"])
def test_gate_from_env_fails_closed_by_default(monkeypatch, value):
    from src.aradhya.mcp_server import GATE_ENV_VAR, gate_from_env

    monkeypatch.setenv(GATE_ENV_VAR, value)
    assert gate_from_env() is None


def test_gate_from_env_unset_fails_closed(monkeypatch):
    from src.aradhya.mcp_server import GATE_ENV_VAR, gate_from_env

    monkeypatch.delenv(GATE_ENV_VAR, raising=False)
    assert gate_from_env() is None


def test_session_unlock_must_be_asked_for_by_name(monkeypatch):
    from src.aradhya.mcp_server import GATE_ENV_VAR, SessionUnlockGate, gate_from_env

    monkeypatch.setenv(GATE_ENV_VAR, "unlocked")
    assert isinstance(gate_from_env(), SessionUnlockGate)


def test_session_unlock_never_persists_an_approval():
    """The unlock lapses with the process; it must not write the allowlist."""
    from src.aradhya.mcp_server import SessionUnlockGate

    approved, persist = SessionUnlockGate()("invoke_control", {"a": 1})
    assert approved is True
    assert persist is False


# ── schema exposure ────────────────────────────────────────────────────


def test_list_tools_uses_the_mcp_schema_shape():
    server = _server()
    tools = server.list_tools()
    assert {tool["name"] for tool in tools} == {"read_thing", "break_thing"}
    for tool in tools:
        assert tool["description"]
        assert tool["inputSchema"]["type"] == "object"


# ── parity with the local registry ─────────────────────────────────────


def test_mcp_exposes_the_same_tools_as_the_local_registry():
    """A tool available locally but not over MCP vanishes on a front-end swap."""
    from src.aradhya.assistant_core import AradhyaAssistant

    policy = _live_policy()
    mcp_names = {tool["name"] for tool in AradhyaMCPServer(build_tool_registry(policy)).list_tools()}

    local = AradhyaAssistant._build_tool_registry_from_policy(
        _FakeCore(), policy  # type: ignore[arg-type]
    )
    local_names = {entry["function"]["name"] for entry in local.list_tools()}

    assert mcp_names == local_names, (
        f"only local: {sorted(local_names - mcp_names)}; "
        f"only MCP: {sorted(mcp_names - local_names)}"
    )


class _FakeCore:
    """Just enough of AradhyaAssistant for _build_tool_registry_from_policy."""

    mcp_manager = None


def test_the_registry_the_server_builds_is_not_empty():
    registry = build_tool_registry(_live_policy())
    assert registry.count > 30
    assert registry.get("list_windows") is not None
    assert registry.get("browser_read") is not None


def test_dangerous_tools_keep_their_flags_over_mcp():
    """The flags are the gate; over MCP they must read the same."""
    registry = build_tool_registry(_live_policy())
    for name in ("run_command", "write_file", "browser_click", "browser_type",
                 "browser_execute_js", "invoke_control", "set_control_text"):
        assert registry.requires_confirmation(name) is True, f"{name} lost its flag"
    for name in ("list_windows", "list_window_controls", "browser_read"):
        assert registry.requires_confirmation(name) is False, f"{name} gained a flag"
