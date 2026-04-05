"""Tests for MergeService — propose, resolve conflicts, execute merges."""

from __future__ import annotations

import pytest

from hephaestus.forgebase.domain.enums import (
    BranchPurpose,
    MergeResolution,
    MergeVerdict,
    PageType,
)
from hephaestus.forgebase.domain.values import Version
from hephaestus.forgebase.service.branch_service import BranchService
from hephaestus.forgebase.service.exceptions import (
    EntityNotFoundError,
    StaleMergeError,
    UnresolvedConflictsError,
)
from hephaestus.forgebase.service.merge_service import MergeService
from hephaestus.forgebase.service.page_service import PageService
from hephaestus.forgebase.service.vault_service import VaultService


@pytest.mark.asyncio
class TestMergeServicePropose:
    """Tests for propose_merge."""

    async def _setup(self, uow_factory, actor):
        """Create vault, page on canonical, and workbook."""
        vault_svc = VaultService(uow_factory=uow_factory, default_actor=actor)
        vault = await vault_svc.create_vault(name="MergeVault")

        page_svc = PageService(uow_factory=uow_factory, default_actor=actor)
        page, pv = await page_svc.create_page(
            vault_id=vault.vault_id,
            page_key="alpha",
            page_type=PageType.CONCEPT,
            title="Alpha",
            content=b"# Alpha\nOriginal",
            summary="v1",
        )

        branch_svc = BranchService(uow_factory=uow_factory, default_actor=actor)
        wb = await branch_svc.create_workbook(
            vault_id=vault.vault_id,
            name="Feature Branch",
            purpose=BranchPurpose.RESEARCH,
        )

        return vault, page, pv, wb

    async def test_propose_clean_merge(self, uow_factory, actor):
        """A branch that modifies a page where canonical didn't change should be CLEAN."""
        vault, page, pv, wb = await self._setup(uow_factory, actor)

        # Modify page on branch
        page_svc = PageService(uow_factory=uow_factory, default_actor=actor)
        await page_svc.update_page(
            page_id=page.page_id,
            expected_version=Version(1),
            title="Alpha Updated",
            content=b"# Alpha\nUpdated on branch",
            workbook_id=wb.workbook_id,
        )

        merge_svc = MergeService(uow_factory=uow_factory, default_actor=actor)
        proposal = await merge_svc.propose_merge(wb.workbook_id)

        assert proposal.verdict == MergeVerdict.CLEAN
        assert proposal.workbook_id == wb.workbook_id
        assert proposal.vault_id == vault.vault_id
        assert proposal.resulting_revision is None

    async def test_propose_conflicted_merge(self, uow_factory, actor):
        """When both branch and canonical modify the same page, detect conflict."""
        vault, page, pv, wb = await self._setup(uow_factory, actor)

        page_svc = PageService(uow_factory=uow_factory, default_actor=actor)

        # Modify on branch first (v1 -> v2 in page_versions, branch head = v2, base = v1)
        await page_svc.update_page(
            page_id=page.page_id,
            expected_version=Version(1),
            title="Alpha Branch",
            content=b"# Alpha\nBranch version",
            workbook_id=wb.workbook_id,
        )

        # Modify on canonical -- must use expected_version=2 because
        # page_versions table now has v2 from branch, and get_head_version
        # returns v2. This creates v3, canonical head = 3.
        await page_svc.update_page(
            page_id=page.page_id,
            expected_version=Version(2),
            title="Alpha Canonical",
            content=b"# Alpha\nCanonical version",
        )

        # Now: branch head base=v1, canonical head=v3 -> v3 != v1 -> CONFLICTED
        merge_svc = MergeService(uow_factory=uow_factory, default_actor=actor)
        proposal = await merge_svc.propose_merge(wb.workbook_id)

        assert proposal.verdict == MergeVerdict.CONFLICTED

    async def test_propose_merge_emits_events(self, uow_factory, actor, sqlite_db):
        vault, page, pv, wb = await self._setup(uow_factory, actor)

        page_svc = PageService(uow_factory=uow_factory, default_actor=actor)
        await page_svc.update_page(
            page_id=page.page_id,
            expected_version=Version(1),
            title="Changed",
            workbook_id=wb.workbook_id,
        )

        merge_svc = MergeService(uow_factory=uow_factory, default_actor=actor)
        await merge_svc.propose_merge(wb.workbook_id)

        cursor = await sqlite_db.execute(
            "SELECT event_type FROM fb_domain_events WHERE event_type = 'merge.proposed'"
        )
        row = await cursor.fetchone()
        assert row is not None

    async def test_propose_workbook_not_found_raises(self, uow_factory, actor, id_gen):
        merge_svc = MergeService(uow_factory=uow_factory, default_actor=actor)

        fake_id = id_gen.workbook_id()
        with pytest.raises(EntityNotFoundError, match="Workbook not found"):
            await merge_svc.propose_merge(fake_id)

    async def test_propose_conflicted_merge_emits_conflict_events(
        self, uow_factory, actor, sqlite_db
    ):
        vault, page, pv, wb = await self._setup(uow_factory, actor)

        page_svc = PageService(uow_factory=uow_factory, default_actor=actor)

        # Branch and canonical both modify
        await page_svc.update_page(
            page_id=page.page_id,
            expected_version=Version(1),
            title="Branch",
            workbook_id=wb.workbook_id,
        )
        await page_svc.update_page(
            page_id=page.page_id,
            expected_version=Version(2),
            title="Canonical",
        )

        merge_svc = MergeService(uow_factory=uow_factory, default_actor=actor)
        await merge_svc.propose_merge(wb.workbook_id)

        cursor = await sqlite_db.execute(
            "SELECT event_type FROM fb_domain_events WHERE event_type = 'merge.conflict_detected'"
        )
        row = await cursor.fetchone()
        assert row is not None


