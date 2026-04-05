"""Tests for PantheonIngester — structured ingestion of Pantheon deliberation.

Uses a real SQLite backend (no mocks) to exercise the full service stack.

Key scenarios:
  1. UNANIMOUS_CONSENSUS → invention state REVIEWED
  2. FAIL_CLOSED_REJECTION → invention state REJECTED
  3. Canon mandatory_constraints → HYPOTHESIS claims with CONSTRAINED_BY links
  4. Open objections → CHALLENGED_BY links to invention page
  5. Verdict recorded on InventionPageMeta
  6. Works without invention_page_id
  7. Handles minimal/sparse state
  8. Dossier stored as ingested source
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
from hephaestus.forgebase.domain.models import InventionPageMeta
from hephaestus.forgebase.integration.pantheon_ingester import PantheonIngester
from hephaestus.forgebase.service.claim_service import ClaimService
from hephaestus.forgebase.service.link_service import LinkService
from hephaestus.forgebase.service.page_service import PageService

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def claim_service(uow_factory, actor) -> ClaimService:
    return ClaimService(uow_factory=uow_factory, default_actor=actor)


@pytest.fixture
def link_service(uow_factory, actor) -> LinkService:
    return LinkService(uow_factory=uow_factory, default_actor=actor)


@pytest.fixture
def page_service(uow_factory, actor) -> PageService:
    return PageService(uow_factory=uow_factory, default_actor=actor)


@pytest.fixture
def pantheon_ingester(
    uow_factory,
    claim_service,
    link_service,
    run_integration_service,
    ingest_service,
    actor,
) -> PantheonIngester:
    return PantheonIngester(
        uow_factory=uow_factory,
        claim_service=claim_service,
        link_service=link_service,
        run_integration_service=run_integration_service,
        ingest_service=ingest_service,
        default_actor=actor,
    )


@pytest.fixture
async def invention_page(vault, page_service, uow_factory, clock):
    """Pre-created INVENTION page with InventionPageMeta in PROPOSED state."""
    page, _ = await page_service.create_page(
        vault_id=vault.vault_id,
        page_key="invention:test-mechanism",
        page_type=PageType.INVENTION,
        title="Test Invention: Decentralized Optimization",
        content=b"# Decentralized Optimization\n\nMechanism description...",
    )
    # Create the InventionPageMeta
    uow = uow_factory()
    async with uow:
        now = clock.now()
        meta = InventionPageMeta(
            page_id=page.page_id,
            vault_id=vault.vault_id,
            invention_state=InventionEpistemicState.PROPOSED,
            run_id="genesis-test-001",
            run_type="genesis",
            models_used=["test-model"],
            created_at=now,
            updated_at=now,
        )
        await uow.invention_meta.create(meta)
        await uow.commit()
    return page


# ---------------------------------------------------------------------------
# Mock state
# ---------------------------------------------------------------------------

MOCK_PANTHEON_STATE = {
    "final_verdict": "UNANIMOUS_CONSENSUS",
    "outcome_tier": "UNANIMOUS_CONSENSUS",
    "consensus_achieved": True,
    "canon": {
        "mandatory_constraints": ["Must handle 10K req/s", "Sub-ms latency"],
        "anti_goals": ["No central coordinator"],
        "structural_form": "Decentralized optimization",
        "confidence": 0.9,
    },
    "dossier": {
        "competitor_patterns": ["Round-robin", "Least-connections"],
        "ecosystem_constraints": ["Must work with existing HTTP stack"],
    },
    "objection_ledger": [
        {
            "statement": "Path memory assumption is invalid for HTTP",
            "status": "OPEN",
            "severity": "REPAIRABLE",
        },
    ],
}


MOCK_FAIL_CLOSED_STATE = {
    "final_verdict": "FAIL_CLOSED_REJECTION",
    "outcome_tier": "FAIL_CLOSED_REJECTION",
    "consensus_achieved": False,
    "objection_ledger": [
        {
            "statement": "Fundamental flaw in theoretical basis",
            "status": "OPEN",
            "severity": "FATAL",
        },
        {
            "statement": "Contradicts established results",
            "status": "OPEN",
            "severity": "FATAL",
        },
    ],
}


MOCK_QUALIFIED_STATE = {
    "final_verdict": "QUALIFIED_CONSENSUS",
    "outcome_tier": "QUALIFIED_CONSENSUS",
    "consensus_achieved": True,
    "objection_ledger": [
        {
            "statement": "Minor concern resolved during deliberation",
            "status": "RESOLVED",
            "severity": "COSMETIC",
        },
    ],
}


MOCK_MINIMAL_STATE = {
    "final_verdict": "UNKNOWN_OUTCOME",
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestPantheonIngester:
    async def test_ingest_updates_invention_state_reviewed(
        self,
        vault,
        invention_page,
        pantheon_ingester,
        uow_factory,
    ):
        """UNANIMOUS_CONSENSUS verdict updates invention state to REVIEWED."""
        await pantheon_ingester.ingest_pantheon_state(
            vault_id=vault.vault_id,
            run_id="pantheon-001",
            state=MOCK_PANTHEON_STATE,
            invention_page_id=invention_page.page_id,
        )

        uow = uow_factory()
        async with uow:
            meta = await uow.invention_meta.get(invention_page.page_id)
            assert meta is not None
            assert meta.invention_state == InventionEpistemicState.REVIEWED

    async def test_ingest_fail_closed_rejects(
        self,
        vault,
        invention_page,
        pantheon_ingester,
        uow_factory,
    ):
        """FAIL_CLOSED_REJECTION verdict updates invention state to REJECTED."""
        await pantheon_ingester.ingest_pantheon_state(
            vault_id=vault.vault_id,
            run_id="pantheon-002",
            state=MOCK_FAIL_CLOSED_STATE,
            invention_page_id=invention_page.page_id,
        )

        uow = uow_factory()
        async with uow:
            meta = await uow.invention_meta.get(invention_page.page_id)
            assert meta is not None
            assert meta.invention_state == InventionEpistemicState.REJECTED

    async def test_ingest_creates_constraint_claims(
        self,
        vault,
        invention_page,
        pantheon_ingester,
        sqlite_db,
    ):
        """Canon mandatory_constraints produce HYPOTHESIS claims with GENERATED support."""
        await pantheon_ingester.ingest_pantheon_state(
            vault_id=vault.vault_id,
            run_id="pantheon-003",
            state=MOCK_PANTHEON_STATE,
            invention_page_id=invention_page.page_id,
        )

        # Query claims created for this vault
        cursor = await sqlite_db.execute(
            """
            SELECT cv.statement, cv.status, cv.support_type
            FROM fb_claim_versions cv
            JOIN fb_claims c ON c.claim_id = cv.claim_id
            WHERE c.vault_id = ?
            AND cv.support_type = ?
            AND cv.status = ?
            ORDER BY cv.statement
            """,
            (str(vault.vault_id), SupportType.GENERATED.value, ClaimStatus.HYPOTHESIS.value),
        )
        rows = await cursor.fetchall()
        statements = [row["statement"] for row in rows]

        # The two mandatory constraints should be present
        assert "Must handle 10K req/s" in statements
        assert "Sub-ms latency" in statements

    async def test_ingest_creates_constrained_by_links(
        self,
        vault,
        invention_page,
        pantheon_ingester,
        sqlite_db,
    ):
        """CONSTRAINED_BY links are created from invention page to constraint claims."""
        await pantheon_ingester.ingest_pantheon_state(
            vault_id=vault.vault_id,
            run_id="pantheon-004",
            state=MOCK_PANTHEON_STATE,
            invention_page_id=invention_page.page_id,
        )

        # Query CONSTRAINED_BY links
        cursor = await sqlite_db.execute(
            """
            SELECT lv.source_entity, lv.target_entity
            FROM fb_link_versions lv
            JOIN fb_links l ON l.link_id = lv.link_id
            WHERE l.vault_id = ?
            AND l.kind = ?
            """,
            (str(vault.vault_id), LinkKind.CONSTRAINED_BY.value),
        )
        rows = await cursor.fetchall()
        assert len(rows) >= 2  # At least two constraints

        # All CONSTRAINED_BY links should have the invention page as source
        for row in rows:
            assert row["source_entity"] == str(invention_page.page_id)

    async def test_ingest_marks_contested_from_objections(
        self,
        vault,
        invention_page,
        pantheon_ingester,
        sqlite_db,
    ):
        """Open objections create HYPOTHESIS claims and CHALLENGED_BY links."""
        await pantheon_ingester.ingest_pantheon_state(
            vault_id=vault.vault_id,
            run_id="pantheon-005",
            state=MOCK_PANTHEON_STATE,
            invention_page_id=invention_page.page_id,
        )

        # Check that an objection claim was created
        cursor = await sqlite_db.execute(
            """
            SELECT cv.statement
            FROM fb_claim_versions cv
            JOIN fb_claims c ON c.claim_id = cv.claim_id
            WHERE c.vault_id = ?
            AND cv.statement LIKE '%Path memory%'
            """,
            (str(vault.vault_id),),
        )
        rows = await cursor.fetchall()
        assert len(rows) >= 1

        # Check CHALLENGED_BY links exist
        cursor = await sqlite_db.execute(
            """
            SELECT COUNT(*) as cnt
            FROM fb_links
            WHERE vault_id = ?
            AND kind = ?
            """,
            (str(vault.vault_id), LinkKind.CHALLENGED_BY.value),
        )
        row = await cursor.fetchone()
        assert row["cnt"] >= 1

    async def test_ingest_records_verdict_on_meta(
        self,
        vault,
        invention_page,
        pantheon_ingester,
        uow_factory,
    ):
        """Pantheon verdict, outcome_tier, and consensus are recorded on meta."""
        await pantheon_ingester.ingest_pantheon_state(
            vault_id=vault.vault_id,
            run_id="pantheon-006",
            state=MOCK_PANTHEON_STATE,
            invention_page_id=invention_page.page_id,
        )

        uow = uow_factory()
        async with uow:
            meta = await uow.invention_meta.get(invention_page.page_id)
            assert meta is not None
            assert meta.pantheon_verdict == "UNANIMOUS_CONSENSUS"
            assert meta.pantheon_outcome_tier == "UNANIMOUS_CONSENSUS"
            assert meta.pantheon_consensus is True
            assert meta.objection_count_open == 1
            assert meta.objection_count_resolved == 0

    async def test_ingest_handles_no_invention_page(
        self,
        vault,
        pantheon_ingester,
        sqlite_db,
    ):
        """Ingestion works without an invention_page_id — standalone Pantheon run."""
        # Should not raise, even without an invention page
        await pantheon_ingester.ingest_pantheon_state(
            vault_id=vault.vault_id,
            run_id="pantheon-standalone",
            state=MOCK_PANTHEON_STATE,
            invention_page_id=None,
        )

        # Run ref should be created
        cursor = await sqlite_db.execute(
            "SELECT sync_status FROM fb_run_refs WHERE run_id = ?",
            ("pantheon-standalone",),
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row["sync_status"] == "synced"

        # Canon constraint claims should still be created (they're vault knowledge)
        cursor = await sqlite_db.execute(
            """
            SELECT COUNT(*) as cnt
            FROM fb_claim_versions cv
            JOIN fb_claims c ON c.claim_id = cv.claim_id
            WHERE c.vault_id = ?
            AND cv.support_type = ?
            """,
            (str(vault.vault_id), SupportType.GENERATED.value),
        )
        row = await cursor.fetchone()
        # At least the 2 mandatory constraints + anti_goal + 1 objection
        assert row["cnt"] >= 2

    async def test_ingest_handles_minimal_state(
        self,
        vault,
        invention_page,
        pantheon_ingester,
        sqlite_db,
    ):
        """State with missing fields should not crash."""
        await pantheon_ingester.ingest_pantheon_state(
            vault_id=vault.vault_id,
            run_id="pantheon-minimal",
            state=MOCK_MINIMAL_STATE,
            invention_page_id=invention_page.page_id,
        )

        # Run ref should be created and synced
        cursor = await sqlite_db.execute(
            "SELECT sync_status FROM fb_run_refs WHERE run_id = ?",
            ("pantheon-minimal",),
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row["sync_status"] == "synced"

        # Meta should NOT be updated to REVIEWED because verdict is unknown
        uow_fac = lambda: None  # not needed, we'll use sqlite_db directly
        cursor = await sqlite_db.execute(
            """
            SELECT invention_state FROM fb_invention_page_meta
            WHERE page_id = ?
            """,
            (str(invention_page.page_id),),
        )
        row = await cursor.fetchone()
        # With UNKNOWN_OUTCOME, state should remain PROPOSED
        assert row["invention_state"] == InventionEpistemicState.PROPOSED.value

    async def test_ingest_qualified_consensus_reviews(
        self,
        vault,
        invention_page,
        pantheon_ingester,
        uow_factory,
    ):
        """QUALIFIED_CONSENSUS also maps to REVIEWED state."""
        await pantheon_ingester.ingest_pantheon_state(
            vault_id=vault.vault_id,
            run_id="pantheon-qualified",
            state=MOCK_QUALIFIED_STATE,
            invention_page_id=invention_page.page_id,
        )

        uow = uow_factory()
        async with uow:
            meta = await uow.invention_meta.get(invention_page.page_id)
            assert meta is not None
            assert meta.invention_state == InventionEpistemicState.REVIEWED

    async def test_ingest_stores_dossier_as_source(
        self,
        vault,
        pantheon_ingester,
        sqlite_db,
    ):
        """HermesDossier is stored as an ingested source for later compilation."""
        await pantheon_ingester.ingest_pantheon_state(
            vault_id=vault.vault_id,
            run_id="pantheon-dossier-test",
            state=MOCK_PANTHEON_STATE,
            invention_page_id=None,
        )

        # Check that a dossier source was ingested
        cursor = await sqlite_db.execute(
            """
            SELECT sv.title
            FROM fb_source_versions sv
            JOIN fb_sources s ON s.source_id = sv.source_id
            WHERE s.vault_id = ?
            AND sv.title LIKE '%dossier%'
            """,
            (str(vault.vault_id),),
        )
        rows = await cursor.fetchall()
        assert len(rows) >= 1
