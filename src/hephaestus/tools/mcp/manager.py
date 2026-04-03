"""MCP server manager — orchestrates multiple MCP server connections."""

from __future__ import annotations

from hephaestus.tools.mcp.client import MCPClient, MCPServerConfig, MCPTool
from hephaestus.tools.permissions import PermissionPolicy
from hephaestus.tools.registry import ToolDefinition, ToolRegistry


class MCPManager:
    """Manages multiple MCP servers and bridges their tools into the ToolRegistry."""

    def __init__(
        self,
        tool_registry: ToolRegistry,
        permission_policy: PermissionPolicy | None = None,
    ) -> None:
        self._registry = tool_registry
        self._policy = permission_policy
        self._clients: dict[str, MCPClient] = {}
        self._server_tools: dict[str, list[MCPTool]] = {}

    async def add_server(self, config: MCPServerConfig) -> None:
        """Start a server, discover its tools, and register them."""
        client = MCPClient(config)
        await client.start()
        tools = await client.discover_tools()

        self._clients[config.name] = client
        self._server_tools[config.name] = tools

        for tool in tools:
            # Create a closure bound to the qualified name so that runtime can invoke it
            async def _make_handler(qname: str) -> Any:
                async def _handler(**kwargs: Any) -> str:
                    return await self.call(qname, kwargs)
                return _handler

            self._registry.register(ToolDefinition(
                name=tool.qualified_name,
                description=tool.description,
                input_schema=tool.input_schema,
                category="dangerous",
                handler=await _make_handler(tool.qualified_name),
            ))

    async def remove_server(self, name: str) -> None:
        """Shut down a server and unregister its tools."""
        if name not in self._clients:
            raise KeyError(f"No server named '{name}'")

        for tool in self._server_tools.get(name, []):
            self._registry._tools.pop(tool.qualified_name, None)

        await self._clients[name].shutdown()
        del self._clients[name]
        del self._server_tools[name]

    def list_servers(self) -> list[str]:
        """Return names of active servers."""
        return list(self._clients.keys())

    def list_server_tools(self, name: str) -> list[MCPTool]:
        """Return tools discovered from a specific server."""
        if name not in self._server_tools:
            raise KeyError(f"No server named '{name}'")
        return list(self._server_tools[name])

    async def call(self, qualified_name: str, arguments: dict) -> str:
        """Route a tool call to the correct server."""
        parts = qualified_name.split(".", 1)
        if len(parts) != 2:
            raise ValueError(
                f"Invalid qualified tool name '{qualified_name}': "
                "expected 'server_name.tool_name'"
            )
        server_name, tool_name = parts

        if server_name not in self._clients:
            raise KeyError(f"No server named '{server_name}'")

        if self._policy is not None and not self._policy.check(qualified_name):
            raise PermissionError(self._policy.explain_denial(qualified_name))

        return await self._clients[server_name].call_tool(tool_name, arguments)

    async def shutdown_all(self) -> None:
        """Shut down all servers gracefully."""
        for name in list(self._clients.keys()):
            try:
                await self.remove_server(name)
            except Exception:
                pass
