"""Tests for ForgeBase workbook API endpoints."""

from __future__ import annotations

import pytest

from hephaestus.forgebase.domain.enums import PageType


@pytest.fixture
async def vault_id(client):
    """Create a vault and return its ID."""
    resp = await client.post(
        "/api/forgebase/vaults",
        json={"name": "Workbook Test Vault", "description": "For workbook tests"},
    )
    return resp.json()["vault_id"]


@pytest.mark.asyncio
async def test_create_workbook(client, vault_id):
    """POST /api/forgebase/vaults/{id}/workbooks creates a workbook."""
    resp = await client.post(
        f"/api/forgebase/vaults/{vault_id}/workbooks",
        json={"name": "test-branch", "purpose": "manual"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "test-branch"
    assert data["purpose"] == "manual"
    assert data["status"] == "open"
    assert data["vault_id"] == vault_id
    assert data["workbook_id"].startswith("wb_")


@pytest.mark.asyncio
async def test_create_workbook_invalid_purpose(client, vault_id):
    """POST with invalid purpose returns 400."""
    resp = await client.post(
        f"/api/forgebase/vaults/{vault_id}/workbooks",
        json={"name": "bad-branch", "purpose": "invalid_purpose"},
    )
    assert resp.status_code == 400
    assert "Invalid purpose" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_list_workbooks(client, vault_id):
    """GET /api/forgebase/vaults/{id}/workbooks lists workbooks."""
    await client.post(
        f"/api/forgebase/vaults/{vault_id}/workbooks",
        json={"name": "branch-1", "purpose": "research"},
    )
    await client.post(
        f"/api/forgebase/vaults/{vault_id}/workbooks",
        json={"name": "branch-2", "purpose": "manual"},
    )

    resp = await client.get(f"/api/forgebase/vaults/{vault_id}/workbooks")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 2


@pytest.mark.asyncio
async def test_get_workbook_detail(client, vault_id):
    """GET /api/forgebase/workbooks/{id} returns workbook detail."""
    create_resp = await client.post(
        f"/api/forgebase/vaults/{vault_id}/workbooks",
        json={"name": "detail-branch", "purpose": "research"},
    )
    workbook_id = create_resp.json()["workbook_id"]

    resp = await client.get(f"/api/forgebase/workbooks/{workbook_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["workbook_id"] == workbook_id
    assert data["name"] == "detail-branch"


@pytest.mark.asyncio
async def test_get_workbook_not_found(client):
    """GET /api/forgebase/workbooks/{bad} returns error."""
    resp = await client.get("/api/forgebase/workbooks/invalid")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_workbook_diff_empty(client, vault_id):
    """GET /api/forgebase/workbooks/{id}/diff shows no changes for fresh branch."""
    create_resp = await client.post(
        f"/api/forgebase/vaults/{vault_id}/workbooks",
        json={"name": "diff-branch", "purpose": "manual"},
    )
    workbook_id = create_resp.json()["workbook_id"]

    resp = await client.get(f"/api/forgebase/workbooks/{workbook_id}/diff")
    assert resp.status_code == 200
    data = resp.json()
    assert data["pages_added"] == 0
    assert data["pages_modified"] == 0
    assert data["pages_deleted"] == 0
    assert data["claims_added"] == 0


@pytest.mark.asyncio
async def test_workbook_diff_with_changes(client, vault_id, forgebase):
    """GET /api/forgebase/workbooks/{id}/diff reflects branch changes."""
    from hephaestus.forgebase.domain.values import EntityId

    vid = EntityId(vault_id)

    create_resp = await client.post(
        f"/api/forgebase/vaults/{vault_id}/workbooks",
        json={"name": "change-branch", "purpose": "manual"},
    )
    workbook_id = create_resp.json()["workbook_id"]
    wbid = EntityId(workbook_id)

    # Add a page on the branch
    await forgebase.pages.create_page(
        vault_id=vid,
        page_key="concept:branch_page",
        page_type=PageType.CONCEPT,
        title="Branch Page",
        content=b"Content on branch.",
        workbook_id=wbid,
    )

    resp = await client.get(f"/api/forgebase/workbooks/{workbook_id}/diff")
    assert resp.status_code == 200
    data = resp.json()
    assert data["pages_added"] == 1


@pytest.mark.asyncio
async def test_merge_clean_workbook(client, vault_id, forgebase):
    """POST /api/forgebase/workbooks/{id}/merge succeeds for clean merge."""
    from hephaestus.forgebase.domain.values import EntityId

    vid = EntityId(vault_id)

    create_resp = await client.post(
        f"/api/forgebase/vaults/{vault_id}/workbooks",
        json={"name": "merge-branch", "purpose": "manual"},
    )
    workbook_id = create_resp.json()["workbook_id"]
    wbid = EntityId(workbook_id)

    # Add a page on the branch
    await forgebase.pages.create_page(
        vault_id=vid,
        page_key="concept:merge_page",
        page_type=PageType.CONCEPT,
        title="Merge Page",
        content=b"Will be merged.",
        workbook_id=wbid,
    )

    resp = await client.post(f"/api/forgebase/workbooks/{workbook_id}/merge")
    assert resp.status_code == 200
    data = resp.json()
    assert data["verdict"] == "clean"
    assert data["resulting_revision"] is not None


@pytest.mark.asyncio
async def test_abandon_workbook(client, vault_id):
    """POST /api/forgebase/workbooks/{id}/abandon sets status to abandoned."""
    create_resp = await client.post(
        f"/api/forgebase/vaults/{vault_id}/workbooks",
        json={"name": "abandon-branch", "purpose": "manual"},
    )
    workbook_id = create_resp.json()["workbook_id"]

    resp = await client.post(f"/api/forgebase/workbooks/{workbook_id}/abandon")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "abandoned"