@pytest.mark.asyncio
class TestMergeServiceResolve:
    """Tests for resolve_conflict."""

    async def _setup_conflicted(self, uow_factory, actor):
        """Create a conflicted merge proposal and return (merge_svc, proposal, conflicts)."""
        vault_svc = VaultService(uow_factory=uow_factory, default_actor=actor)
        vault = await vault_svc.create_vault(name="ConflictVault")

        page_svc = PageService(uow_factory=uow_factory, default_actor=actor)
        page, _ = await page_svc.create_page(
            vault_id=vault.vault_id,
            page_key="beta",
            page_type=PageType.CONCEPT,
            title="Beta",
            content=b"Beta content",
        )

        branch_svc = BranchService(uow_factory=uow_factory, default_actor=actor)
        wb = await branch_svc.create_workbook(
            vault_id=vault.vault_id,
            name="Conflicting Branch",
            purpose=BranchPurpose.MANUAL,
        )

        # Branch modifies first (creates v2, branch head base=v1)
        await page_svc.update_page(
            page_id=page.page_id,
            expected_version=Version(1),
            title="Beta Branch",
            workbook_id=wb.workbook_id,
        )
        # Canonical modifies (creates v3, canonical head=3)
        await page_svc.update_page(
            page_id=page.page_id,
            expected_version=Version(2),
            title="Beta Canonical",
        )

        merge_svc = MergeService(uow_factory=uow_factory, default_actor=actor)
        proposal = await merge_svc.propose_merge(wb.workbook_id)

        # Get conflicts from DB
        uow = uow_factory()
        async with uow:
            conflicts = await uow.merge_conflicts.list_by_merge(proposal.merge_id)
            await uow.rollback()

        return merge_svc, proposal, conflicts, vault, wb

    async def test_resolve_conflict(self, uow_factory, actor):
        merge_svc, proposal, conflicts, _, _ = await self._setup_conflicted(uow_factory, actor)

        assert len(conflicts) == 1
        conflict = conflicts[0]
        assert conflict.resolution is None

        resolved = await merge_svc.resolve_conflict(
            conflict.conflict_id, MergeResolution.ACCEPT_BRANCH
        )
        assert resolved.resolution == MergeResolution.ACCEPT_BRANCH

    async def test_resolve_conflict_not_found_raises(self, uow_factory, actor, id_gen):
        merge_svc = MergeService(uow_factory=uow_factory, default_actor=actor)

        fake_id = id_gen.conflict_id()
        with pytest.raises(EntityNotFoundError, match="MergeConflict not found"):
            await merge_svc.resolve_conflict(fake_id, MergeResolution.ACCEPT_BRANCH)


