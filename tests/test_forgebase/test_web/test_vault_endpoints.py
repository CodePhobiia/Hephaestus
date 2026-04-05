"""Tests for ForgeBase vault management API endpoints."""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_create_vault(client):
    """POST /api/forgebase/vaults creates a vault and returns it."""
    resp = await client.post(
        "/api/forgebase/vaults",
        json={"name": "My Vault", "description": "Test vault"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "My Vault"
    assert data["description"] == "Test vault"
    assert "vault_id" in data
    assert data["vault_id"].startswith("vault_")


@pytest.mark.asyncio
async def test_create_vault_missing_name(client):
    """POST /api/forgebase/vaults with empty name returns 422."""
    resp = await client.post(
        "/api/forgebase/vaults",
        json={"name": "", "description": "Test"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_vaults_empty(client):
    """GET /api/forgebase/vaults returns empty list initially."""
    resp = await client.get("/api/forgebase/vaults")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 0
    assert data["vaults"] == []


@pytest.mark.asyncio
async def test_list_vaults_after_create(client):
    """GET /api/forgebase/vaults returns created vaults."""
    await client.post(
        "/api/forgebase/vaults",
        json={"name": "V1", "description": "First"},
    )
    await client.post(
        "/api/forgebase/vaults",
        json={"name": "V2", "description": "Second"},
    )

    resp = await client.get("/api/forgebase/vaults")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 2
    names = {v["name"] for v in data["vaults"]}
    assert names == {"V1", "V2"}


@pytest.mark.asyncio
async def test_get_vault_detail(client):
    """GET /api/forgebase/vaults/{id} returns vault detail."""
    create_resp = await client.post(
        "/api/forgebase/vaults",
        json={"name": "Detail", "description": "Detail test"},
    )
    vault_id = create_resp.json()["vault_id"]

    resp = await client.get(f"/api/forgebase/vaults/{vault_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["vault_id"] == vault_id
    assert data["name"] == "Detail"
    assert data["page_count"] == 0
    assert data["claim_count"] == 0
    assert data["source_count"] == 0


@pytest.mark.asyncio
async def test_get_vault_not_found(client):
    """GET /api/forgebase/vaults/{bad_id} returns 400 for malformed ID."""
    resp = await client.get("/api/forgebase/vaults/bad_id")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_archive_vault(client):
    """DELETE /api/forgebase/vaults/{id} archives the vault."""
    create_resp = await client.post(
        "/api/forgebase/vaults",
        json={"name": "To Archive", "description": "Will be archived"},
    )
    vault_id = create_resp.json()["vault_id"]

    resp = await client.delete(f"/api/forgebase/vaults/{vault_id}")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_archive_vault_not_found(client):
    """DELETE /api/forgebase/vaults/{bad_id} returns 400."""
    resp = await client.delete("/api/forgebase/vaults/bad_id")
    assert resp.status_code == 400
