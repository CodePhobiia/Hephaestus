"""SQLite implementation of WorkbookRepository."""
from __future__ import annotations

from datetime import datetime

import aiosqlite

from hephaestus.forgebase.domain.enums import (
    ActorType,
    BranchPurpose,
    EntityKind,
    WorkbookStatus,
)
from hephaestus.forgebase.domain.models import (
    BranchClaimDerivationHead,
    BranchClaimHead,
    BranchClaimSupportHead,
    BranchLinkHead,
    BranchPageHead,
    BranchSourceHead,
    BranchTombstone,
    Workbook,
)
from hephaestus.forgebase.domain.values import ActorRef, EntityId, VaultRevisionId, Version
from hephaestus.forgebase.repository.workbook_repo import WorkbookRepository


class SqliteWorkbookRepository(WorkbookRepository):
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    # ================================================================
    # Workbook CRUD
    # ================================================================

    async def create(self, workbook: Workbook) -> None:
        await self._db.execute(
            "INSERT INTO fb_workbooks (workbook_id, vault_id, name, purpose, status, base_revision_id, created_at, created_by_type, created_by_id, created_by_run) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(workbook.workbook_id),
                str(workbook.vault_id),
                workbook.name,
                workbook.purpose.value,
                workbook.status.value,
                str(workbook.base_revision_id),
                workbook.created_at.isoformat(),
                workbook.created_by.actor_type.value,
                workbook.created_by.actor_id,
                str(workbook.created_by_run) if workbook.created_by_run else None,
            ),
        )

    async def get(self, workbook_id: EntityId) -> Workbook | None:
        cursor = await self._db.execute(
            "SELECT * FROM fb_workbooks WHERE workbook_id = ?",
            (str(workbook_id),),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_workbook(row)

    async def list_by_vault(
        self,
        vault_id: EntityId,
        *,
        status: WorkbookStatus | None = None,
    ) -> list[Workbook]:
        if status is not None:
            cursor = await self._db.execute(
                "SELECT * FROM fb_workbooks WHERE vault_id = ? AND status = ? ORDER BY created_at",
                (str(vault_id), status.value),
            )
        else:
            cursor = await self._db.execute(
                "SELECT * FROM fb_workbooks WHERE vault_id = ? ORDER BY created_at",
                (str(vault_id),),
            )
        rows = await cursor.fetchall()
        return [self._row_to_workbook(r) for r in rows]

    async def update_status(self, workbook_id: EntityId, status: WorkbookStatus) -> None:
        await self._db.execute(
            "UPDATE fb_workbooks SET status = ? WHERE workbook_id = ?",
            (status.value, str(workbook_id)),
        )

    # ================================================================
    # Branch Page Heads
    # ================================================================

    async def set_page_head(self, head: BranchPageHead) -> None:
        await self._db.execute(
            "INSERT OR REPLACE INTO fb_branch_page_heads (workbook_id, page_id, head_version, base_version) VALUES (?, ?, ?, ?)",
            (
                str(head.workbook_id),
                str(head.page_id),
                head.head_version.number,
                head.base_version.number,
            ),
        )

    async def get_page_head(self, workbook_id: EntityId, page_id: EntityId) -> BranchPageHead | None:
        cursor = await self._db.execute(
            "SELECT * FROM fb_branch_page_heads WHERE workbook_id = ? AND page_id = ?",
            (str(workbook_id), str(page_id)),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return BranchPageHead(
            workbook_id=EntityId(row["workbook_id"]),
            page_id=EntityId(row["page_id"]),
            head_version=Version(row["head_version"]),
            base_version=Version(row["base_version"]),
        )

    async def list_page_heads(self, workbook_id: EntityId) -> list[BranchPageHead]:
        cursor = await self._db.execute(
            "SELECT * FROM fb_branch_page_heads WHERE workbook_id = ?",
            (str(workbook_id),),
        )
        rows = await cursor.fetchall()
        return [
            BranchPageHead(
                workbook_id=EntityId(r["workbook_id"]),
                page_id=EntityId(r["page_id"]),
                head_version=Version(r["head_version"]),
                base_version=Version(r["base_version"]),
            )
            for r in rows
        ]

    # ================================================================
    # Branch Claim Heads
    # ================================================================

    async def set_claim_head(self, head: BranchClaimHead) -> None:
        await self._db.execute(
            "INSERT OR REPLACE INTO fb_branch_claim_heads (workbook_id, claim_id, head_version, base_version) VALUES (?, ?, ?, ?)",
            (
                str(head.workbook_id),
                str(head.claim_id),
                head.head_version.number,
                head.base_version.number,
            ),
        )

    async def get_claim_head(self, workbook_id: EntityId, claim_id: EntityId) -> BranchClaimHead | None:
        cursor = await self._db.execute(
            "SELECT * FROM fb_branch_claim_heads WHERE workbook_id = ? AND claim_id = ?",
            (str(workbook_id), str(claim_id)),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return BranchClaimHead(
            workbook_id=EntityId(row["workbook_id"]),
            claim_id=EntityId(row["claim_id"]),
            head_version=Version(row["head_version"]),
            base_version=Version(row["base_version"]),
        )

    async def list_claim_heads(self, workbook_id: EntityId) -> list[BranchClaimHead]:
        cursor = await self._db.execute(
            "SELECT * FROM fb_branch_claim_heads WHERE workbook_id = ?",
            (str(workbook_id),),
        )
        rows = await cursor.fetchall()
        return [
            BranchClaimHead(
                workbook_id=EntityId(r["workbook_id"]),
                claim_id=EntityId(r["claim_id"]),
                head_version=Version(r["head_version"]),
                base_version=Version(r["base_version"]),
            )
            for r in rows
        ]

    # ================================================================
    # Branch Link Heads
    # ================================================================

    async def set_link_head(self, head: BranchLinkHead) -> None:
        await self._db.execute(
            "INSERT OR REPLACE INTO fb_branch_link_heads (workbook_id, link_id, head_version, base_version) VALUES (?, ?, ?, ?)",
            (
                str(head.workbook_id),
                str(head.link_id),
                head.head_version.number,
                head.base_version.number,
            ),
        )

    async def get_link_head(self, workbook_id: EntityId, link_id: EntityId) -> BranchLinkHead | None:
        cursor = await self._db.execute(
            "SELECT * FROM fb_branch_link_heads WHERE workbook_id = ? AND link_id = ?",
            (str(workbook_id), str(link_id)),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return BranchLinkHead(
            workbook_id=EntityId(row["workbook_id"]),
            link_id=EntityId(row["link_id"]),
            head_version=Version(row["head_version"]),
            base_version=Version(row["base_version"]),
        )

    async def list_link_heads(self, workbook_id: EntityId) -> list[BranchLinkHead]:
        cursor = await self._db.execute(
            "SELECT * FROM fb_branch_link_heads WHERE workbook_id = ?",
            (str(workbook_id),),
        )
        rows = await cursor.fetchall()
        return [
            BranchLinkHead(
                workbook_id=EntityId(r["workbook_id"]),
                link_id=EntityId(r["link_id"]),
                head_version=Version(r["head_version"]),
                base_version=Version(r["base_version"]),
            )
            for r in rows
        ]

    # ================================================================
    # Branch Source Heads
    # ================================================================

    async def set_source_head(self, head: BranchSourceHead) -> None:
        await self._db.execute(
            "INSERT OR REPLACE INTO fb_branch_source_heads (workbook_id, source_id, head_version, base_version) VALUES (?, ?, ?, ?)",
            (
                str(head.workbook_id),
                str(head.source_id),
                head.head_version.number,
                head.base_version.number,
            ),
        )

    async def get_source_head(self, workbook_id: EntityId, source_id: EntityId) -> BranchSourceHead | None:
        cursor = await self._db.execute(
            "SELECT * FROM fb_branch_source_heads WHERE workbook_id = ? AND source_id = ?",
            (str(workbook_id), str(source_id)),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return BranchSourceHead(
            workbook_id=EntityId(row["workbook_id"]),
            source_id=EntityId(row["source_id"]),
            head_version=Version(row["head_version"]),
            base_version=Version(row["base_version"]),
        )

    async def list_source_heads(self, workbook_id: EntityId) -> list[BranchSourceHead]:
        cursor = await self._db.execute(
            "SELECT * FROM fb_branch_source_heads WHERE workbook_id = ?",
            (str(workbook_id),),
        )
        rows = await cursor.fetchall()
        return [
            BranchSourceHead(
                workbook_id=EntityId(r["workbook_id"]),
                source_id=EntityId(r["source_id"]),
                head_version=Version(r["head_version"]),
                base_version=Version(r["base_version"]),
            )
            for r in rows
        ]

    # ================================================================
    # Branch Claim Support Heads
    # ================================================================

    async def set_claim_support_head(self, head: BranchClaimSupportHead) -> None:
        await self._db.execute(
            "INSERT OR REPLACE INTO fb_branch_claim_support_heads (workbook_id, support_id, created_on_branch) VALUES (?, ?, ?)",
            (
                str(head.workbook_id),
                str(head.support_id),
                int(head.created_on_branch),
            ),
        )

    async def list_claim_support_heads(self, workbook_id: EntityId) -> list[BranchClaimSupportHead]:
        cursor = await self._db.execute(
            "SELECT * FROM fb_branch_claim_support_heads WHERE workbook_id = ?",
            (str(workbook_id),),
        )
        rows = await cursor.fetchall()
        return [
            BranchClaimSupportHead(
                workbook_id=EntityId(r["workbook_id"]),
                support_id=EntityId(r["support_id"]),
                created_on_branch=bool(r["created_on_branch"]),
            )
            for r in rows
        ]

    # ================================================================
    # Branch Claim Derivation Heads
    # ================================================================

    async def set_claim_derivation_head(self, head: BranchClaimDerivationHead) -> None:
        await self._db.execute(
            "INSERT OR REPLACE INTO fb_branch_claim_derivation_heads (workbook_id, derivation_id, created_on_branch) VALUES (?, ?, ?)",
            (
                str(head.workbook_id),
                str(head.derivation_id),
                int(head.created_on_branch),
            ),
        )

    async def list_claim_derivation_heads(self, workbook_id: EntityId) -> list[BranchClaimDerivationHead]:
        cursor = await self._db.execute(
            "SELECT * FROM fb_branch_claim_derivation_heads WHERE workbook_id = ?",
            (str(workbook_id),),
        )
        rows = await cursor.fetchall()
        return [
            BranchClaimDerivationHead(
                workbook_id=EntityId(r["workbook_id"]),
                derivation_id=EntityId(r["derivation_id"]),
                created_on_branch=bool(r["created_on_branch"]),
            )
            for r in rows
        ]

    # ================================================================
    # Tombstones
    # ================================================================

    async def add_tombstone(self, tombstone: BranchTombstone) -> None:
        await self._db.execute(
            "INSERT INTO fb_branch_tombstones (workbook_id, entity_kind, entity_id, tombstoned_at) VALUES (?, ?, ?, ?)",
            (
                str(tombstone.workbook_id),
                tombstone.entity_kind.value,
                str(tombstone.entity_id),
                tombstone.tombstoned_at.isoformat(),
            ),
        )

    async def get_tombstone(
        self,
        workbook_id: EntityId,
        entity_kind: EntityKind,
        entity_id: EntityId,
    ) -> BranchTombstone | None:
        cursor = await self._db.execute(
            "SELECT * FROM fb_branch_tombstones WHERE workbook_id = ? AND entity_kind = ? AND entity_id = ?",
            (str(workbook_id), entity_kind.value, str(entity_id)),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return BranchTombstone(
            workbook_id=EntityId(row["workbook_id"]),
            entity_kind=EntityKind(row["entity_kind"]),
            entity_id=EntityId(row["entity_id"]),
            tombstoned_at=datetime.fromisoformat(row["tombstoned_at"]),
        )

    async def list_tombstones(self, workbook_id: EntityId) -> list[BranchTombstone]:
        cursor = await self._db.execute(
            "SELECT * FROM fb_branch_tombstones WHERE workbook_id = ?",
            (str(workbook_id),),
        )
        rows = await cursor.fetchall()
        return [
            BranchTombstone(
                workbook_id=EntityId(r["workbook_id"]),
                entity_kind=EntityKind(r["entity_kind"]),
                entity_id=EntityId(r["entity_id"]),
                tombstoned_at=datetime.fromisoformat(r["tombstoned_at"]),
            )
            for r in rows
        ]

    # ================================================================
    # Row mapping
    # ================================================================

    @staticmethod
    def _row_to_workbook(row: aiosqlite.Row) -> Workbook:
        return Workbook(
            workbook_id=EntityId(row["workbook_id"]),
            vault_id=EntityId(row["vault_id"]),
            name=row["name"],
            purpose=BranchPurpose(row["purpose"]),
            status=WorkbookStatus(row["status"]),
            base_revision_id=VaultRevisionId(row["base_revision_id"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            created_by=ActorRef(
                actor_type=ActorType(row["created_by_type"]),
                actor_id=row["created_by_id"],
            ),
            created_by_run=EntityId(row["created_by_run"]) if row["created_by_run"] else None,
        )
