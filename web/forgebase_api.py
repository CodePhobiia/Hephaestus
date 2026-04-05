"""ForgeBase API router — REST endpoints for the ForgeBase knowledge foundry.

Mounted at ``/api/forgebase/`` on the main FastAPI app.
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse

from web.forgebase_deps import get_forgebase
from web.forgebase_models import (
    ClaimListResponse,
    ClaimResponse,
    CompileRequest,
    CompileResponse,
    FindingListResponse,
    FindingResponse,
    FindingTriageRequest,
    FusionApiRequest,
    FusionRunListResponse,
    FusionRunResponse,
    GraphEdge,
    GraphNode,
    KnowledgeGraphResponse,
    LintReportResponse,
    LintRequest,
    LinkResponse,
    MergeResponse,
    PageDetailResponse,
    PageListResponse,
    PageResponse,
    SourceIngestRequest,
    SourceListResponse,
    SourceResponse,
    VaultCreateRequest,
    VaultListResponse,
    VaultResponse,
    WorkbookCreateRequest,
    WorkbookDiffResponse,
    WorkbookListResponse,
    WorkbookResponse,
)

logger = logging.getLogger(__name__)

forgebase_router = APIRouter(prefix="/api/forgebase", tags=["forgebase"])


# ---------------------------------------------------------------------------
# SSE helpers (mirror web/app.py patterns)
# ---------------------------------------------------------------------------


def _sse_event(event_type: str, data: Any) -> str:
    payload = json.dumps(data, default=str)
    return f"event: {event_type}\ndata: {payload}\n\n"


def _sse_error(message: str) -> str:
    return _sse_event("error", {"message": message})


# ---------------------------------------------------------------------------
# Auth check helper (reuse the same pattern as app.py)
# ---------------------------------------------------------------------------

import os
import time

_HEPH_API_KEY = os.environ.get("HEPH_API_KEY", "")


def _check_auth(request: Request) -> bool:
    if not _HEPH_API_KEY:
        return True
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:].strip() == _HEPH_API_KEY
    return False


def _require_auth(request: Request) -> None:
    if not _check_auth(request):
        raise HTTPException(status_code=401, detail="Unauthorized")


# ===========================================================================
# 1. Vault Management
# ===========================================================================


@forgebase_router.post("/vaults", response_model=VaultResponse, status_code=201)
async def create_vault(
    body: VaultCreateRequest,
    request: Request,
    fb=Depends(get_forgebase),
):
    """Create a new vault."""
    _require_auth(request)
    try:
        vault = await fb.vaults.create_vault(
            name=body.name,
            description=body.description,
        )
        return VaultResponse(
            vault_id=str(vault.vault_id),
            name=vault.name,
            description=vault.description,
            created_at=str(vault.created_at),
            updated_at=str(vault.updated_at),
        )
    except Exception as exc:
        logger.exception("Failed to create vault")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@forgebase_router.get("/vaults", response_model=VaultListResponse)
async def list_vaults(
    request: Request,
    fb=Depends(get_forgebase),
):
    """List all vaults with stats."""
    _require_auth(request)
    try:
        uow = fb.uow_factory()
        async with uow:
            vaults = await uow.vaults.list_all()
            results = []
            for v in vaults:
                pages = await uow.pages.list_by_vault(v.vault_id)
                claims = await uow.claims.list_by_vault(v.vault_id)
                sources = await uow.sources.list_by_vault(v.vault_id)
                findings = await uow.findings.list_by_vault(v.vault_id)
                reports = await uow.lint_reports.list_by_vault(v.vault_id)
                health = reports[-1].debt_score if reports else None
                results.append(VaultResponse(
                    vault_id=str(v.vault_id),
                    name=v.name,
                    description=v.description,
                    health_score=health,
                    page_count=len(pages),
                    claim_count=len(claims),
                    source_count=len(sources),
                    finding_count=len(findings),
                    created_at=str(v.created_at),
                    updated_at=str(v.updated_at),
                ))
            await uow.rollback()  # read-only
        return VaultListResponse(vaults=results, count=len(results))
    except Exception as exc:
        logger.exception("Failed to list vaults")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@forgebase_router.get("/vaults/{vault_id}", response_model=VaultResponse)
async def get_vault(
    vault_id: str,
    request: Request,
    fb=Depends(get_forgebase),
):
    """Get vault detail with summary stats."""
    _require_auth(request)
    try:
        from hephaestus.forgebase.domain.values import EntityId

        vid = EntityId(vault_id)
        uow = fb.uow_factory()
        async with uow:
            vault = await uow.vaults.get(vid)
            if vault is None:
                raise HTTPException(status_code=404, detail=f"Vault {vault_id} not found")
            pages = await uow.pages.list_by_vault(vid)
            claims = await uow.claims.list_by_vault(vid)
            sources = await uow.sources.list_by_vault(vid)
            findings = await uow.findings.list_by_vault(vid)
            reports = await uow.lint_reports.list_by_vault(vid)
            health = reports[-1].debt_score if reports else None
            await uow.rollback()

        return VaultResponse(
            vault_id=str(vault.vault_id),
            name=vault.name,
            description=vault.description,
            health_score=health,
            page_count=len(pages),
            claim_count=len(claims),
            source_count=len(sources),
            finding_count=len(findings),
            created_at=str(vault.created_at),
            updated_at=str(vault.updated_at),
        )
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to get vault")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@forgebase_router.delete("/vaults/{vault_id}", status_code=204)
async def archive_vault(
    vault_id: str,
    request: Request,
    fb=Depends(get_forgebase),
):
    """Archive a vault (soft delete by updating config)."""
    _require_auth(request)
    try:
        from hephaestus.forgebase.domain.values import EntityId

        vid = EntityId(vault_id)
        uow = fb.uow_factory()
        async with uow:
            vault = await uow.vaults.get(vid)
            if vault is None:
                raise HTTPException(status_code=404, detail=f"Vault {vault_id} not found")
            await uow.rollback()

        await fb.vaults.update_vault_config(vid, {"archived": True})
        return None
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to archive vault")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ===========================================================================
# 2. Source Ingestion
# ===========================================================================


@forgebase_router.post(
    "/vaults/{vault_id}/sources",
    response_model=SourceResponse,
    status_code=201,
)
async def ingest_source(
    vault_id: str,
    body: SourceIngestRequest,
    request: Request,
    fb=Depends(get_forgebase),
):
    """Ingest a source into a vault."""
    _require_auth(request)
    try:
        from hephaestus.forgebase.domain.enums import SourceFormat, SourceTrustTier
        from hephaestus.forgebase.domain.values import EntityId

        vid = EntityId(vault_id)

        # Parse format enum
        try:
            src_format = SourceFormat(body.format)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid source format: {body.format}. "
                f"Valid: {[f.value for f in SourceFormat]}",
            )

        # Parse trust tier
        try:
            trust = SourceTrustTier(body.trust_tier)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid trust tier: {body.trust_tier}. "
                f"Valid: {[t.value for t in SourceTrustTier]}",
            )

        source, version = await fb.ingest.ingest_source(
            vault_id=vid,
            raw_content=body.content.encode("utf-8"),
            format=src_format,
            title=body.title,
            authors=body.authors,
            url=body.url,
            trust_tier=trust,
            metadata=body.metadata,
            idempotency_key=f"api-{uuid.uuid4()}",
        )

        return SourceResponse(
            source_id=str(source.source_id),
            vault_id=str(source.vault_id),
            format=source.format.value,
            title=version.title,
            authors=version.authors,
            url=version.url,
            status=version.status.value,
            version=version.version.number,
            trust_tier=version.trust_tier.value,
            created_at=str(source.created_at),
        )
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to ingest source")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@forgebase_router.get(
    "/vaults/{vault_id}/sources",
    response_model=SourceListResponse,
)
async def list_sources(
    vault_id: str,
    request: Request,
    fb=Depends(get_forgebase),
):
    """List sources in a vault."""
    _require_auth(request)
    try:
        from hephaestus.forgebase.domain.values import EntityId

        vid = EntityId(vault_id)
        uow = fb.uow_factory()
        async with uow:
            sources = await uow.sources.list_by_vault(vid)
            results = []
            for s in sources:
                head = await uow.sources.get_head_version(s.source_id)
                results.append(SourceResponse(
                    source_id=str(s.source_id),
                    vault_id=str(s.vault_id),
                    format=s.format.value,
                    title=head.title if head else "",
                    authors=head.authors if head else [],
                    url=head.url if head else None,
                    status=head.status.value if head else "",
                    version=head.version.number if head else 1,
                    trust_tier=head.trust_tier.value if head else "standard",
                    created_at=str(s.created_at),
                ))
            await uow.rollback()

        return SourceListResponse(sources=results, count=len(results))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to list sources")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@forgebase_router.get(
    "/vaults/{vault_id}/sources/{source_id}",
    response_model=SourceResponse,
)
async def get_source(
    vault_id: str,
    source_id: str,
    request: Request,
    fb=Depends(get_forgebase),
):
    """Get source detail."""
    _require_auth(request)
    try:
        from hephaestus.forgebase.domain.values import EntityId

        sid = EntityId(source_id)
        uow = fb.uow_factory()
        async with uow:
            source = await uow.sources.get(sid)
            if source is None:
                raise HTTPException(status_code=404, detail=f"Source {source_id} not found")
            head = await uow.sources.get_head_version(sid)
            await uow.rollback()

        return SourceResponse(
            source_id=str(source.source_id),
            vault_id=str(source.vault_id),
            format=source.format.value,
            title=head.title if head else "",
            authors=head.authors if head else [],
            url=head.url if head else None,
            status=head.status.value if head else "",
            version=head.version.number if head else 1,
            trust_tier=head.trust_tier.value if head else "standard",
            created_at=str(source.created_at),
        )
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to get source")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ===========================================================================
# 3. Compilation
# ===========================================================================


@forgebase_router.post(
    "/vaults/{vault_id}/compile",
)
async def compile_vault(
    vault_id: str,
    body: CompileRequest,
    request: Request,
    fb=Depends(get_forgebase),
):
    """Trigger vault compilation and stream progress via SSE."""
    _require_auth(request)

    from hephaestus.forgebase.domain.values import EntityId

    try:
        vid = EntityId(vault_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    async def _compile_stream():
        try:
            yield _sse_event("stage", {"stage": "scheduling", "message": "Scheduling compilation..."})

            # Schedule the compile job
            job = await fb.compile.schedule_compile(
                vault_id=vid,
                config=body.config,
                idempotency_key=f"compile-api-{vault_id}-{uuid.uuid4()}",
            )

            yield _sse_event("stage", {"stage": "compiling", "message": "Compiling sources...", "job_id": str(job.job_id)})

            # Run source compilation
            uow = fb.uow_factory()
            async with uow:
                sources = await uow.sources.list_by_vault(vid)
                await uow.rollback()

            compiled_count = 0
            for source in sources:
                try:
                    await fb.source_compiler.compile_source(vid, source.source_id)
                    compiled_count += 1
                    yield _sse_event("progress", {
                        "stage": "source_compile",
                        "message": f"Compiled source {compiled_count}/{len(sources)}",
                        "compiled": compiled_count,
                        "total": len(sources),
                    })
                except Exception as e:
                    yield _sse_event("warning", {
                        "message": f"Source compile warning: {e}",
                    })

            # Run vault synthesis
            yield _sse_event("stage", {"stage": "synthesizing", "message": "Synthesizing vault..."})
            try:
                await fb.vault_synthesizer.synthesize(vid)
            except Exception as e:
                yield _sse_event("warning", {"message": f"Synthesis warning: {e}"})

            # Complete the job
            await fb.compile.complete_compile(job.job_id)

            yield _sse_event("complete", {
                "stage": "complete",
                "message": "Compilation finished",
                "job_id": str(job.job_id),
                "sources_compiled": compiled_count,
            })
        except Exception as exc:
            logger.exception("Compilation failed")
            yield _sse_error(str(exc))

    return StreamingResponse(
        _compile_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@forgebase_router.get(
    "/vaults/{vault_id}/pages",
    response_model=PageListResponse,
)
async def list_pages(
    vault_id: str,
    request: Request,
    page_type: str | None = Query(default=None, description="Filter by page type"),
    fb=Depends(get_forgebase),
):
    """List pages in a vault."""
    _require_auth(request)
    try:
        from hephaestus.forgebase.domain.values import EntityId

        vid = EntityId(vault_id)
        uow = fb.uow_factory()
        async with uow:
            pages = await uow.pages.list_by_vault(vid, page_type=page_type)
            results = []
            for p in pages:
                head = await uow.pages.get_head_version(p.page_id)
                claims = await uow.claims.list_by_page(p.page_id)
                results.append(PageResponse(
                    page_id=str(p.page_id),
                    page_type=p.page_type.value,
                    page_key=p.page_key,
                    title=head.title if head else "",
                    version=head.version.number if head else 1,
                    claim_count=len(claims),
                    vault_id=str(p.vault_id),
                    created_at=str(p.created_at),
                ))
            await uow.rollback()

        return PageListResponse(pages=results, count=len(results))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to list pages")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@forgebase_router.get(
    "/vaults/{vault_id}/pages/{page_id}",
    response_model=PageDetailResponse,
)
async def get_page(
    vault_id: str,
    page_id: str,
    request: Request,
    fb=Depends(get_forgebase),
):
    """Get page detail with claims and links."""
    _require_auth(request)
    try:
        from hephaestus.forgebase.domain.values import EntityId

        pid = EntityId(page_id)
        uow = fb.uow_factory()
        async with uow:
            page = await uow.pages.get(pid)
            if page is None:
                raise HTTPException(status_code=404, detail=f"Page {page_id} not found")

            head = await uow.pages.get_head_version(pid)
            claims_list = await uow.claims.list_by_page(pid)

            claim_responses = []
            for c in claims_list:
                cv = await uow.claims.get_head_version(c.claim_id)
                supports = await uow.claim_supports.list_by_claim(c.claim_id)
                if cv:
                    claim_responses.append(ClaimResponse(
                        claim_id=str(c.claim_id),
                        page_id=str(c.page_id),
                        statement=cv.statement,
                        status=cv.status.value,
                        confidence=cv.confidence,
                        support_count=len(supports),
                        version=cv.version.number,
                        support_type=cv.support_type.value,
                        vault_id=str(c.vault_id),
                    ))

            links_raw = await uow.links.list_by_entity(pid)
            link_responses = []
            for lnk in links_raw:
                lv = await uow.links.get_head_version(lnk.link_id)
                if lv:
                    link_responses.append(LinkResponse(
                        link_id=str(lnk.link_id),
                        kind=lnk.kind.value,
                        source_entity=str(lv.source_entity),
                        target_entity=str(lv.target_entity),
                        label=lv.label,
                        weight=lv.weight,
                        version=lv.version.number,
                    ))

            await uow.rollback()

        return PageDetailResponse(
            page_id=str(page.page_id),
            page_type=page.page_type.value,
            page_key=page.page_key,
            title=head.title if head else "",
            version=head.version.number if head else 1,
            claim_count=len(claim_responses),
            vault_id=str(page.vault_id),
            created_at=str(page.created_at),
            summary=head.summary if head else "",
            claims=claim_responses,
            links=link_responses,
        )
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to get page")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@forgebase_router.get(
    "/vaults/{vault_id}/claims",
    response_model=ClaimListResponse,
)
async def list_claims(
    vault_id: str,
    request: Request,
    status: str | None = Query(default=None, description="Filter by claim status"),
    fb=Depends(get_forgebase),
):
    """List claims in a vault."""
    _require_auth(request)
    try:
        from hephaestus.forgebase.domain.values import EntityId

        vid = EntityId(vault_id)
        uow = fb.uow_factory()
        async with uow:
            claims = await uow.claims.list_by_vault(vid)
            results = []
            for c in claims:
                cv = await uow.claims.get_head_version(c.claim_id)
                if cv is None:
                    continue
                # Apply status filter if provided
                if status and cv.status.value != status:
                    continue
                supports = await uow.claim_supports.list_by_claim(c.claim_id)
                results.append(ClaimResponse(
                    claim_id=str(c.claim_id),
                    page_id=str(c.page_id),
                    statement=cv.statement,
                    status=cv.status.value,
                    confidence=cv.confidence,
                    support_count=len(supports),
                    version=cv.version.number,
                    support_type=cv.support_type.value,
                    vault_id=str(c.vault_id),
                ))
            await uow.rollback()

        return ClaimListResponse(claims=results, count=len(results))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to list claims")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ===========================================================================
# 4. Linting
# ===========================================================================


@forgebase_router.post("/vaults/{vault_id}/lint")
async def lint_vault(
    vault_id: str,
    body: LintRequest,
    request: Request,
    fb=Depends(get_forgebase),
):
    """Trigger a lint pass and stream progress via SSE."""
    _require_auth(request)

    from hephaestus.forgebase.domain.values import EntityId

    try:
        vid = EntityId(vault_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    async def _lint_stream():
        try:
            yield _sse_event("stage", {"stage": "starting", "message": "Starting lint pass..."})

            report = await fb.lint_engine.run_lint(
                vault_id=vid,
                config=body.config,
            )

            yield _sse_event("complete", {
                "stage": "complete",
                "message": "Lint pass finished",
                "report_id": str(report.report_id),
                "finding_count": report.finding_count,
                "debt_score": report.debt_score,
                "findings_by_category": report.findings_by_category,
                "findings_by_severity": report.findings_by_severity,
            })
        except Exception as exc:
            logger.exception("Lint failed")
            yield _sse_error(str(exc))

    return StreamingResponse(
        _lint_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@forgebase_router.get(
    "/vaults/{vault_id}/lint/report",
    response_model=LintReportResponse,
)
async def get_lint_report(
    vault_id: str,
    request: Request,
    fb=Depends(get_forgebase),
):
    """Get the latest lint report for a vault."""
    _require_auth(request)
    try:
        from hephaestus.forgebase.domain.values import EntityId

        vid = EntityId(vault_id)
        uow = fb.uow_factory()
        async with uow:
            reports = await uow.lint_reports.list_by_vault(vid)
            await uow.rollback()

        if not reports:
            raise HTTPException(status_code=404, detail="No lint reports found for this vault")

        latest = reports[-1]
        return LintReportResponse(
            report_id=str(latest.report_id),
            vault_id=str(latest.vault_id),
            job_id=str(latest.job_id),
            finding_count=latest.finding_count,
            debt_score=latest.debt_score,
            findings_by_category=latest.findings_by_category,
            findings_by_severity=latest.findings_by_severity,
            created_at=str(latest.created_at),
        )
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to get lint report")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@forgebase_router.get(
    "/vaults/{vault_id}/lint/findings",
    response_model=FindingListResponse,
)
async def list_findings(
    vault_id: str,
    request: Request,
    category: str | None = Query(default=None, description="Filter by finding category"),
    severity: str | None = Query(default=None, description="Filter by severity"),
    status: str | None = Query(default=None, description="Filter by disposition status"),
    fb=Depends(get_forgebase),
):
    """List lint findings for a vault with optional filters."""
    _require_auth(request)
    try:
        from hephaestus.forgebase.domain.values import EntityId

        vid = EntityId(vault_id)
        uow = fb.uow_factory()
        async with uow:
            findings = await uow.findings.list_by_vault(vid)
            await uow.rollback()

        # Apply filters
        if category:
            findings = [f for f in findings if f.category.value == category]
        if severity:
            findings = [f for f in findings if f.severity.value == severity]
        if status:
            findings = [f for f in findings if f.disposition.value == status]

        results = [
            FindingResponse(
                finding_id=str(f.finding_id),
                job_id=str(f.job_id),
                vault_id=str(f.vault_id),
                category=f.category.value,
                severity=f.severity.value,
                description=f.description,
                status=f.status.value,
                suggested_action=f.suggested_action,
                page_id=str(f.page_id) if f.page_id else None,
                claim_id=str(f.claim_id) if f.claim_id else None,
                confidence=f.confidence,
                remediation_status=f.remediation_status.value,
                disposition=f.disposition.value,
                remediation_route=f.remediation_route.value if f.remediation_route else None,
            )
            for f in findings
        ]

        return FindingListResponse(findings=results, count=len(results))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to list findings")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@forgebase_router.post(
    "/vaults/{vault_id}/lint/findings/{finding_id}/triage",
    response_model=FindingResponse,
)
async def triage_finding(
    vault_id: str,
    finding_id: str,
    body: FindingTriageRequest,
    request: Request,
    fb=Depends(get_forgebase),
):
    """Update a finding's remediation route."""
    _require_auth(request)
    try:
        from hephaestus.forgebase.domain.enums import (
            RemediationRoute,
            RemediationStatus,
            RouteSource,
        )
        from hephaestus.forgebase.domain.values import EntityId

        fid = EntityId(finding_id)

        try:
            route = RemediationRoute(body.remediation_route)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid remediation route: {body.remediation_route}. "
                f"Valid: {[r.value for r in RemediationRoute]}",
            )

        finding = await fb.lint.update_finding_remediation(
            fid,
            remediation_status=RemediationStatus.TRIAGED,
            route=route,
            route_source=RouteSource.USER,
        )

        return FindingResponse(
            finding_id=str(finding.finding_id),
            job_id=str(finding.job_id),
            vault_id=str(finding.vault_id),
            category=finding.category.value,
            severity=finding.severity.value,
            description=finding.description,
            status=finding.status.value,
            suggested_action=finding.suggested_action,
            page_id=str(finding.page_id) if finding.page_id else None,
            claim_id=str(finding.claim_id) if finding.claim_id else None,
            confidence=finding.confidence,
            remediation_status=finding.remediation_status.value,
            disposition=finding.disposition.value,
            remediation_route=finding.remediation_route.value if finding.remediation_route else None,
        )
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to triage finding")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ===========================================================================
# 5. Workbooks
# ===========================================================================


