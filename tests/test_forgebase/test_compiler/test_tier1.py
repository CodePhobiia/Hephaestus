"""Tests for Tier 1 SourceCompiler — per-source extraction orchestrator."""

from __future__ import annotations

from pathlib import Path

import aiosqlite
import pytest

from hephaestus.forgebase.compiler.tier1 import SourceCompiler
from hephaestus.forgebase.domain.enums import (
    BranchPurpose,
    CandidateStatus,
    ClaimStatus,
    DirtyTargetKind,
    PageType,
    SourceFormat,
    SupportType,
)
from hephaestus.forgebase.domain.values import Version
from hephaestus.forgebase.service.branch_service import BranchService
from hephaestus.forgebase.service.ingest_service import IngestService
from hephaestus.forgebase.service.vault_service import VaultService
from hephaestus.forgebase.store.blobs.memory import InMemoryContentStore
from hephaestus.forgebase.store.sqlite.schema import initialize_schema
from hephaestus.forgebase.store.sqlite.uow import SqliteUnitOfWork

# -----------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------


@pytest.fixture
async def sqlite_db(tmp_path: Path):
    """File-backed SQLite database with WAL mode for realistic testing."""
    db_path = tmp_path / "forgebase_tier1_test.db"
    db = await aiosqlite.connect(str(db_path))
    db.row_factory = aiosqlite.Row
    await initialize_schema(db)
    yield db
    await db.close()


@pytest.fixture
def content_store() -> InMemoryContentStore:
    return InMemoryContentStore()


@pytest.fixture
def uow_factory(sqlite_db, content_store, clock, id_gen):
    """Factory that returns a fresh SqliteUnitOfWork each time."""

    def _factory() -> SqliteUnitOfWork:
        return SqliteUnitOfWork(
            db=sqlite_db,
            content=content_store,
            clock=clock,
            id_generator=id_gen,
        )

    return _factory


# -----------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------

SAMPLE_SOURCE_TEXT = """\
# Neural Network Pruning

Structured pruning removes entire neurons or channels from deep neural networks,
reducing computational cost by 40-60% with minimal accuracy loss.

## Methods

Channel pruning uses L1-norm criteria to identify and remove low-importance filters.

## Results

Experiments on ResNet-50 show 2.3x speedup with less than 1% accuracy drop.

## Limitations

Pruning effectiveness varies significantly across architectures.
"""


async def _setup_vault_and_source(uow_factory, actor):
    """Create a vault, ingest a source, and normalize it. Returns (vault, source, norm_version)."""
    vault_svc = VaultService(uow_factory=uow_factory, default_actor=actor)
    vault = await vault_svc.create_vault(name="TestVault", description="Test vault for Tier 1")

    ingest_svc = IngestService(uow_factory=uow_factory, default_actor=actor)

    source, v1 = await ingest_svc.ingest_source(
        vault_id=vault.vault_id,
        raw_content=SAMPLE_SOURCE_TEXT.encode("utf-8"),
        format=SourceFormat.MARKDOWN,
        title="Neural Network Pruning",
        authors=["Alice"],
    )

    v2 = await ingest_svc.normalize_source(
        source_id=source.source_id,
        normalized_content=SAMPLE_SOURCE_TEXT.encode("utf-8"),
        expected_version=Version(1),
    )

    return vault, source, v2


async def _setup_vault_and_source_on_branch(uow_factory, actor):
    """Create a vault, workbook, ingest a source on branch, and normalize. Returns (vault, workbook, source, norm_version)."""
    vault_svc = VaultService(uow_factory=uow_factory, default_actor=actor)
    vault = await vault_svc.create_vault(name="BranchVault", description="Test")

    branch_svc = BranchService(uow_factory=uow_factory, default_actor=actor)
    workbook = await branch_svc.create_workbook(
        vault_id=vault.vault_id,
        name="research-branch",
        purpose=BranchPurpose.RESEARCH,
    )

    ingest_svc = IngestService(uow_factory=uow_factory, default_actor=actor)

    source, v1 = await ingest_svc.ingest_source(
        vault_id=vault.vault_id,
        raw_content=SAMPLE_SOURCE_TEXT.encode("utf-8"),
        format=SourceFormat.MARKDOWN,
        title="Pruning on Branch",
        authors=["Bob"],
        workbook_id=workbook.workbook_id,
    )

    v2 = await ingest_svc.normalize_source(
        source_id=source.source_id,
        normalized_content=SAMPLE_SOURCE_TEXT.encode("utf-8"),
        expected_version=Version(1),
        workbook_id=workbook.workbook_id,
    )

    return vault, workbook, source, v2


