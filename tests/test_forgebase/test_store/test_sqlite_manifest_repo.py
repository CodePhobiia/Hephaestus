"""Tests for SQLite compile manifest repository."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from hephaestus.forgebase.domain.models import (
    BackendCallRecord,
    SourceCompileManifest,
    VaultSynthesisManifest,
)
from hephaestus.forgebase.domain.values import ContentHash, EntityId, VaultRevisionId, Version
from hephaestus.forgebase.store.sqlite.compile_manifest_repo import SqliteCompileManifestRepository


def _now() -> datetime:
    return datetime(2026, 4, 3, 12, 0, 0, tzinfo=UTC)


def _source_manifest(
    id_gen, vault_id: EntityId, source_id: EntityId | None = None
) -> SourceCompileManifest:
    return SourceCompileManifest(
        manifest_id=id_gen.generate("mfst"),
        vault_id=vault_id,
        workbook_id=None,
        source_id=source_id or id_gen.generate("source"),
        source_version=Version(1),
        job_id=id_gen.generate("job"),
        compiler_policy_version="1.0.0",
        prompt_versions={"claim_extraction": "1.0.0"},
        backend_calls=[
            BackendCallRecord(
                model_name="claude-sonnet-4-5",
                backend_kind="anthropic",
                prompt_id="claim_extraction",
                prompt_version="1.0.0",
                schema_version=1,
                repair_invoked=False,
                input_tokens=500,
                output_tokens=200,
                duration_ms=1200,
                raw_output_ref=None,
            ),
        ],
        claim_count=5,
        concept_count=3,
        relationship_count=2,
        source_content_hash=ContentHash(sha256="a" * 64),
        created_at=_now(),
    )


def _vault_manifest(id_gen, vault_id: EntityId) -> VaultSynthesisManifest:
    return VaultSynthesisManifest(
        manifest_id=id_gen.generate("mfst"),
        vault_id=vault_id,
        workbook_id=None,
        job_id=id_gen.generate("job"),
        base_revision=VaultRevisionId(f"rev_{id_gen.generate('x')._raw.split('_', 1)[1]}"),
        synthesis_policy_version="1.0.0",
        prompt_versions={"synthesis": "1.0.0"},
        backend_calls=[],
        candidates_resolved=10,
        augmentor_calls=2,
        created_at=_now(),
    )


@pytest.mark.asyncio
class TestSqliteCompileManifestRepository:
    async def test_create_and_get_source_manifest(self, sqlite_db, id_gen):
        repo = SqliteCompileManifestRepository(sqlite_db)
        vault_id = id_gen.vault_id()
        m = _source_manifest(id_gen, vault_id)

        await repo.create_source_manifest(m)
        await sqlite_db.commit()

        got = await repo.get_source_manifest(m.manifest_id)
        assert got is not None
        assert got.claim_count == 5
        assert got.concept_count == 3
        assert len(got.backend_calls) == 1
        assert got.backend_calls[0].model_name == "claude-sonnet-4-5"
        assert got.source_content_hash.sha256 == "a" * 64

    async def test_get_source_manifest_for(self, sqlite_db, id_gen):
        repo = SqliteCompileManifestRepository(sqlite_db)
        vault_id = id_gen.vault_id()
        source_id = id_gen.generate("source")
        m = _source_manifest(id_gen, vault_id, source_id=source_id)

        await repo.create_source_manifest(m)
        await sqlite_db.commit()

        got = await repo.get_source_manifest_for(source_id, Version(1))
        assert got is not None
        assert got.manifest_id == m.manifest_id

    async def test_get_source_manifest_nonexistent(self, sqlite_db, id_gen):
        repo = SqliteCompileManifestRepository(sqlite_db)
        assert await repo.get_source_manifest(id_gen.generate("mfst")) is None

    async def test_create_and_get_vault_manifest(self, sqlite_db, id_gen):
        repo = SqliteCompileManifestRepository(sqlite_db)
        vault_id = id_gen.vault_id()
        m = _vault_manifest(id_gen, vault_id)

        await repo.create_vault_manifest(m)
        await sqlite_db.commit()

        got = await repo.get_vault_manifest(m.manifest_id)
        assert got is not None
        assert got.candidates_resolved == 10
        assert got.augmentor_calls == 2

    async def test_get_latest_vault_manifest(self, sqlite_db, id_gen):
        repo = SqliteCompileManifestRepository(sqlite_db)
        vault_id = id_gen.vault_id()

        m1 = _vault_manifest(id_gen, vault_id)
        m2 = _vault_manifest(id_gen, vault_id)
        # m2 has a later created_at by virtue of datetime, but both use _now()
        # so we need to manually adjust one
        m2 = VaultSynthesisManifest(
            manifest_id=m2.manifest_id,
            vault_id=m2.vault_id,
            workbook_id=m2.workbook_id,
            job_id=m2.job_id,
            base_revision=m2.base_revision,
            synthesis_policy_version=m2.synthesis_policy_version,
            prompt_versions=m2.prompt_versions,
            backend_calls=m2.backend_calls,
            candidates_resolved=20,
            augmentor_calls=m2.augmentor_calls,
            created_at=datetime(2026, 4, 4, 12, 0, 0, tzinfo=UTC),  # later
        )

        await repo.create_vault_manifest(m1)
        await repo.create_vault_manifest(m2)
        await sqlite_db.commit()

        latest = await repo.get_latest_vault_manifest(vault_id)
        assert latest is not None
        assert latest.candidates_resolved == 20  # the later one

    async def test_join_table_source_manifest(self, sqlite_db, id_gen):
        repo = SqliteCompileManifestRepository(sqlite_db)
        vault_id = id_gen.vault_id()

        sm = _source_manifest(id_gen, vault_id)
        vm = _vault_manifest(id_gen, vault_id)

        await repo.create_source_manifest(sm)
        await repo.create_vault_manifest(vm)
        await repo.add_synthesis_source_manifest(vm.manifest_id, sm.manifest_id)
        await sqlite_db.commit()

        # Verify the association exists via a raw query
        cursor = await sqlite_db.execute(
            "SELECT * FROM fb_synthesis_source_manifests WHERE synthesis_manifest_id = ?",
            (str(vm.manifest_id),),
        )
        rows = await cursor.fetchall()
        assert len(rows) == 1
        assert rows[0]["source_manifest_id"] == str(sm.manifest_id)

    async def test_join_table_pages(self, sqlite_db, id_gen):
        repo = SqliteCompileManifestRepository(sqlite_db)
        vault_id = id_gen.vault_id()
        vm = _vault_manifest(id_gen, vault_id)
        await repo.create_vault_manifest(vm)

        page_id = id_gen.generate("page")
        await repo.add_synthesis_page_created(vm.manifest_id, page_id)
        page_id2 = id_gen.generate("page")
        await repo.add_synthesis_page_updated(vm.manifest_id, page_id2)
        await sqlite_db.commit()

        cursor = await sqlite_db.execute(
            "SELECT * FROM fb_synthesis_pages_created WHERE synthesis_manifest_id = ?",
            (str(vm.manifest_id),),
        )
        assert len(await cursor.fetchall()) == 1

        cursor = await sqlite_db.execute(
            "SELECT * FROM fb_synthesis_pages_updated WHERE synthesis_manifest_id = ?",
            (str(vm.manifest_id),),
        )
        assert len(await cursor.fetchall()) == 1

    async def test_join_table_dirty_consumed(self, sqlite_db, id_gen):
        repo = SqliteCompileManifestRepository(sqlite_db)
        vault_id = id_gen.vault_id()
        vm = _vault_manifest(id_gen, vault_id)
        await repo.create_vault_manifest(vm)

        marker_id = id_gen.generate("dirty")
        await repo.add_synthesis_dirty_consumed(vm.manifest_id, marker_id)
        await sqlite_db.commit()

        cursor = await sqlite_db.execute(
            "SELECT * FROM fb_synthesis_dirty_consumed WHERE synthesis_manifest_id = ?",
            (str(vm.manifest_id),),
        )
        rows = await cursor.fetchall()
        assert len(rows) == 1
        assert rows[0]["marker_id"] == str(marker_id)
