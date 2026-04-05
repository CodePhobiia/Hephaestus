"""MCP trust policy — per-server allow/deny and tool permission enforcement."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


class TrustViolation(Exception): # noqa: N818
    """Raised when a tool call violates the trust policy."""


@dataclass
class ServerTrustConfig:
    """Trust configuration for a single MCP server."""

    server_name: str
    allowed_tools: list[str] | None = None  # None = all allowed
    denied_tools: list[str] = field(default_factory=list)
    max_calls_per_minute: int = 60
    max_concurrent_calls: int = 5
    startup_grace_seconds: float = 10.0
    require_schema_validation: bool = True
    trust_level: str = "standard"  # trusted | standard | sandboxed


@dataclass
class MCPTrustPolicy:
    """Enforces per-server tool permissions and call limits."""

    default_trust: str = "standard"
    server_configs: dict[str, ServerTrustConfig] = field(default_factory=dict)
    global_denied_tools: list[str] = field(default_factory=list)
    _call_counts: dict[str, int] = field(default_factory=dict)

    def register_server(self, config: ServerTrustConfig) -> None:
        """Register trust configuration for a server."""
        self.server_configs[config.server_name] = config
        logger.info(
            "Trust policy registered for %s (level=%s, allowed=%s, denied=%s)",
            config.server_name,
            config.trust_level,
            config.allowed_tools or "all",
            config.denied_tools or "none",
        )

    def check_tool_allowed(self, server_name: str, tool_name: str) -> None:
        """Check if a tool call is allowed under the trust policy.

        Raises TrustViolation if denied.
        """
        # Global denials
        if tool_name in self.global_denied_tools:
            raise TrustViolation(f"Tool '{tool_name}' is globally denied")

        config = self.server_configs.get(server_name)
        if config is None:
            # Unknown server — use default trust
            if self.default_trust == "sandboxed":
                raise TrustViolation(
                    f"Unknown server '{server_name}' denied under sandboxed default trust"
                )
            return

        # Explicit deny list
        if tool_name in config.denied_tools:
            raise TrustViolation(f"Tool '{tool_name}' is denied for server '{server_name}'")

        # Explicit allow list (if set)
        if config.allowed_tools is not None and tool_name not in config.allowed_tools:
            raise TrustViolation(
                f"Tool '{tool_name}' is not in the allowed list for server '{server_name}'"
            )

    def validate_tool_schema(
        self, server_name: str, tool_name: str, schema: dict[str, Any]
    ) -> list[str]:
        """Validate a discovered tool's schema. Returns list of warnings."""
        warnings: list[str] = []

        config = self.server_configs.get(server_name)
        if config and not config.require_schema_validation:
            return warnings

        if not schema:
            warnings.append(f"{server_name}.{tool_name}: empty input schema")

        schema_type = schema.get("type")
        if schema_type and schema_type != "object":
            warnings.append(
                f"{server_name}.{tool_name}: input schema type is '{schema_type}', expected 'object'"
            )

        properties = schema.get("properties", {})
        if not properties and schema.get("type") == "object":
            warnings.append(f"{server_name}.{tool_name}: schema has no properties defined")

        return warnings

    def record_call(self, server_name: str) -> None:
        """Record a tool call for rate tracking."""
        self._call_counts[server_name] = self._call_counts.get(server_name, 0) + 1

    def get_config(self, server_name: str) -> ServerTrustConfig:
        """Get trust config for a server, creating a default if needed."""
        if server_name not in self.server_configs:
            self.server_configs[server_name] = ServerTrustConfig(
                server_name=server_name,
                trust_level=self.default_trust,
            )
        return self.server_configs[server_name]

    def summary(self) -> dict[str, Any]:
        """Return a serializable summary of the trust policy."""
        return {
            "default_trust": self.default_trust,
            "global_denied_tools": list(self.global_denied_tools),
            "servers": {
                name: {
                    "trust_level": cfg.trust_level,
                    "allowed_tools": cfg.allowed_tools,
                    "denied_tools": cfg.denied_tools,
                    "require_schema_validation": cfg.require_schema_validation,
                }
                for name, cfg in self.server_configs.items()
            },
        }


__all__ = [
    "MCPTrustPolicy",
    "ServerTrustConfig",
    "TrustViolation",
]
