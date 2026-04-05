"""Tests for InventionIngester — structured ingestion of Genesis invention reports.

Uses a real SQLite backend (no mocks) to exercise the full service stack.

Key scenarios:
  1. Single invention → INVENTION page + InventionPageMeta + claims + concept candidates + links
  2. Multiple inventions → multiple pages
  3. Dict-style report
  4. Empty report → empty list returned
  5. Run artifacts recorded
"""

from __future__ import annotations

import pytest

from hephaestus.forgebase.domain.enums import (
    ClaimStatus,
    InventionEpistemicState,
    LinkKind,
    PageType,
    SupportType,
)
from hephaestus.forgebase.integration.invention_ingester import InventionIngester

# ---------------------------------------------------------------------------
# Mock report data
# ---------------------------------------------------------------------------

MOCK_INVENTION_REPORT = {
    "problem": "I need a load balancer for traffic spikes",
    "verified_inventions": [
        {
            "invention_name": "Pheromone-Gradient Load Balancer",
            "source_domain": "Biology — Ant Colony Foraging",
            "target_domain": "Distributed Systems — Load Balancing",
            "mechanism": "Ant colonies solve routing without central planner via pheromone gradients.",
            "mapping": "Ant -> Request, Pheromone -> Latency score",
            "architecture": "Each server maintains pheromone level P(s,t).",
            "roadmap": "Phase 1: Core router. Phase 2: Decay scheduler.",
            "limitations": "Ants have path memory; HTTP requests don't.",
            "novelty_score": 0.93,
            "fidelity_score": 0.88,
            "domain_distance": 0.91,
            "key_insight": "Pheromone evaporation enables automatic load redistribution.",
        }
    ],
    "total_cost_usd": 1.18,
    "models_used": ["claude-opus-4-5", "gpt-4o"],
}

MOCK_MULTI_INVENTION_REPORT = {
    "verified_inventions": [
        {
            "invention_name": "Pheromone Load Balancer",
            "source_domain": "Biology",
            "mechanism": "Ant pheromone routing.",
            "novelty_score": 0.93,
            "fidelity_score": 0.88,
        },
        {
            "invention_name": "Crystalline Cache Eviction",
            "source_domain": "Chemistry",
            "mechanism": "Crystal nucleation patterns for cache replacement.",
            "novelty_score": 0.85,
            "fidelity_score": 0.90,
        },
    ],
    "total_cost_usd": 2.50,
    "models_used": ["claude-opus-4-5"],
}

