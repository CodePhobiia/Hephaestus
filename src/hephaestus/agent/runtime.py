"""Conversation runtime: drives the model ↔ tool loop."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from hephaestus.session.deliberation import DeliberationGraph
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
        graph = DeliberationGraph(
            workflow_kind="conversation",
            goal=user_message,
            plan=["llm_generate", "tool_loop", "assistant_reply"],
            metadata={"max_rounds": self.max_rounds},
        )
        graph.record_stage(
            "user_turn",
            "Conversation turn started.",
            status="started",
            payload={"message_length": len(user_message)},
        )
        self.session.add_deliberation_graph(graph)

        # Record user message in session and message list.
        self.session.append_entry(Role.USER.value, user_message)
        self._messages.append({"role": "user", "content": user_message})

        tool_specs = self.registry.to_api_schema()
        result = await self._tool_loop(tool_specs, graph)

        # Record final assistant text in session.
        self.session.append_entry(Role.ASSISTANT.value, result.text)
        graph.record_stage(
            "assistant_reply",
            "Assistant produced a final reply.",
            payload={"tool_call_count": len(result.tool_calls), "rounds": result.rounds},
        )
        graph.stop_reason = "assistant_reply"
        self.session.add_deliberation_graph(graph)
        return result.text

    async def _tool_loop(
        self,
        tool_specs: list[dict[str, Any]],
        graph: DeliberationGraph,
    ) -> TurnResult:
        """Run the generate → tool_use → result loop."""
        turn = TurnResult(text="", rounds=0)

        for _round in range(self.max_rounds):
            turn.rounds += 1

            gen = await self.adapter.generate_with_tools(
                self._messages,
                system=self.system_prompt,
                tools=tool_specs or None,
            )
            graph.record_accounting(
                stage="llm_generate",
                route="tool_loop" if gen.tool_calls else "direct_response",
                model=getattr(gen, "model", None),
                cost_usd=float(getattr(gen, "cost_usd", 0.0) or 0.0),
                input_tokens=int(getattr(gen, "input_tokens", 0) or 0),
                output_tokens=int(getattr(gen, "output_tokens", 0) or 0),
                calls=1,
            )
            graph.record_stage(
                "llm_generate",
                f"Completed generation round {turn.rounds}.",
                payload={
                    "tool_calls": len(gen.tool_calls),
                    "stop_reason": getattr(gen, "stop_reason", ""),
                },
            )

            # No tool calls → final text response.
            if not gen.tool_calls:
                turn.text = gen.text
                self._messages.append({"role": "assistant", "content": gen.content_blocks})
                return turn

            # Append assistant message with tool_use blocks.
            self._messages.append({"role": "assistant", "content": gen.content_blocks})

            # Execute each tool call.
            tool_results: list[dict[str, Any]] = []
            for tc in gen.tool_calls:
                record = await self._execute_tool(tc.id, tc.name, tc.input, graph)
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
        graph.record_stage(
            "tool_loop",
            "Tool loop stopped after hitting the configured round cap.",
            status="failed",
            payload={"rounds": turn.rounds},
        )
        graph.stop_reason = "max_rounds"
        return turn

    async def _execute_tool(
        self,
        tool_use_id: str,
        name: str,
        tool_input: dict[str, Any],
        graph: DeliberationGraph,
    ) -> ToolCallRecord:
        """Execute a single tool, checking permissions first."""
        # Record tool_use in session.
        self.session.append_entry(
            Role.ASSISTANT.value,
            f"tool_use: {name}",
            entry_type=EntryType.TOOL_USE.value,
            metadata={"tool_use_id": tool_use_id, "name": name, "input": tool_input},
        )

        # Bind reference lots for resume safety.
        current_op = max(0, len(self.session.transcript) - 1)
        self.session.bind_reference_lot(
            kind="tool",
            subject_key=name,
            op_id=current_op,
            floor={"available": "1"},
            dependents=[current_op],
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
            graph.record_stage(
                "tool_call",
                f"Tool `{name}` denied by permission policy.",
                status="failed",
                payload={"tool_use_id": tool_use_id},
            )
            graph.add_evidence(
                kind="tool_result",
                summary=denial,
                claim_summary=f"Denied tool result from {name}",
                metadata={"tool_name": name, "tool_use_id": tool_use_id, "is_error": True},
            )
            return ToolCallRecord(
                tool_use_id=tool_use_id,
                name=name,
                input=tool_input,
                output=denial,
                is_error=True,
            )

        self.session.bind_reference_lot(
            kind="permission",
            subject_key=name,
            op_id=current_op,
            floor={"allowed": "1"},
            dependents=[current_op],
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
            graph.record_stage(
                "tool_call",
                f"Tool `{name}` has no registered handler.",
                status="failed",
                payload={"tool_use_id": tool_use_id},
            )
            graph.add_evidence(
                kind="tool_result",
                summary=msg,
                claim_summary=f"Missing handler for {name}",
                metadata={"tool_name": name, "tool_use_id": tool_use_id, "is_error": True},
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
            from hephaestus.tools.invocation import ToolContext, ToolInvocation

            context = ToolContext(policy=self.policy)
            if isinstance(tool_def.handler, ToolInvocation):
                output = await tool_def.handler.execute(context, **tool_input)
            else:
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
        graph.record_stage(
            "tool_call",
            f"Executed tool `{name}`.",
            payload={"tool_use_id": tool_use_id, "is_error": is_error},
        )
        graph.add_evidence(
            kind="tool_result",
            summary=output_str[:400],
            claim_summary=f"Tool result from {name}",
            metadata={"tool_name": name, "tool_use_id": tool_use_id, "is_error": is_error},
        )
        graph.record_accounting(
            stage="tool_call",
            route=name,
            calls=1,
        )

        return ToolCallRecord(
            tool_use_id=tool_use_id,
            name=name,
            input=tool_input,
            output=output_str,
            is_error=is_error,
        )
