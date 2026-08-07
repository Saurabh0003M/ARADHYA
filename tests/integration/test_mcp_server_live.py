"""The MCP server over a real stdio pipe, driven by a real MCP client.

The unit tests pin the gating logic; these pin that the gating survives the
transport. They spawn ``src.aradhya.mcp_server`` as a subprocess **with no
confirmation gate** and check that an external caller — which is what OpenCode,
Claude Code or Microsoft's shell will be — cannot get a dangerous tool out of
it, while read-only tools work normally.

    venv\\Scripts\\python.exe -m pytest tests/integration -q
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]

#: Runs in the child process. No confirmation gate on purpose.
SERVER_BOOTSTRAP = f"""
import sys, anyio
sys.path.insert(0, r"{PROJECT_ROOT}")
from pathlib import Path
from src.aradhya.mcp_server import AradhyaMCPServer, build_tool_registry
from src.aradhya.tools.runtime_policy import ToolRuntimePolicy

policy = ToolRuntimePolicy(
    allowed_roots=(Path.home(),),
    live_execution_enabled=True,
    mutation_granted=False,
)
server = AradhyaMCPServer(registry=build_tool_registry(policy), confirmation_gate=None)
anyio.run(server.run_stdio)
"""


@pytest.fixture
def mcp_session():
    """Yield an async callable that runs a coroutine against a live server."""
    import anyio
    from mcp.client.session import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    def run(coroutine_factory):
        async def _main():
            env = dict(os.environ)
            env["PYTHONUTF8"] = "1"
            params = StdioServerParameters(
                command=sys.executable, args=["-c", SERVER_BOOTSTRAP], env=env
            )
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return await coroutine_factory(session)

        return anyio.run(_main)

    return run


def test_server_initializes_and_names_itself(mcp_session):
    async def check(session):
        result = await session.list_tools()
        return [tool.name for tool in result.tools]

    names = mcp_session(check)
    assert names, "the server exposed no tools"


def test_both_effector_legs_are_exposed(mcp_session):
    """The memo's point: the *effectors* are what ships over MCP."""

    async def check(session):
        result = await session.list_tools()
        return {tool.name for tool in result.tools}

    names = mcp_session(check)
    assert {
        "list_windows",
        "list_window_controls",
        "invoke_control",
        "set_control_text",
        "focus_window",
    } <= names
    assert {"browser_open", "browser_read", "browser_navigate"} <= names


def test_read_only_tool_works_over_the_pipe(mcp_session):
    async def check(session):
        return await session.call_tool("list_windows", {})

    result = mcp_session(check)
    assert result.isError is False
    assert "window(s)" in result.content[0].text


@pytest.mark.parametrize(
    "tool, arguments",
    [
        ("run_command", {"command": "echo this must not run"}),
        ("invoke_control", {"window_title": "Calculator", "control_name": "Nine"}),
        ("set_control_text", {"window_title": "Notepad", "control_name": "Text editor",
                              "text": "this must not be typed"}),
        ("write_file", {"path": "mcp-should-never-write.txt", "content": "x"}),
    ],
)
def test_dangerous_tools_are_denied_over_the_pipe(mcp_session, tool, arguments):
    """An external caller must not obtain these by omitting a gate."""

    async def check(session):
        return await session.call_tool(tool, arguments)

    result = mcp_session(check)
    assert result.isError is True, f"{tool} was not reported as an error"
    text = result.content[0].text
    assert "requires confirmation" in text or "denied" in text


def test_a_denial_is_reported_as_an_error_not_a_result(mcp_session):
    """isError=False on a refusal makes a harness report the task done."""

    async def check(session):
        return await session.call_tool("run_command", {"command": "echo no"})

    result = mcp_session(check)
    assert result.isError is True
