"""Conversation runtime: drives the model ↔ tool loop."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from hephaestus.session.schema import EntryType, Role, Session
from hephaestus.tools.permissions import PermissionPolicy
from hephaestus.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 10


@dataclass
class ToolCallRecord:
    """Record of a single tool invocation."""

    tool_use_id: str
    name: str
    input: dict[str, Any]
    output: str
    is_error: bool = False


@dataclass
class TurnResult:
    """Result from a single conversation turn."""

    text: str
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    rounds: int = 0


class ConversationRuntime:
    """Drives the adapter ↔ tool execution loop.

    Parameters
    ----------
    adapter:
        An LLM adapter that exposes ``generate_with_tools``.
    tool_registry:
        Registry of available tools with handlers.
    permission_policy:
        Controls which tools the runtime is allowed to execute.
    session:
        Session object for transcript recording.
    system_prompt:
        Optional system prompt sent with every request.
    max_rounds:
        Maximum tool-loop iterations per turn.
    """

    def __init__(
        self,
        adapter: Any,
        tool_registry: ToolRegistry,
        permission_policy: PermissionPolicy,
        session: Session,
        *,
        system_prompt: str | None = None,
        max_rounds: int = MAX_TOOL_ROUNDS,
    ) -> None:
        self.adapter = adapter
        self.registry = tool_registry
        self.policy = permission_policy
        self.session = session
        self.system_prompt = system_prompt
        self.max_rounds = max_rounds
        self._messages: list[dict[str, Any]] = []

    async def run_turn(self, user_message: str) -> str:
        """Process one user turn through the model, executing tools as needed.

        Returns the final assistant text response.
        """
        # Record user message in session and message list.
        self.session.append_entry(Role.USER.value, user_message)
        self._messages.append({"role": "user", "content": user_message})

        tool_specs = self.registry.to_api_schema()
        result = await self._tool_loop(tool_specs)

        # Record final assistant text in session.
        self.session.append_entry(Role.ASSISTANT.value, result.text)
        return result.text

    async def _tool_loop(self, tool_specs: list[dict[str, Any]]) -> TurnResult:
        """Run the generate → tool_use → result loop."""
        turn = TurnResult(text="", rounds=0)

        for _round in range(self.max_rounds):
            turn.rounds += 1

            gen = await self.adapter.generate_with_tools(
                self._messages,
                system=self.system_prompt,
                tools=tool_specs or None,
            )

            # No tool calls → final text response.
            if not gen.tool_calls:
                turn.text = gen.text
                self._messages.append(
                    {"role": "assistant", "content": gen.content_blocks}
                )
                return turn

            # Append assistant message with tool_use blocks.
            self._messages.append(
                {"role": "assistant", "content": gen.content_blocks}
            )

            # Execute each tool call.
            tool_results: list[dict[str, Any]] = []
            for tc in gen.tool_calls:
                record = await self._execute_tool(tc.id, tc.name, tc.input)
                turn.tool_calls.append(record)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tc.id,
                        "content": record.output,
                        "is_error": record.is_error,
                    }
                )

            # Feed tool results back.
            self._messages.append({"role": "user", "content": tool_results})

        # Exhausted rounds — return whatever text we have.
        turn.text = turn.text or "[max tool rounds reached]"
        return turn

    async def _execute_tool(
        self, tool_use_id: str, name: str, tool_input: dict[str, Any]
    ) -> ToolCallRecord:
        """Execute a single tool, checking permissions first."""
        # Record tool_use in session.
        self.session.append_entry(
            Role.ASSISTANT.value,
            f"tool_use: {name}",
            entry_type=EntryType.TOOL_USE.value,
            metadata={"tool_use_id": tool_use_id, "name": name, "input": tool_input},
        )

        # Permission check.
        if not self.policy.check(name):
            denial = self.policy.explain_denial(name)
            logger.warning("Tool denied: %s — %s", name, denial)
            self.session.append_entry(
                Role.TOOL.value,
                denial,
                entry_type=EntryType.TOOL_RESULT.value,
                metadata={"tool_use_id": tool_use_id, "is_error": True},
            )
            return ToolCallRecord(
                tool_use_id=tool_use_id,
                name=name,
                input=tool_input,
                output=denial,
                is_error=True,
            )

        # Look up handler.
        tool_def = self.registry.get(name)
        if tool_def is None or tool_def.handler is None:
            msg = f"No handler registered for tool '{name}'"
            self.session.append_entry(
                Role.TOOL.value,
                msg,
                entry_type=EntryType.TOOL_RESULT.value,
                metadata={"tool_use_id": tool_use_id, "is_error": True},
            )
            return ToolCallRecord(
                tool_use_id=tool_use_id,
                name=name,
                input=tool_input,
                output=msg,
                is_error=True,
            )

        # Execute.
        try:
            import asyncio

            if asyncio.iscoroutinefunction(tool_def.handler):
                output = await tool_def.handler(**tool_input)
            else:
                output = tool_def.handler(**tool_input)
            output_str = str(output)
            is_error = False
        except Exception as exc:
            output_str = f"Tool error ({name}): {exc}"
            is_error = True

        self.session.append_entry(
            Role.TOOL.value,
            output_str,
            entry_type=EntryType.TOOL_RESULT.value,
            metadata={"tool_use_id": tool_use_id, "is_error": is_error},
        )

        return ToolCallRecord(
            tool_use_id=tool_use_id,
            name=name,
            input=tool_input,
            output=output_str,
            is_error=is_error,
        )