@pytest.mark.asyncio
class TestMergeServiceExecute:
    """Tests for execute_merge."""

    async def _setup_clean_merge(self, uow_factory, actor):
        """Create a clean merge scenario and return everything needed."""
        vault_svc = VaultService(uow_factory=uow_factory, default_actor=actor)
        vault = await vault_svc.create_vault(name="ExecVault")

        page_svc = PageService(uow_factory=uow_factory, default_actor=actor)
        page, _ = await page_svc.create_page(
            vault_id=vault.vault_id,
            page_key="gamma",
            page_type=PageType.CONCEPT,
            title="Gamma",
            content=b"Gamma content",
        )

        branch_svc = BranchService(uow_factory=uow_factory, default_actor=actor)
        wb = await branch_svc.create_workbook(
            vault_id=vault.vault_id,
            name="Clean Merge Branch",
            purpose=BranchPurpose.RESEARCH,
        )

        # Modify on branch only
        await page_svc.update_page(
            page_id=page.page_id,
            expected_version=Version(1),
            title="Gamma Updated",
            content=b"Gamma updated on branch",
            workbook_id=wb.workbook_id,
        )

        merge_svc = MergeService(uow_factory=uow_factory, default_actor=actor)
        proposal = await merge_svc.propose_merge(wb.workbook_id)
        assert proposal.verdict == MergeVerdict.CLEAN

        return merge_svc, proposal, vault, wb, page

    async def test_execute_clean_merge(self, uow_factory, actor, sqlite_db):
        merge_svc, proposal, vault, wb, page = await self._setup_clean_merge(uow_factory, actor)

        revision = await merge_svc.execute_merge(proposal.merge_id)

        # New revision was created
        assert revision.vault_id == vault.vault_id
        assert revision.parent_revision_id == vault.head_revision_id
        assert "Clean Merge Branch" in revision.summary

        # Verify canonical page head was updated
        cursor = await sqlite_db.execute(
            "SELECT head_version FROM fb_canonical_heads WHERE entity_id = ?",
            (str(page.page_id),),
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row["head_version"] == 3  # v1=canonical, v2=branch, v3=merge result

        # Verify vault head was updated
        cursor = await sqlite_db.execute(
            "SELECT head_revision_id FROM fb_vaults WHERE vault_id = ?",
            (str(vault.vault_id),),
        )
        row = await cursor.fetchone()
        assert row["head_revision_id"] == str(revision.revision_id)

    async def test_execute_merge_sets_workbook_merged(self, uow_factory, actor, sqlite_db):
        merge_svc, proposal, vault, wb, page = await self._setup_clean_merge(uow_factory, actor)

        await merge_svc.execute_merge(proposal.merge_id)

        cursor = await sqlite_db.execute(
            "SELECT status FROM fb_workbooks WHERE workbook_id = ?",
            (str(wb.workbook_id),),
        )
        row = await cursor.fetchone()
        assert row["status"] == "merged"

    async def test_execute_merge_emits_workbook_merged_event(self, uow_factory, actor, sqlite_db):
        merge_svc, proposal, vault, wb, page = await self._setup_clean_merge(uow_factory, actor)

        await merge_svc.execute_merge(proposal.merge_id)

        cursor = await sqlite_db.execute(
            "SELECT event_type FROM fb_domain_events WHERE event_type = 'workbook.merged'"
        )
        row = await cursor.fetchone()
        assert row is not None

    async def test_stale_merge_detection(self, uow_factory, actor):
        """If the vault head moves between propose and execute, raise StaleMergeError."""
        vault_svc = VaultService(uow_factory=uow_factory, default_actor=actor)
        vault = await vault_svc.create_vault(name="StaleVault")

        page_svc = PageService(uow_factory=uow_factory, default_actor=actor)
        page, _ = await page_svc.create_page(
            vault_id=vault.vault_id,
            page_key="delta",
            page_type=PageType.CONCEPT,
            title="Delta",
            content=b"Delta content",
        )

        branch_svc = BranchService(uow_factory=uow_factory, default_actor=actor)
        wb = await branch_svc.create_workbook(
            vault_id=vault.vault_id,
            name="Stale Branch",
            purpose=BranchPurpose.MANUAL,
        )

        # Modify on branch
        await page_svc.update_page(
            page_id=page.page_id,
            expected_version=Version(1),
            title="Delta Branch",
            workbook_id=wb.workbook_id,
        )

        merge_svc = MergeService(uow_factory=uow_factory, default_actor=actor)
        proposal = await merge_svc.propose_merge(wb.workbook_id)

        # Now create ANOTHER workbook, modify, and merge it -- moving the vault head
        wb2 = await branch_svc.create_workbook(
            vault_id=vault.vault_id,
            name="Competing Branch",
            purpose=BranchPurpose.MANUAL,
        )

        # Create a second page on the competing branch and merge it
        page2, _ = await page_svc.create_page(
            vault_id=vault.vault_id,
            page_key="epsilon",
            page_type=PageType.CONCEPT,
            title="Epsilon",
            content=b"Epsilon content",
            workbook_id=wb2.workbook_id,
        )

        proposal2 = await merge_svc.propose_merge(wb2.workbook_id)
        await merge_svc.execute_merge(proposal2.merge_id)

        # Now try to execute the original merge -- vault head has moved
        with pytest.raises(StaleMergeError):
            await merge_svc.execute_merge(proposal.merge_id)

    async def test_execute_merge_with_unresolved_conflicts_raises(self, uow_factory, actor):
        """Cannot execute a conflicted merge until all conflicts are resolved."""
        vault_svc = VaultService(uow_factory=uow_factory, default_actor=actor)
        vault = await vault_svc.create_vault(name="UnresolvedVault")

        page_svc = PageService(uow_factory=uow_factory, default_actor=actor)
        page, _ = await page_svc.create_page(
            vault_id=vault.vault_id,
            page_key="zeta",
            page_type=PageType.CONCEPT,
            title="Zeta",
            content=b"Zeta content",
        )

        branch_svc = BranchService(uow_factory=uow_factory, default_actor=actor)
        wb = await branch_svc.create_workbook(
            vault_id=vault.vault_id,
            name="Unresolved",
            purpose=BranchPurpose.MANUAL,
        )

        # Both modify: branch first, then canonical
        await page_svc.update_page(
            page_id=page.page_id,
            expected_version=Version(1),
            title="Zeta Branch",
            workbook_id=wb.workbook_id,
        )
        await page_svc.update_page(
            page_id=page.page_id,
            expected_version=Version(2),
            title="Zeta Canonical",
        )

        merge_svc = MergeService(uow_factory=uow_factory, default_actor=actor)
        proposal = await merge_svc.propose_merge(wb.workbook_id)
        assert proposal.verdict == MergeVerdict.CONFLICTED

        with pytest.raises(UnresolvedConflictsError):
            await merge_svc.execute_merge(proposal.merge_id)

    async def test_execute_merge_after_resolving_conflicts(self, uow_factory, actor, sqlite_db):
        """Resolving all conflicts then executing should succeed."""
        vault_svc = VaultService(uow_factory=uow_factory, default_actor=actor)
        vault = await vault_svc.create_vault(name="ResolvedVault")

        page_svc = PageService(uow_factory=uow_factory, default_actor=actor)
        page, _ = await page_svc.create_page(
            vault_id=vault.vault_id,
            page_key="eta",
            page_type=PageType.CONCEPT,
            title="Eta",
            content=b"Eta content",
        )

        branch_svc = BranchService(uow_factory=uow_factory, default_actor=actor)
        wb = await branch_svc.create_workbook(
            vault_id=vault.vault_id,
            name="Resolved",
            purpose=BranchPurpose.MANUAL,
        )

        # Both modify: branch first, then canonical
        await page_svc.update_page(
            page_id=page.page_id,
            expected_version=Version(1),
            title="Eta Branch",
            workbook_id=wb.workbook_id,
        )
        await page_svc.update_page(
            page_id=page.page_id,
            expected_version=Version(2),
            title="Eta Canonical",
        )

        merge_svc = MergeService(uow_factory=uow_factory, default_actor=actor)
        proposal = await merge_svc.propose_merge(wb.workbook_id)
        assert proposal.verdict == MergeVerdict.CONFLICTED

        # Get and resolve all conflicts
        uow = uow_factory()
        async with uow:
            conflicts = await uow.merge_conflicts.list_by_merge(proposal.merge_id)
            await uow.rollback()

        for conflict in conflicts:
            await merge_svc.resolve_conflict(conflict.conflict_id, MergeResolution.ACCEPT_BRANCH)

        # Now execute should succeed
        revision = await merge_svc.execute_merge(proposal.merge_id)
        assert revision.vault_id == vault.vault_id

    async def test_execute_merge_proposal_not_found_raises(self, uow_factory, actor, id_gen):
        merge_svc = MergeService(uow_factory=uow_factory, default_actor=actor)

        fake_id = id_gen.merge_id()
        with pytest.raises(EntityNotFoundError, match="MergeProposal not found"):
            await merge_svc.execute_merge(fake_id)

    async def test_execute_merge_accept_canonical_skips_branch_change(
        self, uow_factory, actor, sqlite_db
    ):
        """When a conflict is resolved as ACCEPT_CANONICAL, the branch change is skipped."""
        vault_svc = VaultService(uow_factory=uow_factory, default_actor=actor)
        vault = await vault_svc.create_vault(name="CanonicalWinsVault")

        page_svc = PageService(uow_factory=uow_factory, default_actor=actor)
        page, _ = await page_svc.create_page(
            vault_id=vault.vault_id,
            page_key="theta",
            page_type=PageType.CONCEPT,
            title="Theta Original",
            content=b"Theta content",
        )

        branch_svc = BranchService(uow_factory=uow_factory, default_actor=actor)
        wb = await branch_svc.create_workbook(
            vault_id=vault.vault_id,
            name="Canonical Wins",
            purpose=BranchPurpose.MANUAL,
        )

        # Both modify: branch first, then canonical
        await page_svc.update_page(
            page_id=page.page_id,
            expected_version=Version(1),
            title="Theta Branch",
            workbook_id=wb.workbook_id,
        )
        await page_svc.update_page(
            page_id=page.page_id,
            expected_version=Version(2),
            title="Theta Canonical",
        )

        merge_svc = MergeService(uow_factory=uow_factory, default_actor=actor)
        proposal = await merge_svc.propose_merge(wb.workbook_id)

        # Resolve as ACCEPT_CANONICAL
        uow = uow_factory()
        async with uow:
            conflicts = await uow.merge_conflicts.list_by_merge(proposal.merge_id)
            await uow.rollback()

        for conflict in conflicts:
            await merge_svc.resolve_conflict(conflict.conflict_id, MergeResolution.ACCEPT_CANONICAL)

        # Execute merge
        await merge_svc.execute_merge(proposal.merge_id)

        # Canonical head should still be 3 (the canonical update), not bumped further
        cursor = await sqlite_db.execute(
            "SELECT head_version FROM fb_canonical_heads WHERE entity_id = ?",
            (str(page.page_id),),
        )
        row = await cursor.fetchone()
        assert row["head_version"] == 3  # canonical v3, branch was skipped