MOCK_EMPTY_REPORT = {
    "verified_inventions": [],
    "total_cost_usd": 0.10,
    "models_used": ["claude-opus-4-5"],
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def page_service(uow_factory, actor):
    from hephaestus.forgebase.service.page_service import PageService

    return PageService(uow_factory=uow_factory, default_actor=actor)


@pytest.fixture
async def claim_service(uow_factory, actor):
    from hephaestus.forgebase.service.claim_service import ClaimService

    return ClaimService(uow_factory=uow_factory, default_actor=actor)


@pytest.fixture
async def link_service(uow_factory, actor):
    from hephaestus.forgebase.service.link_service import LinkService

    return LinkService(uow_factory=uow_factory, default_actor=actor)


@pytest.fixture
async def ingester(
    uow_factory,
    page_service,
    claim_service,
    link_service,
    ingest_service,
    run_integration_service,
    actor,
):
    return InventionIngester(
        uow_factory=uow_factory,
        page_service=page_service,
        claim_service=claim_service,
        link_service=link_service,
        ingest_service=ingest_service,
        run_integration_service=run_integration_service,
        default_actor=actor,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestInventionIngester:
    async def test_ingest_creates_invention_page(
        self,
        vault,
        ingester,
        sqlite_db,
    ):
        """Ingesting a report creates a page with PageType.INVENTION and content including mechanism."""
        page_ids = await ingester.ingest_invention_report(
            vault_id=vault.vault_id,
            run_id="genesis-001",
            report=MOCK_INVENTION_REPORT,
        )

        assert len(page_ids) == 1

        # Verify the page exists and has the right type
        cursor = await sqlite_db.execute(
            "SELECT page_type, page_key FROM fb_pages WHERE page_id = ?",
            (str(page_ids[0]),),
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row["page_type"] == PageType.INVENTION.value

        # Verify page key contains invention slug
        assert "inventions/" in row["page_key"]

        # Verify page version has content with mechanism text
        cursor = await sqlite_db.execute(
            "SELECT title FROM fb_page_versions WHERE page_id = ? AND version = 1",
            (str(page_ids[0]),),
        )
        row = await cursor.fetchone()
        assert row is not None
        assert "Pheromone-Gradient Load Balancer" in row["title"]

    async def test_ingest_creates_meta_proposed(
        self,
        vault,
        ingester,
        sqlite_db,
    ):
        """Ingesting creates InventionPageMeta with state=PROPOSED."""
        page_ids = await ingester.ingest_invention_report(
            vault_id=vault.vault_id,
            run_id="genesis-002",
            report=MOCK_INVENTION_REPORT,
        )

        cursor = await sqlite_db.execute(
            "SELECT invention_state, run_id, run_type, novelty_score, fidelity_score, "
            "domain_distance, source_domain, total_cost_usd, models_used "
            "FROM fb_invention_page_meta WHERE page_id = ?",
            (str(page_ids[0]),),
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row["invention_state"] == InventionEpistemicState.PROPOSED.value
        assert row["run_id"] == "genesis-002"
        assert row["run_type"] == "genesis"
        assert row["novelty_score"] == pytest.approx(0.93)
        assert row["fidelity_score"] == pytest.approx(0.88)
        assert row["domain_distance"] == pytest.approx(0.91)
        assert row["source_domain"] == "Biology — Ant Colony Foraging"
        assert row["total_cost_usd"] == pytest.approx(1.18)

    async def test_ingest_creates_hypothesis_claims(
        self,
        vault,
        ingester,
        sqlite_db,
    ):
        """Ingesting creates claims with HYPOTHESIS status and GENERATED support_type."""
        page_ids = await ingester.ingest_invention_report(
            vault_id=vault.vault_id,
            run_id="genesis-003",
            report=MOCK_INVENTION_REPORT,
        )

        cursor = await sqlite_db.execute(
            "SELECT cv.status, cv.support_type, cv.statement "
            "FROM fb_claim_versions cv "
            "JOIN fb_claims c ON c.claim_id = cv.claim_id "
            "WHERE c.page_id = ? AND cv.version = 1",
            (str(page_ids[0]),),
        )
        rows = await cursor.fetchall()
        assert len(rows) >= 1  # at least mechanism claim

        for row in rows:
            assert row["status"] == ClaimStatus.HYPOTHESIS.value
            assert row["support_type"] == SupportType.GENERATED.value

        # At least one claim should mention mechanism-related content
        statements = [row["statement"] for row in rows]
        assert any("pheromone" in s.lower() or "mechanism" in s.lower() for s in statements)

    async def test_ingest_creates_concept_candidates(
        self,
        vault,
        ingester,
        sqlite_db,
    ):
        """Ingesting creates concept candidates for source and target domains."""
        page_ids = await ingester.ingest_invention_report(
            vault_id=vault.vault_id,
            run_id="genesis-004",
            report=MOCK_INVENTION_REPORT,
        )

        cursor = await sqlite_db.execute(
            "SELECT name, candidate_kind, status FROM fb_concept_candidates WHERE vault_id = ?",
            (str(vault.vault_id),),
        )
        rows = await cursor.fetchall()
        assert len(rows) >= 1  # at least one concept candidate

    async def test_ingest_creates_semantic_links(
        self,
        vault,
        ingester,
        sqlite_db,
    ):
        """Ingesting creates MAPS_TO links between source and target domain concepts."""
        page_ids = await ingester.ingest_invention_report(
            vault_id=vault.vault_id,
            run_id="genesis-005",
            report=MOCK_INVENTION_REPORT,
        )

        cursor = await sqlite_db.execute(
            "SELECT kind FROM fb_links WHERE vault_id = ?",
            (str(vault.vault_id),),
        )
        rows = await cursor.fetchall()
        kinds = {row["kind"] for row in rows}
        # Should have at least one MAPS_TO link
        assert LinkKind.MAPS_TO.value in kinds

    async def test_ingest_records_run_artifacts(
        self,
        vault,
        ingester,
        sqlite_db,
    ):
        """Ingesting records a KnowledgeRunRef and artifacts."""
        page_ids = await ingester.ingest_invention_report(
            vault_id=vault.vault_id,
            run_id="genesis-006",
            report=MOCK_INVENTION_REPORT,
        )

        # Verify run ref was created
        cursor = await sqlite_db.execute(
            "SELECT run_id, run_type, sync_status FROM fb_run_refs WHERE run_id = ?",
            ("genesis-006",),
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row["run_type"] == "genesis"
        assert row["sync_status"] == "synced"

        # Verify artifacts were recorded
        cursor = await sqlite_db.execute(
            "SELECT COUNT(*) as cnt FROM fb_run_artifacts",
        )
        row = await cursor.fetchone()
        assert row["cnt"] >= 1  # at least the page artifact

    async def test_ingest_handles_dict_report(
        self,
        vault,
        ingester,
        sqlite_db,
    ):
        """Works with a dict-style report."""
        page_ids = await ingester.ingest_invention_report(
            vault_id=vault.vault_id,
            run_id="genesis-007",
            report=MOCK_INVENTION_REPORT,
        )
        assert len(page_ids) == 1

    async def test_ingest_handles_empty_report(
        self,
        vault,
        ingester,
    ):
        """Empty inventions list returns empty page_ids list."""
        page_ids = await ingester.ingest_invention_report(
            vault_id=vault.vault_id,
            run_id="genesis-008",
            report=MOCK_EMPTY_REPORT,
        )
        assert page_ids == []

    async def test_ingest_multiple_inventions(
        self,
        vault,
        ingester,
        sqlite_db,
    ):
        """Report with 2 inventions creates 2 pages."""
        page_ids = await ingester.ingest_invention_report(
            vault_id=vault.vault_id,
            run_id="genesis-009",
            report=MOCK_MULTI_INVENTION_REPORT,
        )
        assert len(page_ids) == 2

        # Verify both pages exist
        for pid in page_ids:
            cursor = await sqlite_db.execute(
                "SELECT page_type FROM fb_pages WHERE page_id = ?",
                (str(pid),),
            )
            row = await cursor.fetchone()
            assert row is not None
            assert row["page_type"] == PageType.INVENTION.value

        # Verify two InventionPageMeta records
        cursor = await sqlite_db.execute(
            "SELECT COUNT(*) as cnt FROM fb_invention_page_meta WHERE vault_id = ?",
            (str(vault.vault_id),),
        )
        row = await cursor.fetchone()
        assert row["cnt"] == 2
