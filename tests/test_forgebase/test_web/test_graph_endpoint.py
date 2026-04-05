"""Tests for ForgeBase knowledge graph API endpoint."""

from __future__ import annotations

import pytest

from hephaestus.forgebase.domain.enums import (
    ClaimStatus,
    LinkKind,
    PageType,
    SupportType,
)


@pytest.mark.asyncio
async def test_knowledge_graph_empty(client):
    """GET /api/forgebase/vaults/{id}/graph returns empty graph for fresh vault."""
    create_resp = await client.post(
        "/api/forgebase/vaults",
        json={"name": "Graph Vault", "description": "For graph test"},
    )
    vault_id = create_resp.json()["vault_id"]

    resp = await client.get(f"/api/forgebase/vaults/{vault_id}/graph")
    assert resp.status_code == 200
    data = resp.json()
    assert data["vault_id"] == vault_id
    assert data["node_count"] == 0
    assert data["edge_count"] == 0
    assert data["nodes"] == []
    assert data["edges"] == []


@pytest.mark.asyncio
async def test_knowledge_graph_with_data(client, forgebase):
    """GET /api/forgebase/vaults/{id}/graph returns nodes and edges."""
    from hephaestus.forgebase.domain.values import EntityId

    create_resp = await client.post(
        "/api/forgebase/vaults",
        json={"name": "Graph Vault 2", "description": "With data"},
    )
    vault_id = create_resp.json()["vault_id"]
    vid = EntityId(vault_id)

    # Create two pages
    page1, _ = await forgebase.pages.create_page(
        vault_id=vid,
        page_key="concept:node_a",
        page_type=PageType.CONCEPT,
        title="Node A",
        content=b"Node A content.",
    )
    page2, _ = await forgebase.pages.create_page(
        vault_id=vid,
        page_key="concept:node_b",
        page_type=PageType.CONCEPT,
        title="Node B",
        content=b"Node B content.",
    )

    # Create a claim on page1
    await forgebase.claims.create_claim(
        vault_id=vid,
        page_id=page1.page_id,
        statement="Node A claim.",
        status=ClaimStatus.SUPPORTED,
        support_type=SupportType.DIRECT,
        confidence=0.9,
    )

    # Create a link between pages
    await forgebase.links.create_link(
        vault_id=vid,
        kind=LinkKind.RELATED_CONCEPT,
        source_entity=page1.page_id,
        target_entity=page2.page_id,
        label="relates to",
        weight=0.8,
    )

    resp = await client.get(f"/api/forgebase/vaults/{vault_id}/graph")
    assert resp.status_code == 200
    data = resp.json()
    assert data["node_count"] == 2
    assert data["edge_count"] == 1

    # Verify nodes
    node_ids = {n["id"] for n in data["nodes"]}
    assert str(page1.page_id) in node_ids
    assert str(page2.page_id) in node_ids

    # Verify the node with claims has claim_count > 0
    node_a = next(n for n in data["nodes"] if n["id"] == str(page1.page_id))
    assert node_a["claim_count"] == 1
    assert node_a["label"] == "Node A"
    assert node_a["page_type"] == "concept"

    # Verify edge
    edge = data["edges"][0]
    assert edge["source"] == str(page1.page_id)
    assert edge["target"] == str(page2.page_id)
    assert edge["kind"] == "related_concept"
    assert edge["label"] == "relates to"
    assert edge["weight"] == 0.8
