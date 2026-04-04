"""Tests for Tier 2 VaultSynthesizer — vault-wide synthesis orchestrator."""
from __future__ import annotations

from pathlib import Path

import aiosqlite
import pytest

from hephaestus.forgebase.compiler.policy import DEFAULT_POLICY, SynthesisPolicy
from hephaestus.forgebase.compiler.tier1 import SourceCompiler
from hephaestus.forgebase.compiler.tier2 import VaultSynthesizer
from hephaestus.forgebase.domain.enums import (
    BranchPurpose,
    CandidateStatus,
    ClaimStatus,
    DirtyTargetKind,
    PageType,
    SourceFormat,
    SupportType,
)
from hephaestus.forgebase.domain.values import ActorRef, EntityId, Version
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
    db_path = tmp_path / "forgebase_tier2_test.db"
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
# Sample source texts — different content so they produce different claims
# -----------------------------------------------------------------

SOURCE_TEXT_1 = """\
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

SOURCE_TEXT_2 = """\
# Advanced Pruning Techniques

Unstructured pruning creates sparse weight matrices in neural networks,
achieving higher compression ratios than structured approaches.

## Methods

Magnitude pruning sets small weights to zero after training.

## Results

On BERT models, unstructured pruning achieves 90% sparsity with 2% accuracy loss.

## Limitations

