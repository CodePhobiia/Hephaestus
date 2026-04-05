"""Pydantic request/response models for ForgeBase API endpoints."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Vault models
# ---------------------------------------------------------------------------


class VaultCreateRequest(BaseModel):
    """Request body for creating a new vault."""

    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)


class VaultResponse(BaseModel):
    """Response model for a single vault."""

    vault_id: str
    name: str
    description: str
    health_score: float | None = None
    page_count: int = 0
    claim_count: int = 0
    source_count: int = 0
    finding_count: int = 0
    created_at: str | None = None
    updated_at: str | None = None


class VaultListResponse(BaseModel):
    """Response for listing vaults."""

    vaults: list[VaultResponse]
    count: int


# ---------------------------------------------------------------------------
# Source models
# ---------------------------------------------------------------------------


class SourceIngestRequest(BaseModel):
    """Request body for JSON-based source ingestion."""

    content: str = Field(..., min_length=1, description="Raw text content to ingest")
    format: str = Field(default="markdown", description="Source format (markdown, json, csv, etc.)")
    title: str = Field(default="", max_length=500)
    authors: list[str] = Field(default_factory=list)
    url: str | None = Field(default=None, max_length=2000)
    trust_tier: str = Field(default="standard", description="authoritative, standard, low, untrusted")
    metadata: dict | None = None


class SourceResponse(BaseModel):
    """Response model for a source."""

    source_id: str
    vault_id: str
    format: str
    title: str = ""
    authors: list[str] = []
    url: str | None = None
    status: str = ""
    version: int = 1
    trust_tier: str = "standard"
    created_at: str | None = None


class SourceListResponse(BaseModel):
    """Response for listing sources."""

    sources: list[SourceResponse]
    count: int


# ---------------------------------------------------------------------------
# Compilation models
# ---------------------------------------------------------------------------


class CompileRequest(BaseModel):
    """Request body for triggering compilation."""

    config: dict | None = None


class CompileResponse(BaseModel):
    """Response after scheduling compilation."""

    job_id: str
    status: str


# ---------------------------------------------------------------------------
# Page models
# ---------------------------------------------------------------------------


class PageResponse(BaseModel):
    """Response model for a page."""

    page_id: str
    page_type: str
    page_key: str
    title: str
    version: int
    claim_count: int = 0
    vault_id: str = ""
    created_at: str | None = None


class PageDetailResponse(PageResponse):
    """Full page detail with content and claims."""

    summary: str = ""
    claims: list[ClaimResponse] = []
    links: list[LinkResponse] = []


class PageListResponse(BaseModel):
    """Response for listing pages."""

    pages: list[PageResponse]
    count: int


# ---------------------------------------------------------------------------
# Claim models
# ---------------------------------------------------------------------------


class ClaimResponse(BaseModel):
    """Response model for a claim."""

    claim_id: str
    page_id: str
    statement: str
    status: str
    confidence: float
    support_count: int = 0
    version: int = 1
    support_type: str = ""
    vault_id: str = ""


class ClaimListResponse(BaseModel):
    """Response for listing claims."""

    claims: list[ClaimResponse]
    count: int


# ---------------------------------------------------------------------------
# Link models
# ---------------------------------------------------------------------------


class LinkResponse(BaseModel):
    """Response model for a link."""

    link_id: str
    kind: str
    source_entity: str
    target_entity: str
    label: str | None = None
    weight: float = 1.0
    version: int = 1


# ---------------------------------------------------------------------------
# Linting models
# ---------------------------------------------------------------------------


class LintRequest(BaseModel):
    """Request body for triggering a lint pass."""

    config: dict | None = None


class LintReportResponse(BaseModel):
    """Response model for a lint report."""

    report_id: str
    vault_id: str
    job_id: str
    finding_count: int
    debt_score: float
    findings_by_category: dict[str, int]
    findings_by_severity: dict[str, int]
    created_at: str | None = None


class FindingResponse(BaseModel):
    """Response model for a lint finding."""

    finding_id: str
    job_id: str
    vault_id: str
    category: str
    severity: str
    description: str
    status: str
    suggested_action: str | None = None
    page_id: str | None = None
    claim_id: str | None = None
    confidence: float = 1.0
    remediation_status: str = "open"
    disposition: str = "active"
    remediation_route: str | None = None


class FindingListResponse(BaseModel):
    """Response for listing findings."""

    findings: list[FindingResponse]
    count: int


class FindingTriageRequest(BaseModel):
    """Request body for triaging a finding."""

    remediation_route: str = Field(
        ...,
        description="report_only, research_only, repair_only, research_then_repair",
    )


# ---------------------------------------------------------------------------
# Workbook models
# ---------------------------------------------------------------------------


class WorkbookCreateRequest(BaseModel):
    """Request body for creating a workbook."""

    name: str = Field(..., min_length=1, max_length=200)
    purpose: str = Field(
        default="manual",
        description="research, lint_repair, invention, compilation, manual",
    )


class WorkbookResponse(BaseModel):
    """Response model for a workbook."""

    workbook_id: str
    vault_id: str
    name: str
    purpose: str
    status: str
    base_revision_id: str
    created_at: str | None = None
    created_by: str = ""


class WorkbookListResponse(BaseModel):
    """Response for listing workbooks."""

    workbooks: list[WorkbookResponse]
    count: int


class WorkbookDiffResponse(BaseModel):
    """Response model for workbook diff vs canonical."""

    workbook_id: str
    vault_id: str
    workbook_name: str
    pages_added: int = 0
    pages_modified: int = 0
    pages_deleted: int = 0
    claims_added: int = 0
    claims_modified: int = 0
    claims_deleted: int = 0
    links_added: int = 0
    links_deleted: int = 0


class MergeResponse(BaseModel):
    """Response after a merge operation."""

    merge_id: str
    verdict: str
    resulting_revision: str | None = None


# ---------------------------------------------------------------------------
# Fusion models
# ---------------------------------------------------------------------------


class FusionApiRequest(BaseModel):
    """Request body for triggering fusion."""

    vault_ids: list[str] = Field(..., min_length=2)
    problem: str | None = None
    mode: str = Field(default="strict", description="strict or exploratory")


class FusionRunResponse(BaseModel):
    """Response model for a fusion run."""

    fusion_run_id: str
    vault_ids: list[str]
    problem: str | None = None
    fusion_mode: str
    status: str
    bridge_count: int = 0
    transfer_count: int = 0
    created_at: str | None = None
    completed_at: str | None = None


class FusionRunListResponse(BaseModel):
    """Response for listing fusion runs."""

    runs: list[FusionRunResponse]
    count: int


# ---------------------------------------------------------------------------
# Knowledge graph models
# ---------------------------------------------------------------------------


class GraphNode(BaseModel):
    """A node in the knowledge graph (represents a page)."""

    id: str
    label: str
    page_type: str
    claim_count: int = 0


class GraphEdge(BaseModel):
    """An edge in the knowledge graph (represents a link)."""

    source: str
    target: str
    kind: str
    label: str | None = None
    weight: float = 1.0


class KnowledgeGraphResponse(BaseModel):
    """Knowledge graph response for visualization."""

    vault_id: str
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    node_count: int
    edge_count: int


# Update forward refs for nested models
PageDetailResponse.model_rebuild()