@forgebase_router.post(
    "/vaults/{vault_id}/workbooks",
    response_model=WorkbookResponse,
    status_code=201,
)
async def create_workbook(
    vault_id: str,
    body: WorkbookCreateRequest,
    request: Request,
    fb=Depends(get_forgebase),
):
    """Create a new workbook (branch) for a vault."""
    _require_auth(request)
    try:
        from hephaestus.forgebase.domain.enums import BranchPurpose
        from hephaestus.forgebase.domain.values import EntityId

        vid = EntityId(vault_id)

        try:
            purpose = BranchPurpose(body.purpose)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid purpose: {body.purpose}. "
                f"Valid: {[p.value for p in BranchPurpose]}",
            )

        workbook = await fb.branches.create_workbook(
            vault_id=vid,
            name=body.name,
            purpose=purpose,
        )

        return WorkbookResponse(
            workbook_id=str(workbook.workbook_id),
            vault_id=str(workbook.vault_id),
            name=workbook.name,
            purpose=workbook.purpose.value,
            status=workbook.status.value,
            base_revision_id=str(workbook.base_revision_id),
            created_at=str(workbook.created_at),
            created_by=str(workbook.created_by.actor_id),
        )
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to create workbook")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@forgebase_router.get(
    "/vaults/{vault_id}/workbooks",
    response_model=WorkbookListResponse,
)
async def list_workbooks(
    vault_id: str,
    request: Request,
    status: str | None = Query(default=None, description="Filter by workbook status"),
    fb=Depends(get_forgebase),
):
    """List workbooks for a vault."""
    _require_auth(request)
    try:
        from hephaestus.forgebase.domain.enums import WorkbookStatus
        from hephaestus.forgebase.domain.values import EntityId

        vid = EntityId(vault_id)
        status_filter = WorkbookStatus(status) if status else None

        uow = fb.uow_factory()
        async with uow:
            workbooks = await uow.workbooks.list_by_vault(vid, status=status_filter)
            await uow.rollback()

        results = [
            WorkbookResponse(
                workbook_id=str(wb.workbook_id),
                vault_id=str(wb.vault_id),
                name=wb.name,
                purpose=wb.purpose.value,
                status=wb.status.value,
                base_revision_id=str(wb.base_revision_id),
                created_at=str(wb.created_at),
                created_by=str(wb.created_by.actor_id),
            )
            for wb in workbooks
        ]

        return WorkbookListResponse(workbooks=results, count=len(results))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to list workbooks")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@forgebase_router.get(
    "/workbooks/{workbook_id}",
    response_model=WorkbookResponse,
)
async def get_workbook(
    workbook_id: str,
    request: Request,
    fb=Depends(get_forgebase),
):
    """Get workbook detail."""
    _require_auth(request)
    try:
        from hephaestus.forgebase.domain.values import EntityId

        wbid = EntityId(workbook_id)
        uow = fb.uow_factory()
        async with uow:
            wb = await uow.workbooks.get(wbid)
            if wb is None:
                raise HTTPException(status_code=404, detail=f"Workbook {workbook_id} not found")
            await uow.rollback()

        return WorkbookResponse(
            workbook_id=str(wb.workbook_id),
            vault_id=str(wb.vault_id),
            name=wb.name,
            purpose=wb.purpose.value,
            status=wb.status.value,
            base_revision_id=str(wb.base_revision_id),
            created_at=str(wb.created_at),
            created_by=str(wb.created_by.actor_id),
        )
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to get workbook")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@forgebase_router.get(
    "/workbooks/{workbook_id}/diff",
    response_model=WorkbookDiffResponse,
)
async def get_workbook_diff(
    workbook_id: str,
    request: Request,
    fb=Depends(get_forgebase),
):
    """Get diff of workbook changes vs canonical."""
    _require_auth(request)
    try:
        from hephaestus.forgebase.domain.enums import EntityKind
        from hephaestus.forgebase.domain.values import EntityId

        wbid = EntityId(workbook_id)
        uow = fb.uow_factory()
        async with uow:
            wb = await uow.workbooks.get(wbid)
            if wb is None:
                raise HTTPException(status_code=404, detail=f"Workbook {workbook_id} not found")

            page_heads = await uow.workbooks.list_page_heads(wbid)
            claim_heads = await uow.workbooks.list_claim_heads(wbid)
            link_heads = await uow.workbooks.list_link_heads(wbid)
            tombstones = await uow.workbooks.list_tombstones(wbid)

            # Classify page changes
            pages_added = 0
            pages_modified = 0
            for ph in page_heads:
                canonical = await uow.vaults.get_canonical_page_head(wb.vault_id, ph.page_id)
                if canonical is None:
                    pages_added += 1
                else:
                    pages_modified += 1

            # Classify claim changes
            claims_added = 0
            claims_modified = 0
            for ch in claim_heads:
                canonical = await uow.vaults.get_canonical_claim_head(wb.vault_id, ch.claim_id)
                if canonical is None:
                    claims_added += 1
                else:
                    claims_modified += 1

            # Classify link changes
            links_added = 0
            for lh in link_heads:
                canonical = await uow.vaults.get_canonical_link_head(wb.vault_id, lh.link_id)
                if canonical is None:
                    links_added += 1

            # Count deletions from tombstones
            pages_deleted = sum(1 for t in tombstones if t.entity_kind == EntityKind.PAGE)
            claims_deleted = sum(1 for t in tombstones if t.entity_kind == EntityKind.CLAIM)
            links_deleted = sum(1 for t in tombstones if t.entity_kind == EntityKind.LINK)

            await uow.rollback()

        return WorkbookDiffResponse(
            workbook_id=str(wb.workbook_id),
            vault_id=str(wb.vault_id),
            workbook_name=wb.name,
            pages_added=pages_added,
            pages_modified=pages_modified,
            pages_deleted=pages_deleted,
            claims_added=claims_added,
            claims_modified=claims_modified,
            claims_deleted=claims_deleted,
            links_added=links_added,
            links_deleted=links_deleted,
        )
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to compute workbook diff")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@forgebase_router.post(
    "/workbooks/{workbook_id}/merge",
    response_model=MergeResponse,
)
async def merge_workbook(
    workbook_id: str,
    request: Request,
    fb=Depends(get_forgebase),
):
    """Propose and execute a merge for a workbook."""
    _require_auth(request)
    try:
        from hephaestus.forgebase.domain.enums import MergeVerdict
        from hephaestus.forgebase.domain.values import EntityId

        wbid = EntityId(workbook_id)

        # Step 1: Propose merge
        proposal = await fb.merge.propose_merge(wbid)

        # Step 2: If clean, execute immediately
        if proposal.verdict == MergeVerdict.CLEAN:
            revision = await fb.merge.execute_merge(proposal.merge_id)
            return MergeResponse(
                merge_id=str(proposal.merge_id),
                verdict=proposal.verdict.value,
                resulting_revision=str(revision.revision_id),
            )
        else:
            # Return the proposal with conflict info
            return MergeResponse(
                merge_id=str(proposal.merge_id),
                verdict=proposal.verdict.value,
                resulting_revision=None,
            )
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to merge workbook")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@forgebase_router.post(
    "/workbooks/{workbook_id}/abandon",
    response_model=WorkbookResponse,
)
async def abandon_workbook(
    workbook_id: str,
    request: Request,
    fb=Depends(get_forgebase),
):
    """Abandon a workbook."""
    _require_auth(request)
    try:
        from hephaestus.forgebase.domain.values import EntityId

        wbid = EntityId(workbook_id)
        wb = await fb.branches.abandon_workbook(wbid)

        return WorkbookResponse(
            workbook_id=str(wb.workbook_id),
            vault_id=str(wb.vault_id),
            name=wb.name,
            purpose=wb.purpose.value,
            status=wb.status.value,
            base_revision_id=str(wb.base_revision_id),
            created_at=str(wb.created_at),
            created_by=str(wb.created_by.actor_id),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to abandon workbook")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ===========================================================================
# 6. Fusion
# ===========================================================================


@forgebase_router.post("/fuse")
async def trigger_fusion(
    body: FusionApiRequest,
    request: Request,
    fb=Depends(get_forgebase),
):
    """Trigger cross-vault fusion and stream progress via SSE."""
    _require_auth(request)

    from hephaestus.forgebase.domain.values import EntityId

    try:
        vault_ids = [EntityId(vid) for vid in body.vault_ids]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    async def _fusion_stream():
        try:
            yield _sse_event("stage", {
                "stage": "starting",
                "message": f"Starting fusion across {len(vault_ids)} vaults...",
            })

            from hephaestus.forgebase.contracts.fusion import FusionRequest
            from hephaestus.forgebase.domain.enums import FusionMode

            try:
                mode = FusionMode(body.mode)
            except ValueError:
                yield _sse_error(f"Invalid fusion mode: {body.mode}")
                return

            fusion_request = FusionRequest(
                vault_ids=vault_ids,
                problem=body.problem,
                fusion_mode=mode,
            )

            yield _sse_event("stage", {
                "stage": "fusing",
                "message": "Running fusion pipeline...",
            })

            result = await fb.fusion.fuse(fusion_request)

            yield _sse_event("complete", {
                "stage": "complete",
                "message": "Fusion finished",
                "fusion_id": str(result.fusion_id),
                "bridge_count": len(result.bridge_concepts),
                "transfer_count": len(result.transfer_opportunities),
            })
        except Exception as exc:
            logger.exception("Fusion failed")
            yield _sse_error(str(exc))

    return StreamingResponse(
        _fusion_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@forgebase_router.get(
    "/fusion-runs",
    response_model=FusionRunListResponse,
)
async def list_fusion_runs(
    request: Request,
    vault_id: str | None = Query(default=None, description="Filter by vault ID"),
    fb=Depends(get_forgebase),
):
    """List fusion runs, optionally filtered by vault ID."""
    _require_auth(request)
    try:
        from hephaestus.forgebase.domain.values import EntityId

        uow = fb.uow_factory()
        async with uow:
            if vault_id:
                vid = EntityId(vault_id)
                runs = await uow.fusion_runs.list_by_vaults([vid])
            else:
                # For listing all runs we query by problem=None to get all,
                # but that only works for runs without a problem. Instead,
                # use the repo's list_by_vaults which scans all rows.
                # We pass a sentinel to get all: manually query the table.
                cursor = await uow._db.execute(
                    "SELECT * FROM fb_fusion_runs ORDER BY created_at DESC"
                )
                rows = await cursor.fetchall()
                from hephaestus.forgebase.store.sqlite.fusion_run_repo import (
                    SqliteFusionRunRepository,
                )
                runs = [SqliteFusionRunRepository._row_to_run(r) for r in rows]
            await uow.rollback()

        results = [
            FusionRunResponse(
                fusion_run_id=str(r.fusion_run_id),
                vault_ids=[str(v) for v in r.vault_ids],
                problem=r.problem,
                fusion_mode=r.fusion_mode.value if hasattr(r.fusion_mode, "value") else str(r.fusion_mode),
                status=r.status,
                bridge_count=r.bridge_count,
                transfer_count=r.transfer_count,
                created_at=str(r.created_at),
                completed_at=str(r.completed_at) if r.completed_at else None,
            )
            for r in runs
        ]

        return FusionRunListResponse(runs=results, count=len(results))
    except Exception as exc:
        logger.exception("Failed to list fusion runs")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@forgebase_router.get(
    "/fusion-runs/{fusion_run_id}",
    response_model=FusionRunResponse,
)
async def get_fusion_run(
    fusion_run_id: str,
    request: Request,
    fb=Depends(get_forgebase),
):
    """Get fusion run detail."""
    _require_auth(request)
    try:
        from hephaestus.forgebase.domain.values import EntityId

        frid = EntityId(fusion_run_id)
        uow = fb.uow_factory()
        async with uow:
            run = await uow.fusion_runs.get(frid)
            if run is None:
                raise HTTPException(status_code=404, detail=f"Fusion run {fusion_run_id} not found")
            await uow.rollback()

        return FusionRunResponse(
            fusion_run_id=str(run.fusion_run_id),
            vault_ids=[str(v) for v in run.vault_ids],
            problem=run.problem,
            fusion_mode=run.fusion_mode.value if hasattr(run.fusion_mode, "value") else str(run.fusion_mode),
            status=run.status,
            bridge_count=run.bridge_count,
            transfer_count=run.transfer_count,
            created_at=str(run.created_at),
            completed_at=str(run.completed_at) if run.completed_at else None,
        )
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to get fusion run")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ===========================================================================
# 7. Knowledge Graph
# ===========================================================================


@forgebase_router.get(
    "/vaults/{vault_id}/graph",
    response_model=KnowledgeGraphResponse,
)
async def get_knowledge_graph(
    vault_id: str,
    request: Request,
    fb=Depends(get_forgebase),
):
    """Get the knowledge graph for a vault (pages as nodes, links as edges)."""
    _require_auth(request)
    try:
        from hephaestus.forgebase.domain.values import EntityId

        vid = EntityId(vault_id)
        uow = fb.uow_factory()
        async with uow:
            pages = await uow.pages.list_by_vault(vid)
            links = await uow.links.list_by_vault(vid)

            nodes = []
            for p in pages:
                head = await uow.pages.get_head_version(p.page_id)
                claims = await uow.claims.list_by_page(p.page_id)
                nodes.append(GraphNode(
                    id=str(p.page_id),
                    label=head.title if head else p.page_key,
                    page_type=p.page_type.value,
                    claim_count=len(claims),
                ))

            edges = []
            for lnk in links:
                lv = await uow.links.get_head_version(lnk.link_id)
                if lv:
                    edges.append(GraphEdge(
                        source=str(lv.source_entity),
                        target=str(lv.target_entity),
                        kind=lnk.kind.value,
                        label=lv.label,
                        weight=lv.weight,
                    ))

            await uow.rollback()

        return KnowledgeGraphResponse(
            vault_id=vault_id,
            nodes=nodes,
            edges=edges,
            node_count=len(nodes),
            edge_count=len(edges),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to get knowledge graph")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
