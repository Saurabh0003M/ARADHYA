"""Model Context Protocol (MCP) Client Manager.

This module provides a unified way to connect to external MCP servers,
fetch their tools, and expose them to Aradhya's ToolRegistry.
"""
from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path
from typing import Any, Callable

from loguru import logger
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession
from mcp.types import CallToolResult

from src.aradhya.tools.tool_registry import ToolDefinition


class MCPServer:
    """Represents a connection to a single MCP server."""

    def __init__(self, name: str, command: str, args: list[str], env: dict[str, str] | None = None) -> None:
        self.name = name
        self.command = command
        self.args = args
        self.env = env
        self.session: ClientSession | None = None
        self._exit_stack = None
        self._tools: list[ToolDefinition] = []

    async def connect(self) -> None:
        from contextlib import AsyncExitStack
        self._exit_stack = AsyncExitStack()
        try:
            params = StdioServerParameters(command=self.command, args=self.args, env=self.env)
            read, write = await self._exit_stack.enter_async_context(stdio_client(params))
            self.session = await self._exit_stack.enter_async_context(ClientSession(read, write))
            await self.session.initialize()
            logger.info(f"MCP server '{self.name}' connected.")
        except Exception as e:
            logger.error(f"Failed to connect MCP server '{self.name}': {e}")
            if self._exit_stack:
                await self._exit_stack.aclose()
            raise

    async def fetch_tools(self) -> list[ToolDefinition]:
        if not self.session:
            return []

        try:
            response = await self.session.list_tools()
            tools = []
            for mcp_tool in response.tools:
                tools.append(ToolDefinition(
                    name=f"{self.name}__{mcp_tool.name}",
                    description=mcp_tool.description or f"MCP tool from {self.name}",
                    parameters=mcp_tool.inputSchema,
                    handler=lambda **kwargs: "Not bound", # We map func later in the manager
                ))
            self._tools = tools
            return tools
        except Exception as e:
            logger.error(f"Failed to list tools for MCP server '{self.name}': {e}")
            return []

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
        if not self.session:
            return "Error: MCP session is not connected."

        # Strip the prefix to get the original tool name
        original_name = tool_name.split("__", 1)[-1]
        try:
            result: CallToolResult = await self.session.call_tool(original_name, arguments)
            text_outputs = []
            for content in result.content:
                if content.type == "text":
                    text_outputs.append(content.text)
            return "\n".join(text_outputs)
        except Exception as e:
            logger.error(f"MCP tool call failed: {e}")
            return f"Error executing tool '{tool_name}': {e}"

    async def close(self) -> None:
        if self._exit_stack:
            try:
                await self._exit_stack.aclose()
            except Exception as e:
                logger.error(f"Error closing MCP server '{self.name}': {e}")
            self._exit_stack = None
            self.session = None


class MCPManager:
    """Manages multiple MCP server connections in a background asyncio loop."""

    def __init__(self) -> None:
        self.servers: dict[str, MCPServer] = {}
        self.loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="mcp-thread")
        self._running = False
        self._connected = False

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_forever()
        finally:
            self.loop.close()

    def start(self) -> None:
        if not self._running:
            self._running = True
            self._thread.start()

    def stop(self) -> None:
        if self._running:
            async def close_all():
                for server in self.servers.values():
                    await server.close()

            future = asyncio.run_coroutine_threadsafe(close_all(), self.loop)
            try:
                future.result(timeout=5)
            except Exception as e:
                logger.error(f"Error while stopping MCP servers: {e}")

            self.loop.call_soon_threadsafe(self.loop.stop)
            self._thread.join(timeout=5)
            self._running = False
            self._connected = False

    def load_from_profile(self, profile_path: Path) -> None:
        """Loads MCP server configurations from profile.json."""
        if not profile_path.is_file():
            return
        try:
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            mcp_config = profile.get("mcp_servers", {})
            for name, config in mcp_config.items():
                if isinstance(config, dict) and "command" in config and "args" in config:
                    self.add_server(
                        name=name,
                        command=config["command"],
                        args=config["args"],
                        env=config.get("env")
                    )
        except Exception as e:
            logger.error(f"Failed to load MCP config: {e}")

    def add_server(self, name: str, command: str, args: list[str], env: dict[str, str] | None = None) -> None:
        if name in self.servers:
            logger.warning(f"MCP server '{name}' already exists.")
            return
        server = MCPServer(name, command, args, env)
        self.servers[name] = server
        logger.info(f"Loaded MCP server config: {name}")

    def connect_and_register_tools(self, tool_registry: Any) -> None:
        """Connects to all configured servers and registers their tools synchronously."""
        if not self.servers:
            return

        if not self._running:
            self.start()

        if self._connected:
            # Re-register tools that we already fetched
            for server in self.servers.values():
                self._register_server_tools(server, server._tools, tool_registry)
            return

        async def _connect_and_fetch():
            all_tools = []
            for name, server in self.servers.items():
                try:
                    await server.connect()
                    tools = await server.fetch_tools()
                    all_tools.extend([(server, t) for t in tools])
                except Exception as e:
                    logger.error(f"Error setting up MCP server {name}: {e}")
            return all_tools

        try:
            future = asyncio.run_coroutine_threadsafe(_connect_and_fetch(), self.loop)
            tools_with_server = future.result(timeout=10) # 10s timeout for MCP boot

            for server, tool in tools_with_server:
                self._register_server_tools(server, [tool], tool_registry)

            self._connected = True
        except Exception as e:
            logger.error(f"Failed to connect and register MCP tools: {e}")

    def _register_server_tools(self, server: MCPServer, tools: list[ToolDefinition], tool_registry: Any) -> None:
        for tool in tools:
            def make_callable(srv: MCPServer, t_name: str) -> Callable:
                def tool_func(**kwargs) -> str:
                    fut = asyncio.run_coroutine_threadsafe(srv.call_tool(t_name, kwargs), self.loop)
                    try:
                        return fut.result(timeout=60) # 60s timeout for tool execution
                    except Exception as e:
                        return f"MCP tool execution failed: {e}"

                # Make it look like a normal function with a docstring
                tool_func.__name__ = t_name
                tool_func.__doc__ = f"Executes {t_name} via MCP."
                return tool_func

            bound_func = make_callable(server, tool.name)

            tool_def = ToolDefinition(
                name=tool.name,
                description=tool.description,
                parameters=tool.parameters,
                handler=bound_func,
                requires_confirmation=False, # Managed by ToolRuntimePolicy later
            )
            tool_registry.register(tool_def)
            logger.info(f"Registered MCP tool: {tool.name}")
