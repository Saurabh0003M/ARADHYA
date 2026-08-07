"""Expose ARADHYA's ToolRegistry over MCP (stdio).

Decision memo 2026-08-07 §1: ARADHYA ships as an **MCP server** exposing its
UIA/browser effectors behind the existing `ToolRegistry` policy gate, and the
voice shell is one thin client of that server rather than a second product.

The whole point is that an external harness — the `lite/` voice loop, OpenCode,
Claude Code, or Microsoft's own shell via the On-Device Registry — calls these
tools **through the policy gate**, not around it. So the invariant this module
exists to hold is:

    A tool call arriving over MCP is gated exactly like a local one.

Concretely, and in this order:

1. ``ToolDefinition.requires_confirmation`` is consulted first. If the tool is
   flagged and **no confirmation gate is configured, the call is denied** — it
   does not fall through to the registry, and it does not execute. A remote
   caller cannot obtain a dangerous tool by simply not providing a gate.
2. The persisted approved-rules allowlist is checked before prompting, same as
   ``AgentLoop._apply_dangerous_tools_gate``, so an approval the user already
   gave is honoured and keyed on the same (tool, args) hash.
3. ``ToolRuntimePolicy`` runs inside ``ToolRegistry.execute_tool``. Nothing here
   bypasses it. An approved confirmation upgrades ``mutation_granted`` for that
   one call only, via ``ToolRegistry.with_policy`` — it never mutates the
   long-lived registry, so one caller's grant cannot leak into another's.
4. Every call is written to ``audit.jsonl`` with ``source="mcp"``, so an
   MCP-originated action is distinguishable from a CLI one after the fact.

Refusing to serve at all is also a decision this module makes: a registry with
``policy=None`` executes everything unchecked, so constructing the server with
one raises rather than quietly exposing an ungated machine to the network of
whatever process is on the other end of the pipe.

Run it::

    venv\\Scripts\\python.exe -m src.aradhya.mcp_server
"""

from __future__ import annotations

import time
from dataclasses import replace
from typing import Any

from loguru import logger

from src.aradhya.confirmation_gates import ConfirmationGate
from src.aradhya.tools.runtime_policy import ToolRuntimePolicy
from src.aradhya.tools.tool_registry import ToolRegistry

SERVER_NAME = "aradhya"

#: Returned verbatim when a flagged tool is called with no gate in place. The
#: wording matters: the caller must understand this is a policy refusal, not a
#: missing feature, or a model will retry it forever.
NO_GATE_DENIAL = (
    "Tool '{tool}' requires confirmation and this MCP server has no "
    "confirmation gate configured, so it was denied without executing. "
    "Start the server with a gate (or approve this call in the ARADHYA CLI "
    "once, which records it in the approved-rules allowlist)."
)

GATE_DENIAL = "Tool '{tool}' was not approved by the user."


class ToolCallDenied(Exception):
    """A tool call was refused by policy, the gate, or the tool itself.

    Raised only at the transport edge: the MCP SDK turns a raised exception
    into ``isError=True``, which is what stops a caller reporting a refusal as
    a completed action.
    """


