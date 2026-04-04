"""SQLite implementation of CompileManifestRepository."""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime

import aiosqlite

from hephaestus.forgebase.domain.models import (
    BackendCallRecord,
    SourceCompileManifest,
    VaultSynthesisManifest,
)
from hephaestus.forgebase.domain.values import (
    BlobRef,
    ContentHash,
    EntityId,
    VaultRevisionId,
    Version,
)
from hephaestus.forgebase.repository.compile_manifest_repo import CompileManifestRepository


class SqliteCompileManifestRepository(CompileManifestRepository):
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    # --- Source manifests ---

    async def create_source_manifest(self, manifest: SourceCompileManifest) -> None:
        await self._db.execute(
            """INSERT INTO fb_source_compile_manifests
            (manifest_id, vault_id, workbook_id, source_id, source_version,
             job_id, compiler_policy_version, prompt_versions, backend_calls,
             claim_count, concept_count, relationship_count, source_content_hash,
             created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(manifest.manifest_id),
                str(manifest.vault_id),
                str(manifest.workbook_id) if manifest.workbook_id else None,
                str(manifest.source_id),
                manifest.source_version.number,
                str(manifest.job_id),
                manifest.compiler_policy_version,
                json.dumps(manifest.prompt_versions),
                json.dumps([self._call_to_dict(c) for c in manifest.backend_calls]),
                manifest.claim_count,
                manifest.concept_count,
                manifest.relationship_count,
                manifest.source_content_hash.sha256,
                manifest.created_at.isoformat(),
            ),
        )

    async def get_source_manifest(self, manifest_id: EntityId) -> SourceCompileManifest | None:
        cursor = await self._db.execute(
            "SELECT * FROM fb_source_compile_manifests WHERE manifest_id = ?",
            (str(manifest_id),),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_source_manifest(row)

    async def get_source_manifest_for(
        self,
        source_id: EntityId,
        source_version: Version,
    ) -> SourceCompileManifest | None:
        cursor = await self._db.execute(
            "SELECT * FROM fb_source_compile_manifests WHERE source_id = ? AND source_version = ? ORDER BY created_at DESC LIMIT 1",
            (str(source_id), source_version.number),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_source_manifest(row)

    # --- Vault synthesis manifests ---

    async def create_vault_manifest(self, manifest: VaultSynthesisManifest) -> None:
        await self._db.execute(
            """INSERT INTO fb_vault_synthesis_manifests
            (manifest_id, vault_id, workbook_id, job_id, base_revision,
             synthesis_policy_version, prompt_versions, backend_calls,
             candidates_resolved, augmentor_calls, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(manifest.manifest_id),
                str(manifest.vault_id),
                str(manifest.workbook_id) if manifest.workbook_id else None,
                str(manifest.job_id),
                str(manifest.base_revision),
                manifest.synthesis_policy_version,
                json.dumps(manifest.prompt_versions),
                json.dumps([self._call_to_dict(c) for c in manifest.backend_calls]),
                manifest.candidates_resolved,
                manifest.augmentor_calls,
                manifest.created_at.isoformat(),
            ),
        )

    async def get_vault_manifest(self, manifest_id: EntityId) -> VaultSynthesisManifest | None:
        cursor = await self._db.execute(
            "SELECT * FROM fb_vault_synthesis_manifests WHERE manifest_id = ?",
            (str(manifest_id),),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_vault_manifest(row)

    async def get_latest_vault_manifest(
        self,
        vault_id: EntityId,
        workbook_id: EntityId | None = None,
    ) -> VaultSynthesisManifest | None:
        if workbook_id is not None:
            cursor = await self._db.execute(
                "SELECT * FROM fb_vault_synthesis_manifests WHERE vault_id = ? AND workbook_id = ? ORDER BY created_at DESC LIMIT 1",
                (str(vault_id), str(workbook_id)),
            )
        else:
            cursor = await self._db.execute(
                "SELECT * FROM fb_vault_synthesis_manifests WHERE vault_id = ? AND workbook_id IS NULL ORDER BY created_at DESC LIMIT 1",
                (str(vault_id),),
            )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_vault_manifest(row)

    # --- Join table methods ---

    async def add_synthesis_source_manifest(
        self,
        synthesis_id: EntityId,
        source_manifest_id: EntityId,
    ) -> None:
        await self._db.execute(
            "INSERT INTO fb_synthesis_source_manifests (synthesis_manifest_id, source_manifest_id) VALUES (?, ?)",
            (str(synthesis_id), str(source_manifest_id)),
        )

    async def add_synthesis_page_created(
        self,
        synthesis_id: EntityId,
        page_id: EntityId,
    ) -> None:
        await self._db.execute(
            "INSERT INTO fb_synthesis_pages_created (synthesis_manifest_id, page_id) VALUES (?, ?)",
            (str(synthesis_id), str(page_id)),
        )

    async def add_synthesis_page_updated(
        self,
        synthesis_id: EntityId,
        page_id: EntityId,
    ) -> None:
        await self._db.execute(
            "INSERT INTO fb_synthesis_pages_updated (synthesis_manifest_id, page_id) VALUES (?, ?)",
            (str(synthesis_id), str(page_id)),
        )

    async def add_synthesis_dirty_consumed(
        self,
        synthesis_id: EntityId,
        marker_id: EntityId,
    ) -> None:
        await self._db.execute(
            "INSERT INTO fb_synthesis_dirty_consumed (synthesis_manifest_id, marker_id) VALUES (?, ?)",
            (str(synthesis_id), str(marker_id)),
        )

    # --- Row mapping ---

    @staticmethod
    def _call_to_dict(call: BackendCallRecord) -> dict:
        d = asdict(call)
        # BlobRef is not JSON-serializable, convert or set to None
        if call.raw_output_ref is not None:
            d["raw_output_ref"] = {
                "content_hash": call.raw_output_ref.content_hash.sha256,
                "size_bytes": call.raw_output_ref.size_bytes,
                "mime_type": call.raw_output_ref.mime_type,
            }
        return d

    @staticmethod
    def _dict_to_call(d: dict) -> BackendCallRecord:
        raw_ref = d.get("raw_output_ref")
        blob_ref = None
        if raw_ref is not None:
            blob_ref = BlobRef(
                content_hash=ContentHash(sha256=raw_ref["content_hash"]),
                size_bytes=raw_ref["size_bytes"],
                mime_type=raw_ref["mime_type"],
            )
        return BackendCallRecord(
            model_name=d["model_name"],
            backend_kind=d["backend_kind"],
            prompt_id=d["prompt_id"],
            prompt_version=d["prompt_version"],
            schema_version=d["schema_version"],
            repair_invoked=d["repair_invoked"],
            input_tokens=d["input_tokens"],
            output_tokens=d["output_tokens"],
            duration_ms=d["duration_ms"],
            raw_output_ref=blob_ref,
        )

    @staticmethod
    def _row_to_source_manifest(row: aiosqlite.Row) -> SourceCompileManifest:
        backend_calls_raw = json.loads(row["backend_calls"])
        return SourceCompileManifest(
            manifest_id=EntityId(row["manifest_id"]),
            vault_id=EntityId(row["vault_id"]),
            workbook_id=EntityId(row["workbook_id"]) if row["workbook_id"] else None,
            source_id=EntityId(row["source_id"]),
            source_version=Version(row["source_version"]),
            job_id=EntityId(row["job_id"]),
            compiler_policy_version=row["compiler_policy_version"],
            prompt_versions=json.loads(row["prompt_versions"]),
            backend_calls=[SqliteCompileManifestRepository._dict_to_call(c) for c in backend_calls_raw],
            claim_count=row["claim_count"],
            concept_count=row["concept_count"],
            relationship_count=row["relationship_count"],
            source_content_hash=ContentHash(sha256=row["source_content_hash"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    @staticmethod
    def _row_to_vault_manifest(row: aiosqlite.Row) -> VaultSynthesisManifest:
        backend_calls_raw = json.loads(row["backend_calls"])
        return VaultSynthesisManifest(
            manifest_id=EntityId(row["manifest_id"]),
            vault_id=EntityId(row["vault_id"]),
            workbook_id=EntityId(row["workbook_id"]) if row["workbook_id"] else None,
            job_id=EntityId(row["job_id"]),
            base_revision=VaultRevisionId(row["base_revision"]),
            synthesis_policy_version=row["synthesis_policy_version"],
            prompt_versions=json.loads(row["prompt_versions"]),
            backend_calls=[SqliteCompileManifestRepository._dict_to_call(c) for c in backend_calls_raw],
            candidates_resolved=row["candidates_resolved"],
            augmentor_calls=row["augmentor_calls"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )
