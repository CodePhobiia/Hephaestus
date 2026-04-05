"""Tests for ForgeBase page and claim API endpoints."""
from __future__ import annotations

import pytest

from hephaestus.forgebase.domain.enums import ClaimStatus, PageType, SupportType


@pytest.fixture
async def vault_with_pages(client, forgebase):
    """Create a vault with pages and claims for testing."""
    # Create vault
    resp = await client.post(
        "/api/forgebase/vaults",
        json={"name": "Page Test Vault", "description": "For page/claim tests"},
    )
    vault_id = resp.json()["vault_id"]

    from hephaestus.forgebase.domain.values import EntityId

    vid = EntityId(vault_id)

    # Create pages via the service directly (not via API since compile is needed)
    page1, pv1 = await forgebase.pages.create_page(
        vault_id=vid,
        page_key="concept:test_concept",
        page_type=PageType.CONCEPT,
        title="Test Concept",
        content=b"# Test Concept\nA test concept page.",
    )
    page2, pv2 = await forgebase.pages.create_page(
        vault_id=vid,
        page_key="mechanism:test_mech",
        page_type=PageType.MECHANISM,
        title="Test Mechanism",
        content=b"# Test Mechanism\nA test mechanism page.",
    )

    # Create claims
    claim1, cv1 = await forgebase.claims.create_claim(
        vault_id=vid,
        page_id=page1.page_id,
        statement="This is a supported claim.",
        status=ClaimStatus.SUPPORTED,
        support_type=SupportType.DIRECT,
        confidence=0.95,
    )
    claim2, cv2 = await forgebase.claims.create_claim(
        vault_id=vid,
        page_id=page1.page_id,
        statement="This is a hypothesis.",
        status=ClaimStatus.HYPOTHESIS,
        support_type=SupportType.SYNTHESIZED,
        confidence=0.6,
    )

    return vault_id, page1, page2, claim1, claim2


@pytest.mark.asyncio
async def test_list_pages(client, vault_with_pages):
    """GET /api/forgebase/vaults/{id}/pages lists pages."""
    vault_id, *_ = vault_with_pages
    resp = await client.get(f"/api/forgebase/vaults/{vault_id}/pages")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 2
    page_types = {p["page_type"] for p in data["pages"]}
    assert "concept" in page_types
    assert "mechanism" in page_types


@pytest.mark.asyncio
async def test_list_pages_filter_by_type(client, vault_with_pages):
    """GET /api/forgebase/vaults/{id}/pages?page_type=concept filters pages."""
    vault_id, *_ = vault_with_pages
    resp = await client.get(
        f"/api/forgebase/vaults/{vault_id}/pages",
        params={"page_type": "concept"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["pages"][0]["page_type"] == "concept"


@pytest.mark.asyncio
async def test_get_page_detail(client, vault_with_pages):
    """GET /api/forgebase/vaults/{id}/pages/{pid} returns full page detail."""
    vault_id, page1, _, claim1, claim2 = vault_with_pages

    resp = await client.get(
        f"/api/forgebase/vaults/{vault_id}/pages/{page1.page_id}"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["page_id"] == str(page1.page_id)
    assert data["title"] == "Test Concept"
    assert data["page_type"] == "concept"
    assert data["claim_count"] == 2
    assert len(data["claims"]) == 2


@pytest.mark.asyncio
async def test_get_page_not_found(client, vault_with_pages):
    """GET /api/forgebase/vaults/{id}/pages/{bad} returns error."""
    vault_id, *_ = vault_with_pages
    resp = await client.get(f"/api/forgebase/vaults/{vault_id}/pages/invalid")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_list_claims(client, vault_with_pages):
    """GET /api/forgebase/vaults/{id}/claims lists all claims."""
    vault_id, *_ = vault_with_pages
    resp = await client.get(f"/api/forgebase/vaults/{vault_id}/claims")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 2
    statuses = {c["status"] for c in data["claims"]}
    assert "supported" in statuses
    assert "hypothesis" in statuses


@pytest.mark.asyncio
async def test_list_claims_filter_by_status(client, vault_with_pages):
    """GET /api/forgebase/vaults/{id}/claims?status=supported filters claims."""
    vault_id, *_ = vault_with_pages
    resp = await client.get(
        f"/api/forgebase/vaults/{vault_id}/claims",
        params={"status": "supported"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["claims"][0]["status"] == "supported"
    assert data["claims"][0]["confidence"] == 0.95