# -----------------------------------------------------------------
# Tests
# -----------------------------------------------------------------


@pytest.mark.asyncio
class TestSourceCompiler:
    """Tier 1 SourceCompiler integration tests."""

    async def test_compile_source_creates_source_card_page(
        self,
        uow_factory,
        actor,
        mock_backend,
        sqlite_db,
        content_store,
    ):
        """Verify page created with type SOURCE_CARD, correct page_key, content includes summary."""
        vault, source, norm_ver = await _setup_vault_and_source(uow_factory, actor)

        compiler = SourceCompiler(
            uow_factory=uow_factory,
            backend=mock_backend,
            default_actor=actor,
        )

        manifest = await compiler.compile_source(
            source_id=source.source_id,
            source_version=norm_ver.version,
            vault_id=vault.vault_id,
        )

        # Query the database for the page
        source_slug = str(source.source_id).replace("_", "-").lower()
        expected_key = f"source-cards/{source_slug}"

        cursor = await sqlite_db.execute(
            "SELECT * FROM fb_pages WHERE page_key = ?",
            (expected_key,),
        )
        row = await cursor.fetchone()
        assert row is not None, f"No page found with page_key={expected_key}"
        assert row["page_type"] == PageType.SOURCE_CARD.value

        # Verify content includes summary
        page_id = row["page_id"]
        cursor = await sqlite_db.execute(
            "SELECT * FROM fb_page_versions WHERE page_id = ? ORDER BY version DESC LIMIT 1",
            (page_id,),
        )
        ver_row = await cursor.fetchone()
        assert ver_row is not None

        # Read content via blob store
        from hephaestus.forgebase.domain.values import BlobRef, ContentHash

        blob_ref = BlobRef(
            content_hash=ContentHash(sha256=ver_row["content_hash"]),
            size_bytes=0,
            mime_type="text/markdown",
        )
        content_bytes = await content_store.read(blob_ref)
        content_text = content_bytes.decode("utf-8")

        assert "Summary" in content_text
        assert "Source: Neural Network Pruning" in content_text

    async def test_compile_source_creates_claims(
        self,
        uow_factory,
        actor,
        mock_backend,
        sqlite_db,
    ):
        """Verify claims created with status=SUPPORTED, support_type=DIRECT."""
        vault, source, norm_ver = await _setup_vault_and_source(uow_factory, actor)

        compiler = SourceCompiler(
            uow_factory=uow_factory,
            backend=mock_backend,
            default_actor=actor,
        )

        manifest = await compiler.compile_source(
            source_id=source.source_id,
            source_version=norm_ver.version,
            vault_id=vault.vault_id,
        )

        assert manifest.claim_count > 0

        # Query claims from DB
        cursor = await sqlite_db.execute(
            "SELECT cv.* FROM fb_claim_versions cv "
            "JOIN fb_claims c ON cv.claim_id = c.claim_id "
            "WHERE c.vault_id = ?",
            (str(vault.vault_id),),
        )
        rows = await cursor.fetchall()
        assert len(rows) == manifest.claim_count

        for row in rows:
            assert row["status"] == ClaimStatus.SUPPORTED.value
            assert row["support_type"] == SupportType.DIRECT.value

    async def test_compile_source_creates_claim_supports(
        self,
        uow_factory,
        actor,
        mock_backend,
        sqlite_db,
    ):
        """Verify ClaimSupport records link claims to source."""
        vault, source, norm_ver = await _setup_vault_and_source(uow_factory, actor)

        compiler = SourceCompiler(
            uow_factory=uow_factory,
            backend=mock_backend,
            default_actor=actor,
        )

        manifest = await compiler.compile_source(
            source_id=source.source_id,
            source_version=norm_ver.version,
            vault_id=vault.vault_id,
        )

        # Query claim supports from DB
        cursor = await sqlite_db.execute(
            "SELECT cs.* FROM fb_claim_supports cs WHERE cs.source_id = ?",
            (str(source.source_id),),
        )
        rows = await cursor.fetchall()
        assert len(rows) == manifest.claim_count

        for row in rows:
            assert row["source_id"] == str(source.source_id)
            assert row["source_segment"] is not None
            assert row["strength"] > 0

    async def test_compile_source_creates_concept_candidates(
        self,
        uow_factory,
        actor,
        mock_backend,
        sqlite_db,
    ):
        """Verify ConceptCandidate records with status=ACTIVE."""
        vault, source, norm_ver = await _setup_vault_and_source(uow_factory, actor)

        compiler = SourceCompiler(
            uow_factory=uow_factory,
            backend=mock_backend,
            default_actor=actor,
        )

        manifest = await compiler.compile_source(
            source_id=source.source_id,
            source_version=norm_ver.version,
            vault_id=vault.vault_id,
        )

        assert manifest.concept_count > 0

        # Query candidates from DB
        cursor = await sqlite_db.execute(
            "SELECT * FROM fb_concept_candidates WHERE vault_id = ?",
            (str(vault.vault_id),),
        )
        rows = await cursor.fetchall()
        assert len(rows) == manifest.concept_count

        for row in rows:
            assert row["status"] == CandidateStatus.ACTIVE.value
            assert row["source_id"] == str(source.source_id)
            assert row["compiler_policy_version"] == "1.0.0"
            # normalized_name should be lowercase stripped
            assert row["normalized_name"] == row["name"].lower().strip()

    async def test_compile_source_creates_candidate_evidence(
        self,
        uow_factory,
        actor,
        mock_backend,
        sqlite_db,
    ):
        """Verify evidence records exist for concept candidates."""
        vault, source, norm_ver = await _setup_vault_and_source(uow_factory, actor)

        compiler = SourceCompiler(
            uow_factory=uow_factory,
            backend=mock_backend,
            default_actor=actor,
        )

        await compiler.compile_source(
            source_id=source.source_id,
            source_version=norm_ver.version,
            vault_id=vault.vault_id,
        )

        # Get all candidate IDs
        cursor = await sqlite_db.execute(
            "SELECT candidate_id FROM fb_concept_candidates WHERE vault_id = ?",
            (str(vault.vault_id),),
        )
        candidate_rows = await cursor.fetchall()
        assert len(candidate_rows) > 0

        # For each candidate, verify evidence exists
        for cand_row in candidate_rows:
            cursor = await sqlite_db.execute(
                "SELECT * FROM fb_candidate_evidence WHERE candidate_id = ?",
                (cand_row["candidate_id"],),
            )
            evidence_rows = await cursor.fetchall()
            assert len(evidence_rows) > 0, (
                f"No evidence found for candidate {cand_row['candidate_id']}"
            )
            for ev in evidence_rows:
                assert ev["role"] == "USAGE"

    async def test_compile_source_creates_dirty_markers(
        self,
        uow_factory,
        actor,
        mock_backend,
        sqlite_db,
    ):
        """Verify dirty markers upserted for concepts."""
        vault, source, norm_ver = await _setup_vault_and_source(uow_factory, actor)

        compiler = SourceCompiler(
            uow_factory=uow_factory,
            backend=mock_backend,
            default_actor=actor,
        )

        manifest = await compiler.compile_source(
            source_id=source.source_id,
            source_version=norm_ver.version,
            vault_id=vault.vault_id,
        )

        # Query dirty markers from DB
        cursor = await sqlite_db.execute(
            "SELECT * FROM fb_synthesis_dirty_markers WHERE vault_id = ? AND consumed_by_job IS NULL",
            (str(vault.vault_id),),
        )
        rows = await cursor.fetchall()

        # Should have at least one dirty marker per concept candidate
        assert len(rows) >= manifest.concept_count

        for row in rows:
            assert row["target_kind"] == DirtyTargetKind.CONCEPT.value
            assert row["times_dirtied"] >= 1

    async def test_compile_source_writes_manifest(
        self,
        uow_factory,
        actor,
        mock_backend,
        sqlite_db,
    ):
        """Verify SourceCompileManifest persisted."""
        vault, source, norm_ver = await _setup_vault_and_source(uow_factory, actor)

        compiler = SourceCompiler(
            uow_factory=uow_factory,
            backend=mock_backend,
            default_actor=actor,
        )

        manifest = await compiler.compile_source(
            source_id=source.source_id,
            source_version=norm_ver.version,
            vault_id=vault.vault_id,
        )

        # Query manifest from DB
        cursor = await sqlite_db.execute(
            "SELECT * FROM fb_source_compile_manifests WHERE manifest_id = ?",
            (str(manifest.manifest_id),),
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row["source_id"] == str(source.source_id)
        assert row["source_version"] == norm_ver.version.number
        assert row["compiler_policy_version"] == "1.0.0"
        assert row["claim_count"] == manifest.claim_count
        assert row["concept_count"] == manifest.concept_count

    async def test_compile_source_emits_events(
        self,
        uow_factory,
        actor,
        mock_backend,
        sqlite_db,
    ):
        """Verify domain events in outbox."""
        vault, source, norm_ver = await _setup_vault_and_source(uow_factory, actor)

        compiler = SourceCompiler(
            uow_factory=uow_factory,
            backend=mock_backend,
            default_actor=actor,
        )

        await compiler.compile_source(
            source_id=source.source_id,
            source_version=norm_ver.version,
            vault_id=vault.vault_id,
        )

        cursor = await sqlite_db.execute(
            "SELECT * FROM fb_domain_events WHERE event_type = ? AND aggregate_id = ?",
            ("compile.completed", str(source.source_id)),
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row["event_type"] == "compile.completed"

    async def test_compile_source_noop_on_unchanged_content(
        self,
        uow_factory,
        actor,
        mock_backend,
        sqlite_db,
    ):
        """Compile same source twice, second time should not create new page version."""
        vault, source, norm_ver = await _setup_vault_and_source(uow_factory, actor)

        compiler = SourceCompiler(
            uow_factory=uow_factory,
            backend=mock_backend,
            default_actor=actor,
        )

        # First compile
        await compiler.compile_source(
            source_id=source.source_id,
            source_version=norm_ver.version,
            vault_id=vault.vault_id,
        )

        # Count page versions after first compile
        source_slug = str(source.source_id).replace("_", "-").lower()
        expected_key = f"source-cards/{source_slug}"

        cursor = await sqlite_db.execute(
            "SELECT page_id FROM fb_pages WHERE page_key = ?",
            (expected_key,),
        )
        page_row = await cursor.fetchone()
        assert page_row is not None
        page_id = page_row["page_id"]

        cursor = await sqlite_db.execute(
            "SELECT COUNT(*) as cnt FROM fb_page_versions WHERE page_id = ?",
            (page_id,),
        )
        count_after_first = (await cursor.fetchone())["cnt"]

        # Second compile (same source, same content, same mock results)
        await compiler.compile_source(
            source_id=source.source_id,
            source_version=norm_ver.version,
            vault_id=vault.vault_id,
        )

        # Page versions should be the same (no-op check)
        cursor = await sqlite_db.execute(
            "SELECT COUNT(*) as cnt FROM fb_page_versions WHERE page_id = ?",
            (page_id,),
        )
        count_after_second = (await cursor.fetchone())["cnt"]

        assert count_after_second == count_after_first, (
            f"Expected no-op: page versions should be {count_after_first}, "
            f"but got {count_after_second}"
        )

    async def test_compile_source_on_workbook_branch(
        self,
        uow_factory,
        actor,
        mock_backend,
        sqlite_db,
    ):
        """Compile with workbook_id, verify branch heads set."""
        vault, workbook, source, norm_ver = await _setup_vault_and_source_on_branch(
            uow_factory,
            actor,
        )

        compiler = SourceCompiler(
            uow_factory=uow_factory,
            backend=mock_backend,
            default_actor=actor,
        )

        manifest = await compiler.compile_source(
            source_id=source.source_id,
            source_version=norm_ver.version,
            vault_id=vault.vault_id,
            workbook_id=workbook.workbook_id,
        )

        # Verify branch page head was set (not canonical)
        cursor = await sqlite_db.execute(
            "SELECT * FROM fb_branch_page_heads WHERE workbook_id = ?",
            (str(workbook.workbook_id),),
        )
        page_heads = await cursor.fetchall()
        assert len(page_heads) >= 1, "No branch page heads set"

        # Verify branch claim heads were set
        cursor = await sqlite_db.execute(
            "SELECT * FROM fb_branch_claim_heads WHERE workbook_id = ?",
            (str(workbook.workbook_id),),
        )
        claim_heads = await cursor.fetchall()
        assert len(claim_heads) == manifest.claim_count

        # Verify branch link heads were set
        cursor = await sqlite_db.execute(
            "SELECT * FROM fb_branch_link_heads WHERE workbook_id = ?",
            (str(workbook.workbook_id),),
        )
        link_heads = await cursor.fetchall()
        assert len(link_heads) >= 1

        # Verify NO canonical heads for pages created by this compile
        # (The vault and source have canonical heads from setup, but page/claim/link should not)
        for ph in page_heads:
            cursor = await sqlite_db.execute(
                "SELECT * FROM fb_canonical_heads WHERE entity_id = ?",
                (ph["page_id"],),
            )
            canonical_row = await cursor.fetchone()
            assert canonical_row is None, (
                f"Page {ph['page_id']} has canonical head but should only have branch head"
            )
