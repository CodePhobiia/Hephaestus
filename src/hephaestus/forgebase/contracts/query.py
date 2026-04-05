"""Query contracts — stubs for sub-project 5b."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from hephaestus.forgebase.domain.values import EntityId


class QueryScope(StrEnum):
    ALL = "all"
    PAGES = "pages"
    CLAIMS = "claims"
    SOURCES = "sources"


@dataclass
class VaultQuery:
    """Query against a single vault's knowledge graph."""

    vault_id: EntityId
    query_text: str
    scope: QueryScope = QueryScope.ALL
    max_results: int = 20
    filters: dict[str, Any] = field(default_factory=dict)


@dataclass
class QueryResult:
    """Result of a vault query."""

    query_id: EntityId
    vault_id: EntityId
    matches: list[dict[str, Any]] = field(default_factory=list)
    total_count: int = 0
