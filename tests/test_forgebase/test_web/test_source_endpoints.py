"""Tests for ForgeBase source ingestion API endpoints."""

from __future__ import annotations

import pytest


@pytest.fixture
async def vault_id(client):
    """Create a vault and return its ID."""
    resp = await client.post(
        "/api/forgebase/vaults",
        json={"name": "Source Test Vault", "description": "For source tests"},
    )
    return resp.json()["vault_id"]


@pytest.mark.asyncio
async def test_ingest_source(client, vault_id):
    """POST /api/forgebase/vaults/{id}/sources ingests content."""
    resp = await client.post(
        f"/api/forgebase/vaults/{vault_id}/sources",
        json={
            "content": "# Hello World\n\nThis is test content.",
            "format": "markdown",
            "title": "Test Source",
            "authors": ["Alice"],
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["source_id"].startswith("source_")
    assert data["vault_id"] == vault_id
    assert data["format"] == "markdown"
    assert data["title"] == "Test Source"
    assert data["status"] == "ingested"
    assert data["version"] == 1


@pytest.mark.asyncio
async def test_ingest_source_invalid_format(client, vault_id):
    """POST with invalid format returns 400."""
    resp = await client.post(
        f"/api/forgebase/vaults/{vault_id}/sources",
        json={
            "content": "Some content",
            "format": "invalid_format",
        },
    )
    assert resp.status_code == 400
    assert "Invalid source format" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_ingest_source_invalid_trust_tier(client, vault_id):
    """POST with invalid trust tier returns 400."""
    resp = await client.post(
        f"/api/forgebase/vaults/{vault_id}/sources",
        json={
            "content": "Some content",
            "format": "markdown",
            "trust_tier": "mega_trusted",
        },
    )
    assert resp.status_code == 400
    assert "Invalid trust tier" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_list_sources_empty(client, vault_id):
    """GET /api/forgebase/vaults/{id}/sources returns empty initially."""
    resp = await client.get(f"/api/forgebase/vaults/{vault_id}/sources")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 0


@pytest.mark.asyncio
async def test_list_sources_after_ingest(client, vault_id):
    """GET /api/forgebase/vaults/{id}/sources lists ingested sources."""
    await client.post(
        f"/api/forgebase/vaults/{vault_id}/sources",
        json={"content": "Content A", "format": "markdown", "title": "Source A"},
    )
    await client.post(
        f"/api/forgebase/vaults/{vault_id}/sources",
        json={"content": "Content B", "format": "markdown", "title": "Source B"},
    )

    resp = await client.get(f"/api/forgebase/vaults/{vault_id}/sources")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 2


@pytest.mark.asyncio
async def test_get_source_detail(client, vault_id):
    """GET /api/forgebase/vaults/{id}/sources/{sid} returns source detail."""
    create_resp = await client.post(
        f"/api/forgebase/vaults/{vault_id}/sources",
        json={"content": "Details here", "format": "markdown", "title": "Detailed"},
    )
    source_id = create_resp.json()["source_id"]

    resp = await client.get(f"/api/forgebase/vaults/{vault_id}/sources/{source_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["source_id"] == source_id
    assert data["title"] == "Detailed"


@pytest.mark.asyncio
async def test_get_source_not_found(client, vault_id):
    """GET /api/forgebase/vaults/{id}/sources/{bad} returns 400 for malformed ID."""
    resp = await client.get(f"/api/forgebase/vaults/{vault_id}/sources/bad_id")
    assert resp.status_code == 400