Hardware acceleration for sparse operations remains limited.
"""


# -----------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------

async def _setup_vault_two_sources_compiled(uow_factory, actor, mock_backend):
    """Create vault, ingest + normalize 2 sources, compile both with Tier 1.

    Returns (vault, source1, source2, manifest1, manifest2).
    """
    vault_svc = VaultService(uow_factory=uow_factory, default_actor=actor)
    vault = await vault_svc.create_vault(
        name="TestVault", description="Test vault for Tier 2",
    )

    ingest_svc = IngestService(uow_factory=uow_factory, default_actor=actor)

    # Source 1
    source1, v1_1 = await ingest_svc.ingest_source(
        vault_id=vault.vault_id,
        raw_content=SOURCE_TEXT_1.encode("utf-8"),
        format=SourceFormat.MARKDOWN,
        title="Neural Network Pruning",
        authors=["Alice"],
    )
    v1_norm = await ingest_svc.normalize_source(
        source_id=source1.source_id,
        normalized_content=SOURCE_TEXT_1.encode("utf-8"),
        expected_version=Version(1),
    )

    # Source 2
    source2, v2_1 = await ingest_svc.ingest_source(
        vault_id=vault.vault_id,
        raw_content=SOURCE_TEXT_2.encode("utf-8"),
        format=SourceFormat.MARKDOWN,
        title="Advanced Pruning Techniques",
        authors=["Bob"],
    )
    v2_norm = await ingest_svc.normalize_source(
        source_id=source2.source_id,
        normalized_content=SOURCE_TEXT_2.encode("utf-8"),
        expected_version=Version(1),
    )

    # Compile both sources with Tier 1
    compiler = SourceCompiler(
        uow_factory=uow_factory,
        backend=mock_backend,
        default_actor=actor,
    )

    manifest1 = await compiler.compile_source(
        source_id=source1.source_id,
        source_version=v1_norm.version,
        vault_id=vault.vault_id,
    )

    manifest2 = await compiler.compile_source(
        source_id=source2.source_id,
        source_version=v2_norm.version,
        vault_id=vault.vault_id,
    )

    return vault, source1, source2, manifest1, manifest2


async def _setup_vault_two_sources_on_branch(uow_factory, actor, mock_backend):
    """Create vault + workbook, ingest + normalize 2 sources on branch, compile both.

    Returns (vault, workbook, source1, source2, manifest1, manifest2).
    """
    vault_svc = VaultService(uow_factory=uow_factory, default_actor=actor)
    vault = await vault_svc.create_vault(
        name="BranchVault", description="Test vault for Tier 2 on branch",
    )

    branch_svc = BranchService(uow_factory=uow_factory, default_actor=actor)
    workbook = await branch_svc.create_workbook(
        vault_id=vault.vault_id,
        name="research-branch",
        purpose=BranchPurpose.RESEARCH,
    )

    ingest_svc = IngestService(uow_factory=uow_factory, default_actor=actor)

    # Source 1
    source1, v1_1 = await ingest_svc.ingest_source(
        vault_id=vault.vault_id,
        raw_content=SOURCE_TEXT_1.encode("utf-8"),
        format=SourceFormat.MARKDOWN,
        title="Neural Network Pruning",
        authors=["Alice"],
        workbook_id=workbook.workbook_id,
    )
    v1_norm = await ingest_svc.normalize_source(
        source_id=source1.source_id,
        normalized_content=SOURCE_TEXT_1.encode("utf-8"),
        expected_version=Version(1),
        workbook_id=workbook.workbook_id,
    )

    # Source 2
    source2, v2_1 = await ingest_svc.ingest_source(
        vault_id=vault.vault_id,
        raw_content=SOURCE_TEXT_2.encode("utf-8"),
        format=SourceFormat.MARKDOWN,
        title="Advanced Pruning Techniques",
        authors=["Bob"],
        workbook_id=workbook.workbook_id,
    )
    v2_norm = await ingest_svc.normalize_source(
        source_id=source2.source_id,
        normalized_content=SOURCE_TEXT_2.encode("utf-8"),
        expected_version=Version(1),
        workbook_id=workbook.workbook_id,
    )

    # Compile both sources with Tier 1 on the branch
    compiler = SourceCompiler(
        uow_factory=uow_factory,
        backend=mock_backend,
        default_actor=actor,
    )

    manifest1 = await compiler.compile_source(
        source_id=source1.source_id,
        source_version=v1_norm.version,
        vault_id=vault.vault_id,
        workbook_id=workbook.workbook_id,
    )

    manifest2 = await compiler.compile_source(
        source_id=source2.source_id,
        source_version=v2_norm.version,
        vault_id=vault.vault_id,
        workbook_id=workbook.workbook_id,
    )

    return vault, workbook, source1, source2, manifest1, manifest2


# -----------------------------------------------------------------
# Tests
# -----------------------------------------------------------------


@pytest.mark.asyncio
class TestVaultSynthesizer:
    """Tier 2 VaultSynthesizer integration tests."""

    async def test_synthesize_creates_concept_pages(
        self, uow_factory, actor, mock_backend, sqlite_db,
    ):
        """Verify concept pages created from promoted candidates."""
        vault, src1, src2, m1, m2 = await _setup_vault_two_sources_compiled(
            uow_factory, actor, mock_backend,
        )

        synthesizer = VaultSynthesizer(
            uow_factory=uow_factory,
            backend=mock_backend,
            default_actor=actor,
        )

        manifest = await synthesizer.synthesize(vault_id=vault.vault_id)

        # Should have created concept pages
        cursor = await sqlite_db.execute(
            "SELECT * FROM fb_pages WHERE vault_id = ? AND page_type = ?",
            (str(vault.vault_id), PageType.CONCEPT.value),
        )
        concept_pages = await cursor.fetchall()
        assert len(concept_pages) >= 1, "No concept pages created"

        # Verify page_key follows pattern "concepts/{normalized_name}"
        for page_row in concept_pages:
            assert page_row["page_key"].startswith("concepts/"), (
                f"Unexpected page_key: {page_row['page_key']}"
            )

        # Verify page versions exist with content
        for page_row in concept_pages:
            cursor = await sqlite_db.execute(
                "SELECT * FROM fb_page_versions WHERE page_id = ? ORDER BY version DESC LIMIT 1",
                (page_row["page_id"],),
            )
            ver_row = await cursor.fetchone()
            assert ver_row is not None, f"No version for page {page_row['page_id']}"
            assert ver_row["title"] is not None
            assert ver_row["content_hash"] is not None

    async def test_synthesize_creates_synthesized_claims(
        self, uow_factory, actor, mock_backend, sqlite_db,
    ):
        """Verify claims with status=INFERRED, support_type=SYNTHESIZED."""
        vault, src1, src2, m1, m2 = await _setup_vault_two_sources_compiled(
            uow_factory, actor, mock_backend,
        )

        synthesizer = VaultSynthesizer(
            uow_factory=uow_factory,
            backend=mock_backend,
            default_actor=actor,
        )

        manifest = await synthesizer.synthesize(vault_id=vault.vault_id)

        # Get concept pages
        cursor = await sqlite_db.execute(
            "SELECT page_id FROM fb_pages WHERE vault_id = ? AND page_type = ?",
            (str(vault.vault_id), PageType.CONCEPT.value),
        )
        concept_page_ids = [r["page_id"] for r in await cursor.fetchall()]
        assert len(concept_page_ids) >= 1

        # Get claims for concept pages — they should be INFERRED / SYNTHESIZED
        for page_id in concept_page_ids:
            cursor = await sqlite_db.execute(
                "SELECT c.claim_id FROM fb_claims c WHERE c.page_id = ?",
                (page_id,),
            )
            claim_rows = await cursor.fetchall()
            assert len(claim_rows) >= 1, (
                f"No claims for concept page {page_id}"
            )

            for claim_row in claim_rows:
                cursor = await sqlite_db.execute(
                    "SELECT * FROM fb_claim_versions WHERE claim_id = ? ORDER BY version DESC LIMIT 1",
                    (claim_row["claim_id"],),
                )
                ver_row = await cursor.fetchone()
                assert ver_row is not None
                assert ver_row["status"] == ClaimStatus.INFERRED.value
                assert ver_row["support_type"] == SupportType.SYNTHESIZED.value

    async def test_synthesize_promotes_candidates(
        self, uow_factory, actor, mock_backend, sqlite_db,
    ):
        """Verify candidate status changed from ACTIVE to PROMOTED."""
        vault, src1, src2, m1, m2 = await _setup_vault_two_sources_compiled(
            uow_factory, actor, mock_backend,
        )

        # Verify candidates are ACTIVE before synthesis
        cursor = await sqlite_db.execute(
            "SELECT * FROM fb_concept_candidates WHERE vault_id = ? AND status = ?",
            (str(vault.vault_id), CandidateStatus.ACTIVE.value),
        )
        active_before = await cursor.fetchall()
        assert len(active_before) >= 2, (
            f"Expected at least 2 ACTIVE candidates, got {len(active_before)}"
        )

        synthesizer = VaultSynthesizer(
            uow_factory=uow_factory,
            backend=mock_backend,
            default_actor=actor,
        )

        manifest = await synthesizer.synthesize(vault_id=vault.vault_id)
        assert manifest.candidates_resolved > 0

        # After synthesis, promoted candidates should have status PROMOTED
        cursor = await sqlite_db.execute(
            "SELECT * FROM fb_concept_candidates WHERE vault_id = ? AND status = ?",
            (str(vault.vault_id), CandidateStatus.PROMOTED.value),
        )
        promoted = await cursor.fetchall()
        assert len(promoted) >= 2, (
            f"Expected promoted candidates, got {len(promoted)}"
        )

        # Promoted candidates should have resolved_page_id set
        for row in promoted:
            assert row["resolved_page_id"] is not None, (
                f"Candidate {row['candidate_id']} promoted but resolved_page_id is null"
            )

    async def test_synthesize_consumes_dirty_markers(
        self, uow_factory, actor, mock_backend, sqlite_db,
    ):
        """Verify markers have consumed_by_job set."""
        vault, src1, src2, m1, m2 = await _setup_vault_two_sources_compiled(
            uow_factory, actor, mock_backend,
        )

        # Verify dirty markers exist before synthesis
        cursor = await sqlite_db.execute(
            "SELECT * FROM fb_synthesis_dirty_markers WHERE vault_id = ? AND consumed_by_job IS NULL",
            (str(vault.vault_id),),
        )
        unconsumed_before = await cursor.fetchall()
        assert len(unconsumed_before) >= 1, "No dirty markers before synthesis"

        synthesizer = VaultSynthesizer(
            uow_factory=uow_factory,
            backend=mock_backend,
            default_actor=actor,
        )

        manifest = await synthesizer.synthesize(vault_id=vault.vault_id)

        # After synthesis, all dirty markers should be consumed
        cursor = await sqlite_db.execute(
            "SELECT * FROM fb_synthesis_dirty_markers WHERE vault_id = ? AND consumed_by_job IS NULL",
            (str(vault.vault_id),),
        )
        unconsumed_after = await cursor.fetchall()
        assert len(unconsumed_after) == 0, (
            f"Expected 0 unconsumed markers after synthesis, got {len(unconsumed_after)}"
        )

        # Verify consumed_by_job is set
        cursor = await sqlite_db.execute(
            "SELECT * FROM fb_synthesis_dirty_markers WHERE vault_id = ? AND consumed_by_job IS NOT NULL",
            (str(vault.vault_id),),
        )
        consumed = await cursor.fetchall()
        assert len(consumed) >= 1

    async def test_synthesize_writes_manifest(
        self, uow_factory, actor, mock_backend, sqlite_db,
    ):
        """Verify VaultSynthesisManifest persisted with join tables."""
        vault, src1, src2, m1, m2 = await _setup_vault_two_sources_compiled(
            uow_factory, actor, mock_backend,
        )

        synthesizer = VaultSynthesizer(
            uow_factory=uow_factory,
            backend=mock_backend,
            default_actor=actor,
        )

        manifest = await synthesizer.synthesize(vault_id=vault.vault_id)

        # Verify manifest in DB
        cursor = await sqlite_db.execute(
            "SELECT * FROM fb_vault_synthesis_manifests WHERE manifest_id = ?",
            (str(manifest.manifest_id),),
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row["vault_id"] == str(vault.vault_id)
        assert row["synthesis_policy_version"] == DEFAULT_POLICY.policy_version
        assert row["candidates_resolved"] > 0

        # Verify join table: pages created
        cursor = await sqlite_db.execute(
            "SELECT * FROM fb_synthesis_pages_created WHERE synthesis_manifest_id = ?",
            (str(manifest.manifest_id),),
        )
        pages_created_rows = await cursor.fetchall()
        assert len(pages_created_rows) >= 1, "No pages created in join table"

        # Verify join table: dirty markers consumed
        cursor = await sqlite_db.execute(
            "SELECT * FROM fb_synthesis_dirty_consumed WHERE synthesis_manifest_id = ?",
            (str(manifest.manifest_id),),
        )
        dirty_consumed_rows = await cursor.fetchall()
        assert len(dirty_consumed_rows) >= 1, "No dirty markers consumed in join table"

    async def test_synthesize_noop_on_unchanged_content(
        self, uow_factory, actor, mock_backend, sqlite_db,
    ):
        """Run synthesize twice; second time creates no new page versions."""
        vault, src1, src2, m1, m2 = await _setup_vault_two_sources_compiled(
            uow_factory, actor, mock_backend,
        )

        synthesizer = VaultSynthesizer(
            uow_factory=uow_factory,
            backend=mock_backend,
            default_actor=actor,
        )

        # First synthesis
        manifest1 = await synthesizer.synthesize(vault_id=vault.vault_id)

        # Count page versions for concept pages after first synthesis
        cursor = await sqlite_db.execute(
            "SELECT page_id FROM fb_pages WHERE vault_id = ? AND page_type = ?",
            (str(vault.vault_id), PageType.CONCEPT.value),
        )
        concept_page_ids = [r["page_id"] for r in await cursor.fetchall()]
        assert len(concept_page_ids) >= 1

        version_counts_after_first = {}
        for pid in concept_page_ids:
            cursor = await sqlite_db.execute(
                "SELECT COUNT(*) as cnt FROM fb_page_versions WHERE page_id = ?",
                (pid,),
            )
            version_counts_after_first[pid] = (await cursor.fetchone())["cnt"]

        # Re-dirty markers so tier 2 runs again (compile source again to re-create markers)
        # Actually, we need to re-compile sources to get new dirty markers,
        # since the first synthesis consumed them all.
        compiler = SourceCompiler(
            uow_factory=uow_factory,
            backend=mock_backend,
            default_actor=actor,
        )
        await compiler.compile_source(
            source_id=src1.source_id,
            source_version=Version(2),
            vault_id=vault.vault_id,
        )
        await compiler.compile_source(
            source_id=src2.source_id,
            source_version=Version(2),
            vault_id=vault.vault_id,
        )

        # Second synthesis (same backend → same content)
        manifest2 = await synthesizer.synthesize(vault_id=vault.vault_id)

        # Page versions should be unchanged (no-op check)
        for pid in concept_page_ids:
            cursor = await sqlite_db.execute(
                "SELECT COUNT(*) as cnt FROM fb_page_versions WHERE page_id = ?",
                (pid,),
            )
            count_after_second = (await cursor.fetchone())["cnt"]
            assert count_after_second == version_counts_after_first[pid], (
                f"Expected no-op for page {pid}: "
                f"versions after first={version_counts_after_first[pid]}, "
                f"after second={count_after_second}"
            )

    async def test_synthesize_on_workbook_branch(
        self, uow_factory, actor, mock_backend, sqlite_db,
    ):
        """Compile + synthesize on branch, verify branch-scoped."""
        vault, workbook, src1, src2, m1, m2 = await _setup_vault_two_sources_on_branch(
            uow_factory, actor, mock_backend,
        )

        synthesizer = VaultSynthesizer(
            uow_factory=uow_factory,
            backend=mock_backend,
            default_actor=actor,
        )

        manifest = await synthesizer.synthesize(
            vault_id=vault.vault_id,
            workbook_id=workbook.workbook_id,
        )

        # Verify concept pages created
        cursor = await sqlite_db.execute(
            "SELECT page_id FROM fb_pages WHERE vault_id = ? AND page_type = ?",
            (str(vault.vault_id), PageType.CONCEPT.value),
        )
        concept_page_ids = [r["page_id"] for r in await cursor.fetchall()]
        assert len(concept_page_ids) >= 1

        # Verify branch page heads set (not canonical)
        cursor = await sqlite_db.execute(
            "SELECT * FROM fb_branch_page_heads WHERE workbook_id = ?",
            (str(workbook.workbook_id),),
        )
        branch_page_heads = await cursor.fetchall()
        # Should have at least the concept pages + source card pages
        concept_branch_heads = [
            h for h in branch_page_heads if h["page_id"] in concept_page_ids
        ]
        assert len(concept_branch_heads) >= 1, (
            "No branch page heads for concept pages"
        )

        # Verify NO canonical heads for concept pages
        for pid in concept_page_ids:
            cursor = await sqlite_db.execute(
                "SELECT * FROM fb_canonical_heads WHERE entity_id = ?",
                (pid,),
            )
            canonical_row = await cursor.fetchone()
            assert canonical_row is None, (
                f"Concept page {pid} has canonical head but should only have branch head"
            )

        # Verify manifest has workbook_id
        assert manifest.workbook_id == workbook.workbook_id
