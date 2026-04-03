"""Tool invocation ABI and execution wrappers."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Callable

from hephaestus.tools.permissions import PermissionPolicy


@dataclass
class ToolContext:
    """Runtime context passed to tools during execution."""
    policy: PermissionPolicy


class ToolInvocationError(Exception):
    """Raised when a tool fails during execution."""


class ToolInvocation:
    """
    Canonical ABI wrapper for built-in tools.

    Ensures that tools cannot be executed as free-floating functions
    without passing through the central permission registry and
    runtime context.
    """

    def __init__(self, name: str, handler: Callable[..., Any]) -> None:
        self.name = name
        self.handler = handler

    async def execute(self, context: ToolContext, **kwargs: Any) -> Any:
        """Execute the tool safely within the provided context."""
        if not context.policy.check(self.name):
            denial = context.policy.explain_denial(self.name)
            raise PermissionError(denial)
            
        try:
            if asyncio.iscoroutinefunction(self.handler):
                return await self.handler(context, **kwargs)
            return self.handler(context, **kwargs)
        except Exception as exc:
            raise ToolInvocationError(f"Tool error ({self.name}): {exc}") from exc