def build_tool_registry(policy: ToolRuntimePolicy) -> ToolRegistry:
    """Build a registry with ARADHYA's full tool catalogue under ``policy``.

    Mirrors ``AssistantCore._build_tool_registry_from_policy`` minus the MCP
    *client* manager (an MCP server that re-exported another server's tools
    would be a loop). ``tests/unit/test_mcp_server.py`` asserts the two stay in
    sync, because a tool that exists locally but not over MCP is a capability
    that silently vanishes when the front end changes.
    """
    from src.aradhya.learnings.learnings_engine import ALL_LEARNINGS_TOOLS
    from src.aradhya.skills.skill_installer import ALL_SKILL_INSTALLER_TOOLS
    from src.aradhya.tools.browser_tools import ALL_BROWSER_TOOLS
    from src.aradhya.tools.desktop_tools import ALL_DESKTOP_TOOLS
    from src.aradhya.tools.file_tools import ALL_FILE_TOOLS
    from src.aradhya.tools.hardware_tools import ALL_HARDWARE_TOOLS
    from src.aradhya.tools.maintenance_tools import ALL_MAINTENANCE_TOOLS
    from src.aradhya.tools.power_tools import ALL_POWER_TOOLS
    from src.aradhya.tools.profile_tools import ALL_PROFILE_TOOLS
    from src.aradhya.tools.scheduler_tool import ALL_SCHEDULER_TOOLS
    from src.aradhya.tools.session_tools import ALL_SESSION_TOOLS
    from src.aradhya.tools.shell_tools import ALL_SHELL_TOOLS
    from src.aradhya.tools.subagent_tools import ALL_SUBAGENT_TOOLS
    from src.aradhya.tools.system_tools import ALL_SYSTEM_TOOLS
    from src.aradhya.tools.vision_tools import ALL_VISION_TOOLS
    from src.aradhya.tools.web_tools import ALL_WEB_TOOLS

    registry = ToolRegistry(policy=policy)
    for tool in (
        *ALL_FILE_TOOLS,
        *ALL_SHELL_TOOLS,
        *ALL_SYSTEM_TOOLS,
        *ALL_SESSION_TOOLS,
        *ALL_WEB_TOOLS,
        *ALL_POWER_TOOLS,
        *ALL_BROWSER_TOOLS,
        *ALL_VISION_TOOLS,
        *ALL_SKILL_INSTALLER_TOOLS,
        *ALL_LEARNINGS_TOOLS,
        *ALL_SCHEDULER_TOOLS,
        *ALL_SUBAGENT_TOOLS,
        *ALL_MAINTENANCE_TOOLS,
        *ALL_HARDWARE_TOOLS,
        *ALL_PROFILE_TOOLS,
        *ALL_DESKTOP_TOOLS,
    ):
        registry.register_function(tool)
    return registry


