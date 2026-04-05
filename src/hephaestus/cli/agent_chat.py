"""
Agentic chat mode for Hephaestus.

This module provides a tool-using chat session around the current invention.
The model can research, read and write notes, compare inventions, export
deliverables, and run safe arithmetic without leaving the REPL.
"""

from __future__ import annotations

import ast
import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
from rich.console import Console

from hephaestus.cli.config import HEPHAESTUS_DIR, INVENTIONS_DIR, ensure_dirs
from hephaestus.deepforge.adapters.claude_max import ClaudeMaxAdapter
from hephaestus.output.formatter import OutputFormatter

if TYPE_CHECKING:
    from hephaestus.cli.repl import SessionState

logger = logging.getLogger(__name__)


MAX_FILE_CHARS = 20_000
MAX_TOOL_ROUNDS = 8


@dataclass
class ToolExecutionResult:
    """Normalised tool execution payload returned to the model."""

    content: str
    summary: str
    is_error: bool = False


class _ArithmeticEvaluator:
    """Safe arithmetic evaluator for numeric expressions only."""

    _BIN_OPS = {
        ast.Add: lambda a, b: a + b,
        ast.Sub: lambda a, b: a - b,
        ast.Mult: lambda a, b: a * b,
        ast.Div: lambda a, b: a / b,
        ast.FloorDiv: lambda a, b: a // b,
        ast.Mod: lambda a, b: a % b,
        ast.Pow: lambda a, b: a**b,
    }
    _UNARY_OPS = {
        ast.UAdd: lambda a: +a,
        ast.USub: lambda a: -a,
    }

    def evaluate(self, expression: str) -> int | float:
        tree = ast.parse(expression, mode="eval")
        value = self._eval_node(tree.body)
        if isinstance(value, complex):
            raise ValueError("complex numbers are not supported")
        if isinstance(value, (int, float)) and abs(value) > 1e100:
            raise ValueError("result magnitude is too large")
        return value

    def _eval_node(self, node: ast.AST) -> int | float:
        if isinstance(node, ast.Constant):
            value = node.value
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError("only integers and floats are supported")
            return value

        if isinstance(node, ast.BinOp):
            op = self._BIN_OPS.get(type(node.op))
            if op is None:
                raise ValueError("unsupported operator")
            left = self._eval_node(node.left)
            right = self._eval_node(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 12:
                raise ValueError("exponent is too large")
            return op(left, right)

        if isinstance(node, ast.UnaryOp):
            op = self._UNARY_OPS.get(type(node.op))
            if op is None:
                raise ValueError("unsupported unary operator")
            return op(self._eval_node(node.operand))

        raise ValueError("unsupported expression")


class AgentChat:
    """Interactive agentic chat session around the current invention."""

    def __init__(self, console: Console, state: SessionState) -> None:
        self.console = console
        self.state = state
        self.messages: list[dict[str, Any]] = []
        self._system_prompt = ""
        self._tool_handlers = {
            "web_search": self._tool_web_search,
            "save_note": self._tool_save_note,
            "read_file": self._tool_read_file,
            "compare_inventions": self._tool_compare_inventions,
            "export": self._tool_export,
            "calculate": self._tool_calculate,
        }

    async def run(self) -> None:
        """Start the interactive agent loop."""
        report = self.state.current_report
        if not report or not getattr(report, "top_invention", None):
            self.console.print("  [dim]No current invention to discuss.[/]\n")
            return
        self._system_prompt = self._build_system_prompt()

        try:
            adapter = ClaudeMaxAdapter(model=self.state.config.default_model)
        except Exception as exc:
            self.console.print(f"  [red]Agent chat unavailable:[/] {self._clean_error(exc)}\n")
            return

        top = report.top_invention
        self.console.print()
        self.console.print(
            f"  [yellow]Agent mode[/] — tool-enabled chat for [dark_orange]{top.invention_name}[/]"
        )
        self.console.print(
            "  [dim]Type /back to return to the menu. Tools run automatically when useful.[/]"
        )
        self.console.print()

        while True:
            try:
                user_input = self.console.input("  [yellow]you>[/] ").strip()
            except (EOFError, KeyboardInterrupt):
                self.console.print("\n  [dim]Back to menu.[/]\n")
                return

            if not user_input:
                continue
            if user_input.lower() in {"/back", "/exit", "/quit", "/menu"}:
                self.console.print("  [dim]Back to menu.[/]\n")
                return

            checkpoint = len(self.messages)
            self.messages.append({"role": "user", "content": user_input})

            try:
                await self._run_turn(adapter)
            except Exception as exc:
                self.messages = self.messages[:checkpoint]
                self.console.print(f"  [red]Agent error:[/] {self._clean_error(exc)}\n")

    async def _run_turn(self, adapter: ClaudeMaxAdapter) -> None:
        """Handle one user turn, including any tool loops."""
        for _ in range(MAX_TOOL_ROUNDS):
            result = await adapter.generate_with_tools(
                messages=self.messages,
                system=self._system_prompt,
                tools=self._tool_specs(),
                max_tokens=4096,
                temperature=0.7,
            )

            if result.tool_calls:
                self.messages.append({"role": "assistant", "content": result.content_blocks})

                preamble = result.text.strip()
                if preamble:
                    for line in preamble.splitlines():
                        self.console.print(f"  [dim]{line}[/]")

                tool_results: list[dict[str, Any]] = []
                for tool_call in result.tool_calls:
                    tool_result = await self._execute_tool(tool_call.name, tool_call.input)
                    style = "yellow" if tool_result.is_error else "dark_orange"
                    self.console.print(
                        f"  [{style}]tool[{tool_call.name}][/] {tool_result.summary}"
                    )
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_call.id,
                            "content": tool_result.content,
                            "is_error": tool_result.is_error,
                        }
                    )

                self.messages.append({"role": "user", "content": tool_results})
                continue

            self.messages.append({"role": "assistant", "content": result.content_blocks})
            reply = result.text.strip() or "No response returned."
            self.console.print("  [dark_orange]heph>[/] ", end="")
            self.console.print(reply)
            self.console.print()
            return

        raise RuntimeError("tool loop limit reached")

    def _build_system_prompt(self) -> str:
        """Construct the agent system prompt with full invention context."""
        report = self.state.current_report
        top = report.top_invention
        formatter = OutputFormatter()

        from hephaestus.cli.main import _bridge_report

        invention_markdown = formatter.to_markdown(_bridge_report(report))
        context_items = "\n".join(f"- {item}" for item in self.state.context_items) or "- None"

        return (
            "You are Hephaestus in agent mode. You are discussing the current invention and "
            "you have tools available.\n\n"
            "Use tools proactively when they will improve the answer.\n"
            "- If the user asks about feasibility, prior art, standards, or competitors, use web_search.\n"
            "- If the user wants something remembered, use save_note.\n"
            "- If the user asks for saved material, use read_file.\n"
            "- If the user asks for a side-by-side analysis, use compare_inventions.\n"
            "- If the user asks for a deliverable, use export.\n"
            "- If the user asks for math or thresholds, use calculate.\n\n"
            "Do not ask permission before using tools. Use them, then explain what you found or did. "
            "Be direct, technical, and concise. If a tool fails, say so briefly and recover.\n\n"
            f"CURRENT INVENTION: {top.invention_name}\n"
            f"SOURCE DOMAIN: {top.source_domain}\n"
            f"NOVELTY SCORE: {top.novelty_score:.2f}\n\n"
            "SESSION CONTEXT ITEMS:\n"
            f"{context_items}\n\n"
            "FULL INVENTION CONTEXT:\n"
            f"{invention_markdown}"
        )

    async def _execute_tool(self, name: str, raw_input: dict[str, Any]) -> ToolExecutionResult:
        """Dispatch a tool call safely."""
        handler = self._tool_handlers.get(name)
        if handler is None:
            return ToolExecutionResult(
                content=self._json_payload({"error": f"Unknown tool: {name}"}),
                summary="failed: unknown tool",
                is_error=True,
            )

        try:
            safe_input = dict(raw_input or {})
            return await handler(safe_input)
        except Exception as exc:
            return ToolExecutionResult(
                content=self._json_payload({"error": self._clean_error(exc)}),
                summary=f"failed: {self._clean_error(exc)}",
                is_error=True,
            )

    async def _tool_web_search(self, tool_input: dict[str, Any]) -> ToolExecutionResult:
        query = str(tool_input.get("query", "")).strip()
        if not query:
            raise ValueError("query is required")

        api_key = os.environ.get("PERPLEXITY_API_KEY")
        if not api_key:
            raise ValueError("PERPLEXITY_API_KEY is not set")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.perplexity.ai/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "sonar",
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are a technical research assistant. Search for prior art, "
                                "feasibility signals, specifications, or related work. Respond "
                                "with concise findings grounded in cited sources."
                            ),
                        },
                        {"role": "user", "content": query},
                    ],
                },
            )

        if response.status_code != 200:
            detail = response.text[:400].strip() or f"status {response.status_code}"
            raise ValueError(f"Perplexity request failed: {detail}")

        data = response.json()
        message = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        citations = [
            {"url": url} for url in data.get("citations", [])[:8] if isinstance(url, str) and url
        ]
        payload = {
            "query": query,
            "summary": message,
            "citations": citations,
        }
        return ToolExecutionResult(
            content=self._json_payload(payload),
            summary=f"completed with {len(citations)} citation(s)",
        )

    async def _tool_save_note(self, tool_input: dict[str, Any]) -> ToolExecutionResult:
        note = str(tool_input.get("note", "")).strip()
        if not note:
            raise ValueError("note is required")

        ensure_dirs()
        notes_dir = HEPHAESTUS_DIR / "notes"
        notes_dir.mkdir(parents=True, exist_ok=True)

        report = self.state.current_report
        top = report.top_invention
        slug = self._sanitize_slug(getattr(self.state.current, "slug", "") or top.invention_name)
        path = notes_dir / f"{slug}.md"

        timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        if path.exists():
            block = f"\n## {timestamp}\n\n{note}\n"
        else:
            block = f"# Notes for {top.invention_name}\n\n## {timestamp}\n\n{note}\n"

        with path.open("a", encoding="utf-8") as handle:
            handle.write(block)

        payload = {
            "path": str(path),
            "saved_at": timestamp,
            "chars_written": len(block),
        }
        return ToolExecutionResult(
            content=self._json_payload(payload),
            summary=f"appended note to {path.name}",
        )

    async def _tool_read_file(self, tool_input: dict[str, Any]) -> ToolExecutionResult:
        raw_path = str(tool_input.get("path", "")).strip()
        if not raw_path:
            raise ValueError("path is required")

        path = self._resolve_hephaestus_path(raw_path)
        if not path.exists():
            raise ValueError(f"{path} does not exist")

        if path.is_dir():
            entries = []
            for child in sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))[:100]:
                entries.append(
                    {
                        "name": child.name,
                        "type": "directory" if child.is_dir() else "file",
                    }
                )
            payload = {
                "path": str(path),
                "type": "directory",
                "entries": entries,
            }
            return ToolExecutionResult(
                content=self._json_payload(payload),
                summary=f"listed {len(entries)} item(s) in {path.name or str(path)}",
            )

        text = path.read_text(encoding="utf-8", errors="replace")
        truncated = len(text) > MAX_FILE_CHARS
        if truncated:
            text = text[:MAX_FILE_CHARS]
        payload = {
            "path": str(path),
            "type": "file",
            "truncated": truncated,
            "content": text,
        }
        return ToolExecutionResult(
            content=self._json_payload(payload),
            summary=f"read {path.name}",
        )

    async def _tool_compare_inventions(self, tool_input: dict[str, Any]) -> ToolExecutionResult:
        current_summary = self._summarize_current_invention()
        other_query = str(tool_input.get("other", "")).strip()
        other_summary, source = self._resolve_other_invention(other_query)
        if other_summary is None:
            raise ValueError("no comparison target found")

        novelty_delta = None
        if isinstance(current_summary.get("novelty_score"), (int, float)) and isinstance(
            other_summary.get("novelty_score"), (int, float)
        ):
            novelty_delta = round(
                float(current_summary["novelty_score"]) - float(other_summary["novelty_score"]),
                4,
            )

        payload = {
            "current": current_summary,
            "other": other_summary,
            "source": source,
            "differences": {
                "source_domain_same": current_summary.get("source_domain")
                == other_summary.get("source_domain"),
                "verdict_same": current_summary.get("verdict") == other_summary.get("verdict"),
                "novelty_delta": novelty_delta,
            },
        }
        return ToolExecutionResult(
            content=self._json_payload(payload),
            summary=f"compared against {other_summary.get('name', 'other invention')}",
        )

    async def _tool_export(self, tool_input: dict[str, Any]) -> ToolExecutionResult:
        fmt_input = str(tool_input.get("format", "markdown")).strip().lower() or "markdown"
        filename = str(tool_input.get("filename", "")).strip()
        ext = self._normalise_export_format(fmt_input)

        ensure_dirs()
        date_str = datetime.now(UTC).strftime("%Y-%m-%d")
        default_stem = f"{date_str}-{self._sanitize_slug(self.state.current.slug)}"
        stem = self._sanitize_slug(filename) if filename else default_stem

        formatter = OutputFormatter()
        from hephaestus.cli.main import _bridge_report

        fmt_report = _bridge_report(self.state.current_report)
        actual_format = ext
        fallback = None

        if ext == "json":
            content = formatter.to_json(fmt_report)
            path = self._unique_path(INVENTIONS_DIR, stem, ".json")
            path.write_text(content, encoding="utf-8")
        elif ext == "txt":
            content = formatter.to_plain(fmt_report)
            path = self._unique_path(INVENTIONS_DIR, stem, ".txt")
            path.write_text(content, encoding="utf-8")
        elif ext == "pdf":
            markdown = formatter.to_markdown(fmt_report)
            path = self._unique_path(INVENTIONS_DIR, stem, ".pdf")
            try:
                from weasyprint import HTML

                html = self._markdown_to_simple_html(markdown)
                document = (
                    "<html><head><style>"
                    "body{font-family:sans-serif;max-width:700px;margin:auto;padding:40px;}"
                    "h1{color:#b8860b;}h2{color:#666;}h3{color:#888;}"
                    "pre{background:#f5f5f5;padding:12px;border-radius:4px;}"
                    "code{background:#f0f0f0;padding:2px 4px;}"
                    "li{margin:4px 0;}"
                    "</style></head><body>"
                    f"{html}</body></html>"
                )
                HTML(string=document).write_pdf(str(path))
            except ImportError:
                actual_format = "md"
                fallback = "weasyprint not installed; exported markdown instead"
                path = self._unique_path(INVENTIONS_DIR, stem, ".md")
                path.write_text(markdown, encoding="utf-8")
        else:
            content = formatter.to_markdown(fmt_report)
            path = self._unique_path(INVENTIONS_DIR, stem, ".md")
            path.write_text(content, encoding="utf-8")

        payload = {
            "path": str(path),
            "requested_format": fmt_input,
            "actual_format": actual_format,
            "fallback": fallback,
        }
        return ToolExecutionResult(
            content=self._json_payload(payload),
            summary=f"exported {path.name}",
        )

    async def _tool_calculate(self, tool_input: dict[str, Any]) -> ToolExecutionResult:
        expression = str(tool_input.get("expression", "")).strip()
        if not expression:
            raise ValueError("expression is required")

        evaluator = _ArithmeticEvaluator()
        result = evaluator.evaluate(expression)
        payload = {
            "expression": expression,
            "result": result,
        }
        return ToolExecutionResult(
            content=self._json_payload(payload),
            summary=f"evaluated to {result}",
        )

    def _resolve_other_invention(self, query: str) -> tuple[dict[str, Any] | None, str]:
        """Find another invention from the session or saved disk exports."""
        if not query or query.lower() == "previous":
            for idx in range(len(self.state.inventions) - 1, -1, -1):
                if idx != self.state.current_idx:
                    return self._summarize_report(self.state.inventions[idx].report), "session"
            return None, "session"

        normalized = query.lower()
        for idx, entry in enumerate(reversed(self.state.inventions)):
            real_idx = len(self.state.inventions) - idx - 1
            if real_idx == self.state.current_idx:
                continue
            summary = self._summarize_report(entry.report)
            haystacks = [
                str(summary.get("name", "")).lower(),
                str(summary.get("problem", "")).lower(),
                str(entry.slug).lower(),
            ]
            if any(normalized in haystack for haystack in haystacks):
                return summary, "session"

        saved = self._find_saved_invention(query)
        if saved is not None:
            return self._summarize_saved_invention(saved), "disk"
        return None, ""

    def _find_saved_invention(self, query: str) -> dict[str, Any] | None:
        """Find a saved invention JSON by partial filename match."""
        sanitized = re.sub(r"[/\\\\*?\\[\\]{}]", "", query).strip().lower()
        if not sanitized or not INVENTIONS_DIR.exists():
            return None

        exact = INVENTIONS_DIR / sanitized
        if exact.exists() and exact.suffix == ".json":
            return json.loads(exact.read_text(encoding="utf-8"))

        candidate = INVENTIONS_DIR / f"{sanitized}.json"
        if candidate.exists():
            return json.loads(candidate.read_text(encoding="utf-8"))

        matches = sorted(INVENTIONS_DIR.glob(f"*{sanitized}*.json"), reverse=True)
        for match in matches:
            try:
                data = json.loads(match.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Skipping unreadable invention file %s: %s", match.name, exc)
                continue
            if isinstance(data, dict) and "top_invention" in data:
                return data
        return None

    def _summarize_current_invention(self) -> dict[str, Any]:
        return self._summarize_report(self.state.current_report)

    def _summarize_report(self, report: Any) -> dict[str, Any]:
        """Extract a compact comparison summary from a live report object."""
        top = getattr(report, "top_invention", None)
        translation = getattr(top, "translation", None)
        return {
            "problem": getattr(report, "problem", ""),
            "name": getattr(top, "invention_name", "Unknown invention"),
            "source_domain": getattr(top, "source_domain", "N/A"),
            "novelty_score": getattr(top, "novelty_score", None),
            "feasibility": getattr(top, "feasibility_rating", None),
            "verdict": getattr(top, "verdict", None),
            "key_insight": getattr(translation, "key_insight", None),
            "architecture": self._truncate_text(getattr(translation, "architecture", "")),
        }

    def _summarize_saved_invention(self, data: dict[str, Any]) -> dict[str, Any]:
        """Extract a compact comparison summary from a saved invention JSON blob."""
        top = data.get("top_invention") or {}
        meta = data.get("_meta") or {}
        return {
            "problem": meta.get("problem", data.get("problem", "")),
            "name": top.get("name", "Unknown invention"),
            "source_domain": top.get("source_domain", "N/A"),
            "novelty_score": top.get("novelty_score"),
            "feasibility": top.get("feasibility"),
            "verdict": top.get("verdict"),
            "key_insight": top.get("key_insight"),
            "architecture": self._truncate_text(top.get("architecture", "")),
        }

    def _resolve_hephaestus_path(self, raw_path: str) -> Path:
        """Resolve a path and ensure it remains under ~/.hephaestus."""
        base = HEPHAESTUS_DIR.resolve()
        expanded = Path(raw_path).expanduser()
        candidate = expanded if expanded.is_absolute() else base / expanded
        resolved = candidate.resolve(strict=False)
        if resolved != base and not resolved.is_relative_to(base):
            raise ValueError("path must stay inside ~/.hephaestus")
        return resolved

    @staticmethod
    def _normalise_export_format(fmt: str) -> str:
        mapping = {
            "markdown": "md",
            "md": "md",
            "json": "json",
            "text": "txt",
            "txt": "txt",
            "plain": "txt",
            "pdf": "pdf",
        }
        normalized = mapping.get(fmt)
        if normalized is None:
            raise ValueError("format must be one of: markdown, json, text, pdf")
        return normalized

    @staticmethod
    def _sanitize_slug(value: str) -> str:
        slug = re.sub(r"[^a-z0-9_-]+", "-", value.lower()).strip("-")
        return slug[:80] or "invention"

    @staticmethod
    def _truncate_text(value: Any, limit: int = 600) -> str:
        text = "" if value is None else str(value)
        if len(text) <= limit:
            return text
        return text[:limit] + "..."

    @staticmethod
    def _clean_error(exc: Exception) -> str:
        text = str(exc).strip()
        if not text:
            return exc.__class__.__name__
        return text.replace("\n", " ")

    @staticmethod
    def _json_payload(payload: dict[str, Any]) -> str:
        return json.dumps(payload, indent=2, ensure_ascii=True)

    @staticmethod
    def _unique_path(directory: Path, stem: str, suffix: str) -> Path:
        path = directory / f"{stem}{suffix}"
        counter = 1
        while path.exists():
            path = directory / f"{stem}-{counter}{suffix}"
            counter += 1
        return path

    @staticmethod
    def _markdown_to_simple_html(markdown: str) -> str:
        import html as html_mod

        lines = markdown.split("\n")
        html_lines: list[str] = []
        in_code = False

        for line in lines:
            if line.startswith("```"):
                html_lines.append("</pre>" if in_code else "<pre>")
                in_code = not in_code
                continue
            if in_code:
                html_lines.append(html_mod.escape(line))
                continue
            if line.startswith("### "):
                html_lines.append(f"<h3>{html_mod.escape(line[4:])}</h3>")
            elif line.startswith("## "):
                html_lines.append(f"<h2>{html_mod.escape(line[3:])}</h2>")
            elif line.startswith("# "):
                html_lines.append(f"<h1>{html_mod.escape(line[2:])}</h1>")
            elif line.startswith("- "):
                html_lines.append(f"<li>{html_mod.escape(line[2:])}</li>")
            elif line.strip():
                html_lines.append(f"<p>{html_mod.escape(line)}</p>")

        if in_code:
            html_lines.append("</pre>")
        return "\n".join(html_lines)

    @staticmethod
    def _tool_specs() -> list[dict[str, Any]]:
        """Anthropic-native tool registry."""
        return [
            {
                "name": "web_search",
                "description": "Search the web for prior art, feasibility data, papers, standards, or related systems using Perplexity.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Research query to send to Perplexity",
                        }
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "save_note",
                "description": "Append an invention note to ~/.hephaestus/notes/<invention-slug>.md.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "note": {
                            "type": "string",
                            "description": "Insight, decision, or reminder to persist",
                        }
                    },
                    "required": ["note"],
                },
            },
            {
                "name": "read_file",
                "description": "Read a file or list a directory under ~/.hephaestus only.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path relative to ~/.hephaestus or an absolute path inside it",
                        }
                    },
                    "required": ["path"],
                },
            },
            {
                "name": "compare_inventions",
                "description": "Compare the current invention with another session or saved invention.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "other": {
                            "type": "string",
                            "description": "Saved invention name, filename, session invention hint, or 'previous'",
                        }
                    },
                },
            },
            {
                "name": "export",
                "description": "Export the current invention to ~/.hephaestus/inventions as markdown, json, text, or pdf.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "format": {
                            "type": "string",
                            "enum": ["markdown", "json", "text", "pdf", "md", "txt", "plain"],
                            "description": "Desired export format",
                        },
                        "filename": {
                            "type": "string",
                            "description": "Optional base filename without directories",
                        },
                    },
                },
            },
            {
                "name": "calculate",
                "description": "Evaluate a safe arithmetic expression with numbers and operators only.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "expression": {
                            "type": "string",
                            "description": "Arithmetic expression using numbers, parentheses, and operators",
                        }
                    },
                    "required": ["expression"],
                },
            },
        ]
