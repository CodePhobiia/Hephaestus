"""MCP (Model Context Protocol) stdio integration for extensible tool discovery."""

from hephaestus.tools.mcp.client import MCPClient, MCPServerConfig, MCPTool
from hephaestus.tools.mcp.manager import MCPManager

__all__ = [
    "MCPClient",
    "MCPManager",
    "MCPServerConfig",
    "MCPTool",
]
