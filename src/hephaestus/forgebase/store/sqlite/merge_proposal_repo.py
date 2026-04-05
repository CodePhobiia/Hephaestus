"""SQLite implementation of MergeProposalRepository."""

from __future__ import annotations

from datetime import datetime

import aiosqlite

from hephaestus.forgebase.domain.enums import ActorType, MergeVerdict
from hephaestus.forgebase.domain.models import MergeProposal
from hephaestus.forgebase.domain.values import ActorRef, EntityId, VaultRevisionId
from hephaestus.forgebase.repository.merge_proposal_repo import MergeProposalRepository


class SqliteMergeProposalRepository(MergeProposalRepository):
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def create(self, proposal: MergeProposal) -> None:
        await self._db.execute(
            "INSERT INTO fb_merge_proposals (merge_id, workbook_id, vault_id, base_revision_id, target_revision_id, verdict, resulting_revision, proposed_at, resolved_at, proposed_by_type, proposed_by_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(proposal.merge_id),
                str(proposal.workbook_id),
                str(proposal.vault_id),
                str(proposal.base_revision_id),
                str(proposal.target_revision_id),
                proposal.verdict.value,
                str(proposal.resulting_revision) if proposal.resulting_revision else None,
                proposal.proposed_at.isoformat(),
                proposal.resolved_at.isoformat() if proposal.resolved_at else None,
                proposal.proposed_by.actor_type.value,
                proposal.proposed_by.actor_id,
            ),
        )

    async def get(self, merge_id: EntityId) -> MergeProposal | None:
        cursor = await self._db.execute(
            "SELECT * FROM fb_merge_proposals WHERE merge_id = ?",
            (str(merge_id),),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_proposal(row)

    async def set_result(self, merge_id: EntityId, resulting_revision: VaultRevisionId) -> None:
        await self._db.execute(
            "UPDATE fb_merge_proposals SET resulting_revision = ? WHERE merge_id = ?",
            (str(resulting_revision), str(merge_id)),
        )

    @staticmethod
    def _row_to_proposal(row: aiosqlite.Row) -> MergeProposal:
        return MergeProposal(
            merge_id=EntityId(row["merge_id"]),
            workbook_id=EntityId(row["workbook_id"]),
            vault_id=EntityId(row["vault_id"]),
            base_revision_id=VaultRevisionId(row["base_revision_id"]),
            target_revision_id=VaultRevisionId(row["target_revision_id"]),
            verdict=MergeVerdict(row["verdict"]),
            resulting_revision=VaultRevisionId(row["resulting_revision"])
            if row["resulting_revision"]
            else None,
            proposed_at=datetime.fromisoformat(row["proposed_at"]),
            resolved_at=datetime.fromisoformat(row["resolved_at"]) if row["resolved_at"] else None,
            proposed_by=ActorRef(
                actor_type=ActorType(row["proposed_by_type"]), actor_id=row["proposed_by_id"]
            ),
        )
