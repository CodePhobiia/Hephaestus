"""MergeService — propose, resolve conflicts, and execute merges."""

from __future__ import annotations

from collections.abc import Callable

from hephaestus.forgebase.domain.conflicts import ConflictCheckResult, detect_entity_conflict
from hephaestus.forgebase.domain.enums import (
    EntityKind,
    MergeResolution,
    MergeVerdict,
    WorkbookStatus,
)
from hephaestus.forgebase.domain.models import (
    ClaimVersion,
    LinkVersion,
    MergeConflict,
    MergeProposal,
    PageVersion,
    SourceVersion,
    VaultRevision,
)
from hephaestus.forgebase.domain.values import ActorRef, EntityId, Version
from hephaestus.forgebase.repository.uow import AbstractUnitOfWork
from hephaestus.forgebase.service.exceptions import (
    EntityNotFoundError,
    StaleMergeError,
    UnresolvedConflictsError,
)


class MergeService:
    """Command service for merge lifecycle: propose, resolve, execute."""

    def __init__(
        self,
        uow_factory: Callable[[], AbstractUnitOfWork],
        default_actor: ActorRef,
    ) -> None:
        self._uow_factory = uow_factory
        self._default_actor = default_actor

    async def propose_merge(
        self,
        workbook_id: EntityId,
        *,
        actor: ActorRef | None = None,
    ) -> MergeProposal:
        """Analyze branch changes and create a merge proposal.

        For each branch-local entity head (pages, claims, links, sources),
        compare the base version, branch version, and canonical version to
        detect conflicts.

        Returns a MergeProposal with verdict CLEAN or CONFLICTED.
        """
        actor = actor or self._default_actor
        uow = self._uow_factory()
        async with uow:
            workbook = await uow.workbooks.get(workbook_id)
            if workbook is None:
                raise EntityNotFoundError("Workbook", str(workbook_id))

            vault = await uow.vaults.get(workbook.vault_id)
            if vault is None:
                raise EntityNotFoundError("Vault", str(workbook.vault_id))

            now = uow.clock.now()
            merge_id = uow.id_generator.merge_id()
            base_revision_id = workbook.base_revision_id
            target_revision_id = vault.head_revision_id

            # Collect all branch heads
            page_heads = await uow.workbooks.list_page_heads(workbook_id)
            claim_heads = await uow.workbooks.list_claim_heads(workbook_id)
            link_heads = await uow.workbooks.list_link_heads(workbook_id)
            source_heads = await uow.workbooks.list_source_heads(workbook_id)

            conflicts: list[MergeConflict] = []
            has_conflict = False

            def _check_and_record(
                entity_kind: EntityKind,
                entity_id: EntityId,
                base_version: Version,
                branch_version: Version,
                canonical_ver_num: int | None,
            ) -> None:
                nonlocal has_conflict
                # No canonical head = entity born on branch, always clean
                if canonical_ver_num is None:
                    return
                canonical_version = Version(canonical_ver_num)
                result = detect_entity_conflict(
                    base_version=base_version,
                    branch_version=branch_version,
                    canonical_version=canonical_version,
                )
                if result == ConflictCheckResult.CONFLICTED:
                    has_conflict = True
                    conflicts.append(
                        MergeConflict(
                            conflict_id=uow.id_generator.conflict_id(),
                            merge_id=merge_id,
                            entity_kind=entity_kind,
                            entity_id=entity_id,
                            base_version=base_version,
                            branch_version=branch_version,
                            canonical_version=canonical_version,
                        )
                    )

            # Check page heads
            for ph in page_heads:
                canonical_ver_num = await uow.vaults.get_canonical_page_head(
                    workbook.vault_id, ph.page_id
                )
                _check_and_record(
                    EntityKind.PAGE,
                    ph.page_id,
                    ph.base_version,
                    ph.head_version,
                    canonical_ver_num,
                )

            # Check claim heads
            for ch in claim_heads:
                canonical_ver_num = await uow.vaults.get_canonical_claim_head(
                    workbook.vault_id, ch.claim_id
                )
                _check_and_record(
                    EntityKind.CLAIM,
                    ch.claim_id,
                    ch.base_version,
                    ch.head_version,
                    canonical_ver_num,
                )

            # Check link heads
            for lh in link_heads:
                canonical_ver_num = await uow.vaults.get_canonical_link_head(
                    workbook.vault_id, lh.link_id
                )
                _check_and_record(
                    EntityKind.LINK,
                    lh.link_id,
                    lh.base_version,
                    lh.head_version,
                    canonical_ver_num,
                )

            # Check source heads
            for sh in source_heads:
                canonical_ver_num = await uow.vaults.get_canonical_source_head(
                    workbook.vault_id, sh.source_id
                )
                _check_and_record(
                    EntityKind.SOURCE,
                    sh.source_id,
                    sh.base_version,
                    sh.head_version,
                    canonical_ver_num,
                )

            verdict = MergeVerdict.CONFLICTED if has_conflict else MergeVerdict.CLEAN

            proposal = MergeProposal(
                merge_id=merge_id,
                workbook_id=workbook_id,
                vault_id=workbook.vault_id,
                base_revision_id=base_revision_id,
                target_revision_id=target_revision_id,
                verdict=verdict,
                resulting_revision=None,
                proposed_at=now,
                resolved_at=None,
                proposed_by=actor,
            )

            await uow.merge_proposals.create(proposal)
            for conflict in conflicts:
                await uow.merge_conflicts.create(conflict)

            # Emit events
            uow.record_event(
                uow.event_factory.create(
                    event_type="merge.proposed",
                    aggregate_type="merge",
                    aggregate_id=merge_id,
                    vault_id=workbook.vault_id,
                    payload={
                        "workbook_id": str(workbook_id),
                        "verdict": verdict.value,
                        "conflict_count": len(conflicts),
                    },
                    actor=actor,
                    workbook_id=workbook_id,
                )
            )

            for conflict in conflicts:
                uow.record_event(
                    uow.event_factory.create(
                        event_type="merge.conflict_detected",
                        aggregate_type="merge",
                        aggregate_id=merge_id,
                        vault_id=workbook.vault_id,
                        payload={
                            "conflict_id": str(conflict.conflict_id),
                            "entity_kind": conflict.entity_kind.value,
                            "entity_id": str(conflict.entity_id),
                        },
                        actor=actor,
                        workbook_id=workbook_id,
                    )
                )

            await uow.commit()

        return proposal

    async def resolve_conflict(
        self,
        conflict_id: EntityId,
        resolution: MergeResolution,
        *,
        actor: ActorRef | None = None,
    ) -> MergeConflict:
        """Resolve a single merge conflict.

        Returns the updated MergeConflict.
        """
        uow = self._uow_factory()
        async with uow:
            conflict = await uow.merge_conflicts.get(conflict_id)
            if conflict is None:
                raise EntityNotFoundError("MergeConflict", str(conflict_id))

            await uow.merge_conflicts.resolve(conflict_id, resolution)
            await uow.commit()

        conflict.resolution = resolution
        conflict.resolved_at = uow.clock.now()
        return conflict

    async def execute_merge(
        self,
        merge_id: EntityId,
        *,
        actor: ActorRef | None = None,
    ) -> VaultRevision:
        """Execute a merge: apply branch changes to canonical.

        Steps:
        1. Re-read canonical head -- if different from proposal target, raise StaleMergeError
        2. Verify all conflicts resolved
        3. For each clean branch change: create new canonical version, update canonical head
        4. For branch-born entities: adopt into canonical (same as clean changes)
        5. For tombstones: mark canonical entities as archived
        6. Create new VaultRevision
        7. Update vault.head_revision_id
        8. Set workbook.status = MERGED
        9. Emit events

        Returns the new VaultRevision.
        """
        actor = actor or self._default_actor
        uow = self._uow_factory()
        async with uow:
            proposal = await uow.merge_proposals.get(merge_id)
            if proposal is None:
                raise EntityNotFoundError("MergeProposal", str(merge_id))

            workbook = await uow.workbooks.get(proposal.workbook_id)
            if workbook is None:
                raise EntityNotFoundError("Workbook", str(proposal.workbook_id))

            vault = await uow.vaults.get(proposal.vault_id)
            if vault is None:
                raise EntityNotFoundError("Vault", str(proposal.vault_id))

            # Step 1: Stale check
            if vault.head_revision_id != proposal.target_revision_id:
                raise StaleMergeError(
                    str(merge_id),
                    str(proposal.target_revision_id),
                    str(vault.head_revision_id),
                )

            # Step 2: Check all conflicts resolved
            if proposal.verdict == MergeVerdict.CONFLICTED:
                conflicts = await uow.merge_conflicts.list_by_merge(merge_id)
                unresolved = [c for c in conflicts if c.resolution is None]
                if unresolved:
                    raise UnresolvedConflictsError(str(merge_id), len(unresolved))

            now = uow.clock.now()

            # Step 3-4: Apply branch changes to canonical
            # Process page heads
            page_heads = await uow.workbooks.list_page_heads(proposal.workbook_id)
            for ph in page_heads:
                # For conflicts resolved as ACCEPT_CANONICAL, skip
                if await self._is_resolved_as_canonical(uow, merge_id, EntityKind.PAGE, ph.page_id):
                    continue

                # Get the branch version data and create a new canonical version
                branch_version = await uow.pages.get_version(ph.page_id, ph.head_version)
                if branch_version is not None:
                    # Get the actual max version from the versions table
                    # (includes both branch and canonical versions)
                    current_head = await uow.pages.get_head_version(ph.page_id)
                    max_ver_num = current_head.version.number if current_head else 0
                    new_ver_num = max_ver_num + 1

                    new_pv = PageVersion(
                        page_id=ph.page_id,
                        version=Version(new_ver_num),
                        title=branch_version.title,
                        content_ref=branch_version.content_ref,
                        content_hash=branch_version.content_hash,
                        summary=branch_version.summary,
                        compiled_from=branch_version.compiled_from,
                        created_at=now,
                        created_by=actor,
                        schema_version=branch_version.schema_version,
                    )
                    await uow.pages.create_version(new_pv)
                    await uow.vaults.set_canonical_page_head(
                        proposal.vault_id, ph.page_id, new_ver_num
                    )

                    uow.record_event(
                        uow.event_factory.create(
                            event_type="page.version_created",
                            aggregate_type="page",
                            aggregate_id=ph.page_id,
                            aggregate_version=Version(new_ver_num),
                            vault_id=proposal.vault_id,
                            payload={
                                "title": branch_version.title,
                                "merged_from_workbook": str(proposal.workbook_id),
                            },
                            actor=actor,
                        )
                    )

            # Process claim heads
            claim_heads = await uow.workbooks.list_claim_heads(proposal.workbook_id)
            for ch in claim_heads:
                if await self._is_resolved_as_canonical(
                    uow, merge_id, EntityKind.CLAIM, ch.claim_id
                ):
                    continue

                branch_version = await uow.claims.get_version(ch.claim_id, ch.head_version)
                if branch_version is not None:
                    current_head = await uow.claims.get_head_version(ch.claim_id)
                    max_ver_num = current_head.version.number if current_head else 0
                    new_ver_num = max_ver_num + 1

                    new_cv = ClaimVersion(
                        claim_id=ch.claim_id,
                        version=Version(new_ver_num),
                        statement=branch_version.statement,
                        status=branch_version.status,
                        support_type=branch_version.support_type,
                        confidence=branch_version.confidence,
                        validated_at=branch_version.validated_at,
                        fresh_until=branch_version.fresh_until,
                        created_at=now,
                        created_by=actor,
                    )
                    await uow.claims.create_version(new_cv)
                    await uow.vaults.set_canonical_claim_head(
                        proposal.vault_id, ch.claim_id, new_ver_num
                    )

                    uow.record_event(
                        uow.event_factory.create(
                            event_type="claim.version_created",
                            aggregate_type="claim",
                            aggregate_id=ch.claim_id,
                            aggregate_version=Version(new_ver_num),
                            vault_id=proposal.vault_id,
                            payload={
                                "merged_from_workbook": str(proposal.workbook_id),
                            },
                            actor=actor,
                        )
                    )

            # Process link heads
            link_heads = await uow.workbooks.list_link_heads(proposal.workbook_id)
            for lh in link_heads:
                if await self._is_resolved_as_canonical(uow, merge_id, EntityKind.LINK, lh.link_id):
                    continue

                branch_version = await uow.links.get_version(lh.link_id, lh.head_version)
                if branch_version is not None:
                    current_head = await uow.links.get_head_version(lh.link_id)
                    max_ver_num = current_head.version.number if current_head else 0
                    new_ver_num = max_ver_num + 1

                    new_lv = LinkVersion(
                        link_id=lh.link_id,
                        version=Version(new_ver_num),
                        source_entity=branch_version.source_entity,
                        target_entity=branch_version.target_entity,
                        label=branch_version.label,
                        weight=branch_version.weight,
                        created_at=now,
                        created_by=actor,
                    )
                    await uow.links.create_version(new_lv)
                    await uow.vaults.set_canonical_link_head(
                        proposal.vault_id, lh.link_id, new_ver_num
                    )

                    uow.record_event(
                        uow.event_factory.create(
                            event_type="link.version_created",
                            aggregate_type="link",
                            aggregate_id=lh.link_id,
                            aggregate_version=Version(new_ver_num),
                            vault_id=proposal.vault_id,
                            payload={
                                "merged_from_workbook": str(proposal.workbook_id),
                            },
                            actor=actor,
                        )
                    )

            # Process source heads
            source_heads = await uow.workbooks.list_source_heads(proposal.workbook_id)
            for sh in source_heads:
                if await self._is_resolved_as_canonical(
                    uow, merge_id, EntityKind.SOURCE, sh.source_id
                ):
                    continue

                branch_version = await uow.sources.get_version(sh.source_id, sh.head_version)
                if branch_version is not None:
                    current_head = await uow.sources.get_head_version(sh.source_id)
                    max_ver_num = current_head.version.number if current_head else 0
                    new_ver_num = max_ver_num + 1

                    new_sv = SourceVersion(
                        source_id=sh.source_id,
                        version=Version(new_ver_num),
                        title=branch_version.title,
                        authors=branch_version.authors,
                        url=branch_version.url,
                        raw_artifact_ref=branch_version.raw_artifact_ref,
                        normalized_ref=branch_version.normalized_ref,
                        content_hash=branch_version.content_hash,
                        metadata=branch_version.metadata,
                        trust_tier=branch_version.trust_tier,
                        status=branch_version.status,
                        created_at=now,
                        created_by=actor,
                    )
                    await uow.sources.create_version(new_sv)
                    await uow.vaults.set_canonical_source_head(
                        proposal.vault_id, sh.source_id, new_ver_num
                    )

            # Step 5: Handle tombstones — mark canonical entities as archived
            # We set the canonical head to 0 to indicate archived status
            tombstones = await uow.workbooks.list_tombstones(proposal.workbook_id)
            for ts in tombstones:
                if ts.entity_kind == EntityKind.PAGE:
                    await uow.vaults.set_canonical_page_head(proposal.vault_id, ts.entity_id, 0)
                elif ts.entity_kind == EntityKind.CLAIM:
                    await uow.vaults.set_canonical_claim_head(proposal.vault_id, ts.entity_id, 0)
                elif ts.entity_kind == EntityKind.LINK:
                    await uow.vaults.set_canonical_link_head(proposal.vault_id, ts.entity_id, 0)
                elif ts.entity_kind == EntityKind.SOURCE:
                    await uow.vaults.set_canonical_source_head(proposal.vault_id, ts.entity_id, 0)

            # Step 6: Create new VaultRevision
            new_rev_id = uow.id_generator.revision_id()
            revision = VaultRevision(
                revision_id=new_rev_id,
                vault_id=proposal.vault_id,
                parent_revision_id=vault.head_revision_id,
                created_at=now,
                created_by=actor,
                causation_event_id=None,
                summary=f"Merge workbook {workbook.name}",
            )
            await uow.vaults.create_revision(revision)

            # Step 7: Update vault head
            await uow.vaults.update_head(proposal.vault_id, new_rev_id)

            # Step 8: Update merge proposal result
            await uow.merge_proposals.set_result(merge_id, new_rev_id)

            # Step 8: Set workbook status = MERGED
            await uow.workbooks.update_status(proposal.workbook_id, WorkbookStatus.MERGED)

            # Step 9: Emit events
            uow.record_event(
                uow.event_factory.create(
                    event_type="workbook.merged",
                    aggregate_type="workbook",
                    aggregate_id=proposal.workbook_id,
                    vault_id=proposal.vault_id,
                    payload={
                        "merge_id": str(merge_id),
                        "resulting_revision": str(new_rev_id),
                    },
                    actor=actor,
                    workbook_id=proposal.workbook_id,
                )
            )

            await uow.commit()

        return revision

    @staticmethod
    async def _is_resolved_as_canonical(
        uow: AbstractUnitOfWork,
        merge_id: EntityId,
        entity_kind: EntityKind,
        entity_id: EntityId,
    ) -> bool:
        """Check if a conflict for this entity was resolved as ACCEPT_CANONICAL."""
        conflicts = await uow.merge_conflicts.list_by_merge(merge_id)
        for c in conflicts:
            if (
                c.entity_kind == entity_kind
                and c.entity_id == entity_id
                and c.resolution == MergeResolution.ACCEPT_CANONICAL
            ):
                return True
        return False
