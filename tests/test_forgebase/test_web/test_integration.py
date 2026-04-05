"""Integration test: full lifecycle via ForgeBase API.

Exercises: create vault -> ingest sources -> compile -> lint -> create workbook -> merge.
"""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_full_lifecycle(client, forgebase):
    """End-to-end flow through ForgeBase API endpoints."""
    # ----- 1. Create vault -----
    resp = await client.post(
        "/api/forgebase/vaults",
        json={"name": "Integration Vault", "description": "Full lifecycle test"},
    )
    assert resp.status_code == 201
    vault_id = resp.json()["vault_id"]

    # ----- 2. Ingest sources -----
    src1 = await client.post(
        f"/api/forgebase/vaults/{vault_id}/sources",
        json={
            "content": "# Neural Networks\n\nDeep learning uses neural networks with multiple layers.",
            "format": "markdown",
            "title": "Neural Networks Paper",
            "authors": ["Smith", "Jones"],
        },
    )
    assert src1.status_code == 201
    source_id = src1.json()["source_id"]

    src2 = await client.post(
        f"/api/forgebase/vaults/{vault_id}/sources",
        json={
            "content": "# Quantum Computing\n\nQubits enable superposition of states.",
            "format": "markdown",
            "title": "Quantum Computing Overview",
        },
    )
    assert src2.status_code == 201

    # ----- 3. Verify sources list -----
    sources_resp = await client.get(f"/api/forgebase/vaults/{vault_id}/sources")
    assert sources_resp.status_code == 200
    assert sources_resp.json()["count"] == 2

    # ----- 4. Verify source detail -----
    detail_resp = await client.get(
        f"/api/forgebase/vaults/{vault_id}/sources/{source_id}"
    )
    assert detail_resp.status_code == 200
    assert detail_resp.json()["title"] == "Neural Networks Paper"

    # ----- 5. Compile (SSE stream) -----
    compile_resp = await client.post(
        f"/api/forgebase/vaults/{vault_id}/compile",
        json={},
    )
    assert compile_resp.status_code == 200
    assert "text/event-stream" in compile_resp.headers["content-type"]

    # ----- 6. Check pages (may be empty if mock compiler produces none) -----
    pages_resp = await client.get(f"/api/forgebase/vaults/{vault_id}/pages")
    assert pages_resp.status_code == 200

    # ----- 7. Lint (SSE stream) -----
    lint_resp = await client.post(
        f"/api/forgebase/vaults/{vault_id}/lint",
        json={},
    )
    assert lint_resp.status_code == 200
    assert "text/event-stream" in lint_resp.headers["content-type"]

    # ----- 8. Create workbook -----
    wb_resp = await client.post(
        f"/api/forgebase/vaults/{vault_id}/workbooks",
        json={"name": "integration-branch", "purpose": "research"},
    )
    assert wb_resp.status_code == 201
    workbook_id = wb_resp.json()["workbook_id"]

    # ----- 9. Check diff (empty since no branch changes) -----
    diff_resp = await client.get(f"/api/forgebase/workbooks/{workbook_id}/diff")
    assert diff_resp.status_code == 200
    assert diff_resp.json()["pages_added"] == 0

    # ----- 10. Abandon workbook -----
    abandon_resp = await client.post(
        f"/api/forgebase/workbooks/{workbook_id}/abandon"
    )
    assert abandon_resp.status_code == 200
    assert abandon_resp.json()["status"] == "abandoned"

    # ----- 11. Knowledge graph -----
    graph_resp = await client.get(f"/api/forgebase/vaults/{vault_id}/graph")
    assert graph_resp.status_code == 200
    graph = graph_resp.json()
    assert "nodes" in graph
    assert "edges" in graph

    # ----- 12. Vault detail with stats -----
    vault_resp = await client.get(f"/api/forgebase/vaults/{vault_id}")
    assert vault_resp.status_code == 200
    detail = vault_resp.json()
    assert detail["name"] == "Integration Vault"
    assert detail["source_count"] == 2


@pytest.mark.asyncio
async def test_vault_list_reflects_counts(client, forgebase):
    """Vault list endpoint returns accurate counts."""
    resp = await client.post(
        "/api/forgebase/vaults",
        json={"name": "Counts Vault", "description": "Count test"},
    )
    vault_id = resp.json()["vault_id"]

    # Ingest a source
    await client.post(
        f"/api/forgebase/vaults/{vault_id}/sources",
        json={"content": "Content", "format": "markdown", "title": "S1"},
    )

    # List should show source_count = 1
    list_resp = await client.get("/api/forgebase/vaults")
    assert list_resp.status_code == 200
    vaults = list_resp.json()["vaults"]
    target = next(v for v in vaults if v["vault_id"] == vault_id)
    assert target["source_count"] == 1


@pytest.mark.asyncio
async def test_fusion_across_vaults(client, forgebase):
    """Fusion endpoint works when triggered with two vaults."""
    from hephaestus.forgebase.domain.enums import ClaimStatus, PageType, SupportType
    from hephaestus.forgebase.domain.values import EntityId

    # Create vault A
    resp_a = await client.post(
        "/api/forgebase/vaults",
        json={"name": "Fusion A", "description": "First"},
    )
    vid_a = resp_a.json()["vault_id"]
    eid_a = EntityId(vid_a)

    page_a, _ = await forgebase.pages.create_page(
        vault_id=eid_a,
        page_key="concept:a",
        page_type=PageType.CONCEPT,
        title="A",
        content=b"A content.",
    )
    await forgebase.claims.create_claim(
        vault_id=eid_a,
        page_id=page_a.page_id,
        statement="Claim A",
        status=ClaimStatus.SUPPORTED,
        support_type=SupportType.DIRECT,
        confidence=0.9,
    )

    # Create vault B
    resp_b = await client.post(
        "/api/forgebase/vaults",
        json={"name": "Fusion B", "description": "Second"},
    )
    vid_b = resp_b.json()["vault_id"]
    eid_b = EntityId(vid_b)

    page_b, _ = await forgebase.pages.create_page(
        vault_id=eid_b,
        page_key="concept:b",
        page_type=PageType.CONCEPT,
        title="B",
        content=b"B content.",
    )
    await forgebase.claims.create_claim(
        vault_id=eid_b,
        page_id=page_b.page_id,
        statement="Claim B",
        status=ClaimStatus.SUPPORTED,
        support_type=SupportType.DIRECT,
        confidence=0.85,
    )

    # Trigger fusion via API
    fuse_resp = await client.post(
        "/api/forgebase/fuse",
        json={"vault_ids": [vid_a, vid_b], "problem": "Integration fusion test"},
    )
    assert fuse_resp.status_code == 200
    body = fuse_resp.text
    assert "event:" in body

    # List fusion runs
    runs_resp = await client.get("/api/forgebase/fusion-runs")
    assert runs_resp.status_code == 200
    assert runs_resp.json()["count"] >= 1