class AradhyaMCPServer:
    """The gate-preserving bridge between MCP and the ToolRegistry.

    Deliberately transport-free: ``list_tools`` and ``call_tool`` are plain
    synchronous methods so the gating can be tested without a pipe, a client, or
    an event loop. ``build()`` wires them to an actual MCP server.
    """

    def __init__(
        self,
        registry: ToolRegistry,
        confirmation_gate: ConfirmationGate | None = None,
        audit: Any = None,
    ) -> None:
        if registry.policy is None:
            raise ValueError(
                "Refusing to serve a ToolRegistry with no ToolRuntimePolicy: "
                "execute_tool() would run every tool unchecked, including the "
                "confirmation-gated ones. Pass a ToolRuntimePolicy."
            )
        self.registry = registry
        self.confirmation_gate = confirmation_gate
        self._audit = audit

    # -- audit ------------------------------------------------------

    @property
    def audit(self) -> Any:
        if self._audit is None:
            from src.aradhya.audit_logger import get_audit_logger

            self._audit = get_audit_logger()
        return self._audit

    def _log(
        self,
        name: str,
        arguments: dict[str, Any],
        success: bool,
        output: str,
        started: float,
    ) -> None:
        try:
            self.audit.log_tool_call(
                tool_name=name,
                arguments=arguments,
                success=success,
                output_preview=output,
                source="mcp",
                wall_time_ms=int((time.time() - started) * 1000),
            )
        except Exception as error:  # auditing must never break a call
            logger.warning("MCP audit log failed for {}: {}", name, error)

    # -- the gate ---------------------------------------------------

    def _confirm(self, name: str, arguments: dict[str, Any]) -> tuple[bool, str]:
        """Apply the confirmation gate. Returns (allowed, denial message)."""
        if not self.registry.requires_confirmation(name):
            return True, ""

        from src.aradhya.tools.approved_rules import get_approved_rules

        rules = get_approved_rules()
        if rules.is_approved(name, arguments):
            logger.debug("MCP: '{}' pre-approved by the allowlist", name)
            return True, ""

        if self.confirmation_gate is None:
            # Fail closed. A caller must not get a dangerous tool by omission.
            return False, NO_GATE_DENIAL.format(tool=name)

        approved, persist = self.confirmation_gate(name, arguments)
        if not approved:
            return False, GATE_DENIAL.format(tool=name)
        rules.record_approval(name, arguments, persist=persist)
        return True, ""

    # -- the two operations MCP needs -------------------------------

    def list_tools(self) -> list[dict[str, Any]]:
        """Tool schemas, in the shape MCP wants (name/description/inputSchema)."""
        return [
            {
                "name": entry["function"]["name"],
                "description": entry["function"]["description"],
                "inputSchema": entry["function"]["parameters"],
            }
            for entry in self.registry.list_tools()
        ]

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> str:
        """Execute a tool for an MCP caller, through every local gate."""
        return self.dispatch(name, arguments)[1]

    def dispatch(
        self, name: str, arguments: dict[str, Any] | None = None
    ) -> tuple[bool, str]:
        """Execute a tool and report ``(succeeded, output)``.

        The boolean is what the MCP wrapper turns into ``isError``. A denial is
        a failure, not a successful call that happens to contain the word "no":
        a harness that reads ``isError=False`` will report the task done.
        """
        arguments = dict(arguments or {})
        started = time.time()

        if self.registry.get(name) is None:
            message = f"Unknown tool: {name}"
            self._log(name, arguments, False, message, started)
            return False, message

        allowed, denial = self._confirm(name, arguments)
        if not allowed:
            logger.info("MCP denied '{}': {}", name, denial)
            self._log(name, arguments, False, denial, started)
            return False, denial

        # The confirmation the caller just passed is what mutation_granted
        # means. Scope it to this call: with_policy shares the tool table but
        # not the grant.
        registry = self.registry
        if self.registry.requires_confirmation(name):
            registry = self.registry.with_policy(
                replace(self.registry.policy, mutation_granted=True)
            )

        result = registry.execute_tool(name, arguments, tool_call_id=f"mcp-{int(started * 1000)}")
        self._log(name, arguments, result.success, result.output, started)
        return result.success, result.output

    # -- transport --------------------------------------------------

    def build(self) -> Any:
        """Wire ``list_tools``/``call_tool`` onto a low-level MCP server."""
        import mcp.types as types
        from mcp.server import Server

        server = Server(SERVER_NAME)

        @server.list_tools()
        async def _list_tools() -> list[types.Tool]:
            return [types.Tool(**tool) for tool in self.list_tools()]

        @server.call_tool()
        async def _call_tool(
            name: str, arguments: dict[str, Any] | None = None
        ) -> list[types.TextContent]:
            import anyio.to_thread

            # Tool handlers are synchronous and several of them block (COM
            # calls, subprocesses, the CDP driver thread's queue). Running one
            # on the event loop would stall the whole server.
            success, output = await anyio.to_thread.run_sync(
                self.dispatch, name, arguments
            )
            if not success:
                # Raising is how this SDK sets isError=True. A denial that
                # comes back as a successful result gets reported as done.
                raise ToolCallDenied(output)
            return [types.TextContent(type="text", text=output)]

        return server

    async def run_stdio(self) -> None:
        """Serve over stdio until the client disconnects."""
        from mcp.server.stdio import stdio_server

        server = self.build()
        logger.info(
            "ARADHYA MCP server: {} tools, gate={}",
            self.registry.count,
            type(self.confirmation_gate).__name__ if self.confirmation_gate else "none",
        )
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream, write_stream, server.create_initialization_options()
            )


def default_policy() -> ToolRuntimePolicy:
    """The policy a standalone server starts with.

    Read and write are scoped to the user's home; live execution follows the
    persisted preference, so ``allow_live_execution: false`` still means
    dry-run — serving over MCP is not a way around it.
    """
    from pathlib import Path

    try:
        from src.aradhya.assistant_models import load_preferences

        preferences = load_preferences()
        roots = tuple(preferences.user_roots) or (Path.home(),)
        live = bool(preferences.allow_live_execution)
    except Exception as error:
        logger.warning("Could not load preferences ({}); defaulting to dry-run", error)
        roots = (Path.home(),)
        live = False
    return ToolRuntimePolicy(allowed_roots=roots, live_execution_enabled=live)


def main() -> None:
    import anyio

    from src.aradhya.confirmation_gates import CliConfirmationGate

    policy = default_policy()
    server = AradhyaMCPServer(
        registry=build_tool_registry(policy),
        # stdio is the MCP channel; the CLI gate prompts on the terminal, which
        # is a different stream, so a human can still approve interactively.
        confirmation_gate=CliConfirmationGate(),
    )
    anyio.run(server.run_stdio)


if __name__ == "__main__":
    main()
