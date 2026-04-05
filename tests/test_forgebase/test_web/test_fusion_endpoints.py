"""Tests for ForgeBase fusion API endpoints."""

from __future__ import annotations

import pytest

from hephaestus.forgebase.domain.enums import ClaimStatus, PageType, SupportType


@pytest.fixture
async def two_vaults(client, forgebase):
    """Create two vaults with pages and claims for fusion testing."""
    from hephaestus.forgebase.domain.values import EntityId

    # Vault 1
    resp1 = await client.post(
        "/api/forgebase/vaults",
        json={"name": "Vault A", "description": "First vault for fusion"},
    )
    vid1 = resp1.json()["vault_id"]
    eid1 = EntityId(vid1)

    page1, _ = await forgebase.pages.create_page(
        vault_id=eid1,
        page_key="concept:fusion_a",
        page_type=PageType.CONCEPT,
        title="Concept A",
        content=b"# Concept A\nDomain A knowledge.",
    )
    await forgebase.claims.create_claim(
        vault_id=eid1,
        page_id=page1.page_id,
        statement="Claim from domain A.",
        status=ClaimStatus.SUPPORTED,
        support_type=SupportType.DIRECT,
        confidence=0.9,
    )

    # Vault 2
    resp2 = await client.post(
        "/api/forgebase/vaults",
        json={"name": "Vault B", "description": "Second vault for fusion"},
    )
    vid2 = resp2.json()["vault_id"]
    eid2 = EntityId(vid2)

    page2, _ = await forgebase.pages.create_page(
        vault_id=eid2,
        page_key="concept:fusion_b",
        page_type=PageType.CONCEPT,
        title="Concept B",
        content=b"# Concept B\nDomain B knowledge.",
    )
    await forgebase.claims.create_claim(
        vault_id=eid2,
        page_id=page2.page_id,
        statement="Claim from domain B.",
        status=ClaimStatus.SUPPORTED,
        support_type=SupportType.DIRECT,
        confidence=0.85,
    )

    return vid1, vid2


@pytest.mark.asyncio
async def test_trigger_fusion_sse(client, two_vaults):
    """POST /api/forgebase/fuse returns SSE stream."""
    vid1, vid2 = two_vaults
    resp = await client.post(
        "/api/forgebase/fuse",
        json={"vault_ids": [vid1, vid2], "problem": "Test fusion", "mode": "strict"},
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    body = resp.text
    assert "event: stage" in body or "event: complete" in body


@pytest.mark.asyncio
async def test_trigger_fusion_single_vault(client, two_vaults):
    """POST /api/forgebase/fuse with < 2 vaults returns 422."""
    vid1, _ = two_vaults
    resp = await client.post(
        "/api/forgebase/fuse",
        json={"vault_ids": [vid1], "problem": "Test"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_fusion_runs(client, two_vaults, forgebase):
    """GET /api/forgebase/fusion-runs lists runs after fusion."""
    vid1, vid2 = two_vaults

    from hephaestus.forgebase.contracts.fusion import FusionRequest
    from hephaestus.forgebase.domain.enums import FusionMode
    from hephaestus.forgebase.domain.values import EntityId

    fusion_req = FusionRequest(
        vault_ids=[EntityId(vid1), EntityId(vid2)],
        problem="Test fusion run",
        fusion_mode=FusionMode.STRICT,
    )
    await forgebase.fusion.fuse(fusion_req)

    resp = await client.get("/api/forgebase/fusion-runs")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] >= 1
    assert any(r["status"] == "completed" for r in data["runs"])


@pytest.mark.asyncio
async def test_get_fusion_run_detail(client, two_vaults, forgebase):
    """GET /api/forgebase/fusion-runs/{id} returns run detail."""
    vid1, vid2 = two_vaults

    from hephaestus.forgebase.contracts.fusion import FusionRequest
    from hephaestus.forgebase.domain.enums import FusionMode
    from hephaestus.forgebase.domain.values import EntityId

    fusion_req = FusionRequest(
        vault_ids=[EntityId(vid1), EntityId(vid2)],
        problem="Detail test",
        fusion_mode=FusionMode.STRICT,
    )
    result = await forgebase.fusion.fuse(fusion_req)

    # Find the run from the list
    list_resp = await client.get("/api/forgebase/fusion-runs")
    runs = list_resp.json()["runs"]
    assert len(runs) >= 1

    run_id = runs[0]["fusion_run_id"]
    resp = await client.get(f"/api/forgebase/fusion-runs/{run_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["fusion_run_id"] == run_id
    assert data["status"] == "completed"


@pytest.mark.asyncio
async def test_get_fusion_run_not_found(client):
    """GET /api/forgebase/fusion-runs/{bad} returns error."""
    resp = await client.get("/api/forgebase/fusion-runs/invalid")
    assert resp.status_code == 400
