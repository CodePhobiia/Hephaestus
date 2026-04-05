"""ForgeBase tool definitions for the ConversationRuntime.

Exposes vault operations (create, ingest, compile, lint, fuse)
as ToolDefinition objects that can be registered with the
ToolRegistry for use by the ConversationRuntime.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from hephaestus.forgebase.contracts.agent import AgentRole
from hephaestus.forgebase.domain.enums import SourceFormat
from hephaestus.tools.invocation import ToolContext
from hephaestus.tools.registry import ToolDefinition

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hephaestus.forgebase.factory import ForgeBase
    from hephaestus.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Handler factories — each returns a closure bound to the ForgeBase instance
# ---------------------------------------------------------------------------


def _make_vault_create_handler(forgebase: ForgeBase):
    """Create handler for vault_create tool."""

    async def handler(context: ToolContext, **kwargs: Any) -> str:
        name = kwargs["name"]
        description = kwargs.get("description", "")
        vault = await forgebase.vaults.create_vault(
            name=name, description=description,
        )
        return json.dumps({
            "vault_id": str(vault.vault_id),
            "name": vault.name,
            "description": vault.description,
        })

    return handler


def _make_vault_ingest_handler(forgebase: ForgeBase):
    """Create handler for vault_ingest tool."""

    async def handler(context: ToolContext, **kwargs: Any) -> str:
        vault_id_str = kwargs["vault_id"]
        content = kwargs["content"]
        title = kwargs.get("title", "Untitled")
        fmt = kwargs.get("format", "markdown")

        from hephaestus.forgebase.domain.values import EntityId

        vault_id = EntityId(vault_id_str)

        try:
            source_format = SourceFormat(fmt)
        except ValueError:
            source_format = SourceFormat.MARKDOWN

        source, version = await forgebase.ingest.ingest_source(
            vault_id=vault_id,
            raw_content=content.encode("utf-8"),
            format=source_format,
            title=title,
        )
        return json.dumps({
            "source_id": str(source.source_id),
            "version": version.version.number,
            "title": title,
        })

    return handler


def _make_vault_compile_handler(forgebase: ForgeBase):
    """Create handler for vault_compile tool."""

    async def handler(context: ToolContext, **kwargs: Any) -> str:
        vault_id_str = kwargs["vault_id"]

        from hephaestus.forgebase.domain.values import EntityId

        vault_id = EntityId(vault_id_str)

        manifest = await forgebase.vault_synthesizer.synthesize(
            vault_id=vault_id,
        )
        return json.dumps({
            "manifest_id": str(manifest.manifest_id),
            "candidates_resolved": manifest.candidates_resolved,
        })

    return handler


def _make_vault_lint_handler(forgebase: ForgeBase):
    """Create handler for vault_lint tool."""

    async def handler(context: ToolContext, **kwargs: Any) -> str:
        vault_id_str = kwargs["vault_id"]

        from hephaestus.forgebase.domain.values import EntityId

        vault_id = EntityId(vault_id_str)

        report = await forgebase.lint_engine.run_lint(vault_id=vault_id)
        return json.dumps({
            "report_id": str(report.report_id),
            "finding_count": report.finding_count,
            "debt_score": report.debt_score,
            "findings_by_category": report.findings_by_category,
            "findings_by_severity": report.findings_by_severity,
        })

    return handler


def _make_vault_fuse_handler(forgebase: ForgeBase):
    """Create handler for vault_fuse tool."""

    async def handler(context: ToolContext, **kwargs: Any) -> str:
        source_vault_str = kwargs["source_vault_id"]
        target_vault_str = kwargs["target_vault_id"]

        from hephaestus.forgebase.domain.values import EntityId

        source_vault = EntityId(source_vault_str)
        target_vault = EntityId(target_vault_str)

        if forgebase.fusion is None:
            return json.dumps({"error": "Fusion not configured"})

        result = await forgebase.fusion.run_fusion(
            source_vault_id=source_vault,
            target_vault_id=target_vault,
        )
        return json.dumps({
            "fusion_id": str(result.fusion_id),
            "packs_created": result.packs_created,
        })

    return handler


def _make_vault_team_handler(forgebase: ForgeBase):
    """Create handler for vault_team tool."""

    async def handler(context: ToolContext, **kwargs: Any) -> str:
        vault_id_str = kwargs["vault_id"]
        run_type = kwargs.get("run_type", "maintenance")
        query = kwargs.get("query", "")
        roles_raw = kwargs.get("roles", [])

        from hephaestus.forgebase.agents.team import KnowledgeTeam
        from hephaestus.forgebase.domain.values import ActorRef, EntityId

        vault_id = EntityId(vault_id_str)
        actor = ActorRef.system()
        team = KnowledgeTeam(forgebase, actor)

        if run_type == "maintenance":
            run = await team.run_maintenance(vault_id)
        elif run_type == "research":
            run = await team.run_research(vault_id, query or "General research")
        elif run_type == "quality":
            run = await team.run_quality(vault_id)
        elif run_type == "custom" and roles_raw:
            roles = [AgentRole(r) for r in roles_raw]
            run = await team.run_custom(vault_id, roles, query or "Custom run")
        else:
            return json.dumps({"error": f"Unknown run_type: {run_type}"})

        return json.dumps({
            "run_id": str(run.run_id),
            "status": run.status.value,
            "tasks": [
                {
                    "task_id": str(t.task_id),
                    "role": t.role.value,
                    "status": t.status.value,
                    "artifacts": [str(a) for a in t.artifacts_created],
                }
                for t in run.tasks
            ],
        })

    return handler


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------


def build_forgebase_tools(forgebase: ForgeBase) -> list[ToolDefinition]:
    """Build ForgeBase tool definitions bound to a ForgeBase instance.

    Returns a list of ToolDefinition objects ready for registration
    with a ToolRegistry.
    """
    return [
        ToolDefinition(
            name="vault_create",
            description="Create a new knowledge vault.",
            category="write",
            input_schema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Name for the new vault.",
                    },
                    "description": {
                        "type": "string",
                        "description": "Optional description of the vault.",
                        "default": "",
                    },
                },
                "required": ["name"],
            },
            handler=_make_vault_create_handler(forgebase),
        ),
        ToolDefinition(
            name="vault_ingest",
            description="Ingest source content into a vault.",
            category="write",
            input_schema={
                "type": "object",
                "properties": {
                    "vault_id": {
                        "type": "string",
                        "description": "ID of the vault to ingest into.",
                    },
                    "content": {
                        "type": "string",
                        "description": "Raw text content to ingest.",
                    },
                    "title": {
                        "type": "string",
                        "description": "Title for the source.",
                        "default": "Untitled",
                    },
                    "format": {
                        "type": "string",
                        "description": "Source format (markdown, pdf, url, etc.).",
                        "default": "markdown",
                    },
                },
                "required": ["vault_id", "content"],
            },
            handler=_make_vault_ingest_handler(forgebase),
        ),
        ToolDefinition(
            name="vault_compile",
            description="Run vault-wide compilation (Tier 2 synthesis).",
            category="write",
            input_schema={
                "type": "object",
                "properties": {
                    "vault_id": {
                        "type": "string",
                        "description": "ID of the vault to compile.",
                    },
                },
                "required": ["vault_id"],
            },
            handler=_make_vault_compile_handler(forgebase),
        ),
        ToolDefinition(
            name="vault_lint",
            description="Run lint detectors on a vault and return findings.",
            category="read",
            input_schema={
                "type": "object",
                "properties": {
                    "vault_id": {
                        "type": "string",
                        "description": "ID of the vault to lint.",
                    },
                },
                "required": ["vault_id"],
            },
            handler=_make_vault_lint_handler(forgebase),
        ),
        ToolDefinition(
            name="vault_fuse",
            description="Fuse knowledge from one vault into another.",
            category="write",
            input_schema={
                "type": "object",
                "properties": {
                    "source_vault_id": {
                        "type": "string",
                        "description": "ID of the source vault.",
                    },
                    "target_vault_id": {
                        "type": "string",
                        "description": "ID of the target vault.",
                    },
                },
                "required": ["source_vault_id", "target_vault_id"],
            },
            handler=_make_vault_fuse_handler(forgebase),
        ),
        ToolDefinition(
            name="vault_team",
            description=(
                "Run a knowledge agent team on a vault. "
                "Run types: maintenance, research, quality, custom."
            ),
            category="write",
            input_schema={
                "type": "object",
                "properties": {
                    "vault_id": {
                        "type": "string",
                        "description": "ID of the vault.",
                    },
                    "run_type": {
                        "type": "string",
                        "description": "Type of run: maintenance, research, quality, custom.",
                        "default": "maintenance",
                        "enum": ["maintenance", "research", "quality", "custom"],
                    },
                    "query": {
                        "type": "string",
                        "description": "Research query (for research/custom runs).",
                        "default": "",
                    },
                    "roles": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Agent roles for custom runs.",
                        "default": [],
                    },
                },
                "required": ["vault_id"],
            },
            handler=_make_vault_team_handler(forgebase),
        ),
    ]


def register_forgebase_tools(
    registry: ToolRegistry,
    forgebase: ForgeBase,
) -> None:
    """Register all ForgeBase tools with the given ToolRegistry."""
    for tool in build_forgebase_tools(forgebase):
        registry.register(tool)
