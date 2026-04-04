"""VaultSynthesizer — vault-wide synthesis orchestrator (Tier 2).

Reads active concept candidates, clusters them, synthesizes
canonical knowledge pages, and consumes dirty markers.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Callable

from hephaestus.forgebase.compiler.backend import CompilerBackend
from hephaestus.forgebase.compiler.dirty import DirtyTracker
from hephaestus.forgebase.compiler.models import ConceptEvidence, SynthesizedPage
from hephaestus.forgebase.compiler.policy import DEFAULT_POLICY, SynthesisPolicy
from hephaestus.forgebase.domain.enums import (
    CandidateStatus,
    ClaimStatus,
    LinkKind,
    PageType,
    SupportType,
)
from hephaestus.forgebase.domain.models import (
    BackendCallRecord,
    BranchClaimHead,
    BranchLinkHead,
    BranchPageHead,
    Claim,
    ClaimVersion,
    ConceptCandidate,
    Link,
    LinkVersion,
    Page,
    PageVersion,
    VaultSynthesisManifest,
)
from hephaestus.forgebase.domain.values import (
    ActorRef,
    ContentHash,
    EntityId,
    Version,
)
from hephaestus.forgebase.repository.uow import AbstractUnitOfWork


class VaultSynthesizer:
    """Vault-wide synthesis orchestrator (Tier 2).

    Reads active concept candidates, clusters them, synthesizes
    canonical knowledge pages, and consumes dirty markers.
    """

    def __init__(
        self,
        uow_factory: Callable[[], AbstractUnitOfWork],
        backend: CompilerBackend,
        default_actor: ActorRef,
        policy: SynthesisPolicy | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._backend = backend
        self._default_actor = default_actor
        self._policy = policy or DEFAULT_POLICY

    async def synthesize(
        self,
        vault_id: EntityId,
        workbook_id: EntityId | None = None,
        job_id: EntityId | None = None,
    ) -> VaultSynthesisManifest:
        """Execute vault-wide synthesis.

        Flow:
        1. Acquire UoW
        2. Read all ACTIVE ConceptCandidates for this vault/workbook
        3. Read all unconsumed SynthesisDirtyMarkers
        4. Cluster candidates by normalized_name
        5. For each cluster that meets promotion threshold:
           a. Gather ConceptEvidence from source claims
           b. Check if concept page already exists
           c. Call backend.synthesize_concept_page()
           d. NO-OP CHECK: skip if content hash unchanged
           e. Create/update concept page + synthesized claims + derivations
           f. Update candidate status -> PROMOTED
           g. Create links (RELATED_CONCEPT, BACKLINKs)
        6. Consume dirty markers
        7. Write VaultSynthesisManifest (join tables for associations)
        8. Emit events + commit
        """
        uow = self._uow_factory()
        async with uow:
            now = uow.clock.now()
            all_call_records: list[BackendCallRecord] = []

            # Resolve job_id
            effective_job_id = job_id or uow.id_generator.job_id()

            # ----- 2. Read state -----
            candidates = await uow.concept_candidates.list_active(
                vault_id, workbook_id,
            )

            # ----- 3. Read dirty markers -----
            dirty_tracker = DirtyTracker(
                uow.dirty_markers, uow.id_generator, uow.clock.now,
            )
            dirty_markers = await dirty_tracker.get_dirty_targets(
                vault_id, workbook_id,
            )

            # ----- 4. Cluster candidates by normalized_name -----
            clusters = _cluster_candidates(candidates, self._policy)

            # Tracking lists for manifest join tables
            pages_created: list[EntityId] = []
            pages_updated: list[EntityId] = []
            pages_unchanged: list[EntityId] = []
            promoted_candidates: list[ConceptCandidate] = []
            included_source_manifest_ids: list[EntityId] = []

            # Collect source manifest IDs from compiled candidates
            seen_jobs: set[str] = set()
            for c in candidates:
                job_raw = c.source_compile_job_id._raw
                if job_raw not in seen_jobs:
                    seen_jobs.add(job_raw)
                    src_manifest = await uow.compile_manifests.get_source_manifest_for(
                        c.source_id, c.source_version,
                    )
                    if src_manifest is not None:
                        included_source_manifest_ids.append(src_manifest.manifest_id)

            # ----- 5. Process each promotable cluster -----
            # Gather all other concept names for related_concepts context
            all_concept_names = list(clusters.keys())

            for normalized_name, cluster in clusters.items():
                if not _should_promote(cluster, self._policy):
                    continue

                # 5a. Gather evidence
                evidence = await self._gather_evidence(cluster, uow)

                # 5b. Determine related concepts (other cluster names)
                related_concepts = [
                    n for n in all_concept_names if n != normalized_name
                ][:self._policy.max_related_concepts]

                # Gather existing claims for this concept (if page exists)
                concept_page_key = f"concepts/{normalized_name}"
                existing_page = await uow.pages.find_by_key(vault_id, concept_page_key)
                existing_claims: list[str] = []
                if existing_page is not None:
                    page_claims = await uow.claims.list_by_page(existing_page.page_id)
                    for claim_obj in page_claims:
                        head = await uow.claims.get_head_version(claim_obj.claim_id)
                        if head:
                            existing_claims.append(head.statement)

                # 5c. Call backend
                synthesized_page, synth_call = await self._backend.synthesize_concept_page(
                    concept_name=normalized_name,
                    evidence=evidence,
                    existing_claims=existing_claims,
                    related_concepts=related_concepts,
                    policy=self._policy,
                )
                all_call_records.append(synth_call)

                # 5d. No-op check
                new_content = synthesized_page.content_markdown.encode("utf-8")
                new_hash = ContentHash.from_bytes(new_content)

                if existing_page is not None:
                    existing_ver = await uow.pages.get_head_version(
                        existing_page.page_id,
                    )
                    if existing_ver and existing_ver.content_hash == new_hash:
                        # Content unchanged -- skip version creation
                        pages_unchanged.append(existing_page.page_id)
                        # Still promote candidates even when content unchanged
                        for c in cluster:
                            await uow.concept_candidates.update_status(
                                c.candidate_id,
                                CandidateStatus.PROMOTED,
                                resolved_page_id=existing_page.page_id,
                            )
                            promoted_candidates.append(c)
                        continue

                # 5e. Create or update concept page
                concept_page = await self._persist_concept_page(
                    uow=uow,
                    vault_id=vault_id,
                    page_key=concept_page_key,
                    synthesized_page=synthesized_page,
                    new_hash=new_hash,
                    new_content=new_content,
                    existing_page=existing_page,
                    workbook_id=workbook_id,
                    now=now,
                    cluster=cluster,
                    pages_created=pages_created,
                    pages_updated=pages_updated,
                )

                # 5e (cont). Create synthesized claims
                await self._persist_synthesized_claims(
                    uow=uow,
                    vault_id=vault_id,
                    page_id=concept_page.page_id,
                    synthesized_page=synthesized_page,
                    workbook_id=workbook_id,
                    now=now,
                )

                # 5f. Update candidate status -> PROMOTED
                for c in cluster:
                    await uow.concept_candidates.update_status(
                        c.candidate_id,
                        CandidateStatus.PROMOTED,
                        resolved_page_id=concept_page.page_id,
                    )
                    promoted_candidates.append(c)

                # 5g. Create links
                await self._persist_synthesis_links(
                    uow=uow,
                    vault_id=vault_id,
                    concept_page_id=concept_page.page_id,
                    related_concepts=synthesized_page.related_concepts,
                    cluster=cluster,
                    workbook_id=workbook_id,
                    now=now,
                )

            # ----- 6. Consume dirty markers -----
            consumed_marker_ids: list[EntityId] = []
            for marker in dirty_markers:
                await dirty_tracker.consume(marker.marker_id, effective_job_id)
                consumed_marker_ids.append(marker.marker_id)

            # ----- 7. Write VaultSynthesisManifest -----
            vault_obj = await uow.vaults.get(vault_id)
            base_revision = vault_obj.head_revision_id if vault_obj else EntityId("rev_00000000000000000000000000")

            prompt_versions = {
                cr.prompt_id: cr.prompt_version for cr in all_call_records
            }

            manifest = VaultSynthesisManifest(
                manifest_id=uow.id_generator.generate("mfst"),
                vault_id=vault_id,
                workbook_id=workbook_id,
                job_id=effective_job_id,
                base_revision=base_revision,
                synthesis_policy_version=self._policy.policy_version,
                prompt_versions=prompt_versions,
                backend_calls=all_call_records,
                candidates_resolved=len(promoted_candidates),
                augmentor_calls=0,
                created_at=now,
            )
            await uow.compile_manifests.create_vault_manifest(manifest)

            # Join table associations
            seen_src_manifests: set[str] = set()
            for src_manifest_id in included_source_manifest_ids:
                if src_manifest_id._raw not in seen_src_manifests:
                    seen_src_manifests.add(src_manifest_id._raw)
                    await uow.compile_manifests.add_synthesis_source_manifest(
                        manifest.manifest_id, src_manifest_id,
                    )
            for page_id in pages_created:
                await uow.compile_manifests.add_synthesis_page_created(
                    manifest.manifest_id, page_id,
                )
            for page_id in pages_updated:
                await uow.compile_manifests.add_synthesis_page_updated(
                    manifest.manifest_id, page_id,
                )
            for marker_id in consumed_marker_ids:
                await uow.compile_manifests.add_synthesis_dirty_consumed(
                    manifest.manifest_id, marker_id,
                )

            # ----- 8. Emit events + commit -----
            uow.record_event(
                uow.event_factory.create(
                    event_type="compile.completed",
                    aggregate_type="vault",
                    aggregate_id=vault_id,
                    vault_id=vault_id,
                    workbook_id=workbook_id,
                    payload={
                        "manifest_id": str(manifest.manifest_id),
                        "candidates_resolved": manifest.candidates_resolved,
                        "pages_created": len(pages_created),
                        "pages_updated": len(pages_updated),
                        "pages_unchanged": len(pages_unchanged),
                        "dirty_markers_consumed": len(consumed_marker_ids),
                    },
                    actor=self._default_actor,
                )
            )

            await uow.commit()

        return manifest

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _gather_evidence(
        self,
        cluster: list[ConceptCandidate],
        uow: AbstractUnitOfWork,
    ) -> list[ConceptEvidence]:
        """Gather ConceptEvidence from each unique source in the cluster."""
        evidence_list: list[ConceptEvidence] = []
        seen_sources: set[str] = set()

        for candidate in cluster:
            src_raw = candidate.source_id._raw
            if src_raw in seen_sources:
                continue
            seen_sources.add(src_raw)

            source_ver = await uow.sources.get_version(
                candidate.source_id, candidate.source_version,
            )
            if source_ver is None:
                continue

            # Find claims from the source card page for this source
            source_slug = str(candidate.source_id).replace("_", "-").lower()
            page_key = f"source-cards/{source_slug}"
            page = await uow.pages.find_by_key(candidate.vault_id, page_key)

            claim_statements: list[str] = []
            if page is not None:
                page_claims = await uow.claims.list_by_page(page.page_id)
                for claim_obj in page_claims:
                    head = await uow.claims.get_head_version(claim_obj.claim_id)
                    if head:
                        claim_statements.append(head.statement)

            # Get candidate evidence segments
            candidate_evidence_records = await uow.candidate_evidence.list_by_candidate(
                candidate.candidate_id,
            )
            segments = [e.segment_ref for e in candidate_evidence_records]

            evidence_list.append(
                ConceptEvidence(
                    source_id=candidate.source_id,
                    source_title=source_ver.title,
                    claims=claim_statements,
                    segments=segments,
                )
            )

        return evidence_list

    async def _persist_concept_page(
        self,
        uow: AbstractUnitOfWork,
        vault_id: EntityId,
        page_key: str,
        synthesized_page: SynthesizedPage,
        new_hash: ContentHash,
        new_content: bytes,
        existing_page: Page | None,
        workbook_id: EntityId | None,
        now,
        cluster: list[ConceptCandidate],
        pages_created: list[EntityId],
        pages_updated: list[EntityId],
    ) -> Page:
        """Persist or update a concept page. Returns the Page entity."""
        compiled_from = list({c.source_id for c in cluster})

        if existing_page is not None:
            # Update existing page with new version
            existing_ver = await uow.pages.get_head_version(existing_page.page_id)
            new_ver_num = existing_ver.version.next() if existing_ver else Version(1)

            pending = await uow.content.stage(new_content, "text/markdown")
            blob_ref = pending.to_blob_ref()

            page_version = PageVersion(
                page_id=existing_page.page_id,
                version=new_ver_num,
                title=synthesized_page.title,
                content_ref=blob_ref,
                content_hash=new_hash,
                summary=f"Synthesized concept page: {synthesized_page.title}",
                compiled_from=compiled_from,
                created_at=now,
                created_by=self._default_actor,
            )
            await uow.pages.create_version(page_version)

            # Update head
            if workbook_id is not None:
                await uow.workbooks.set_page_head(
                    BranchPageHead(
                        workbook_id=workbook_id,
                        page_id=existing_page.page_id,
                        head_version=new_ver_num,
                        base_version=existing_ver.version if existing_ver else Version(1),
                    )
                )
            else:
                await uow.vaults.set_canonical_page_head(
                    vault_id, existing_page.page_id, new_ver_num.number,
                )

            pages_updated.append(existing_page.page_id)
            return existing_page
        else:
            # Create new page
            page_id = uow.id_generator.page_id()

            pending = await uow.content.stage(new_content, "text/markdown")
            blob_ref = pending.to_blob_ref()

            page = Page(
                page_id=page_id,
                vault_id=vault_id,
                page_type=PageType.CONCEPT,
                page_key=page_key,
                created_at=now,
            )

            page_version = PageVersion(
                page_id=page_id,
                version=Version(1),
                title=synthesized_page.title,
                content_ref=blob_ref,
                content_hash=new_hash,
                summary=f"Synthesized concept page: {synthesized_page.title}",
                compiled_from=compiled_from,
                created_at=now,
                created_by=self._default_actor,
            )

            await uow.pages.create(page, page_version)

            # Set head
            if workbook_id is not None:
                await uow.workbooks.set_page_head(
                    BranchPageHead(
                        workbook_id=workbook_id,
                        page_id=page_id,
                        head_version=Version(1),
                        base_version=Version(1),
                    )
                )
            else:
                await uow.vaults.set_canonical_page_head(vault_id, page_id, 1)

            pages_created.append(page_id)
            return page

    async def _persist_synthesized_claims(
        self,
        uow: AbstractUnitOfWork,
        vault_id: EntityId,
        page_id: EntityId,
        synthesized_page: SynthesizedPage,
        workbook_id: EntityId | None,
        now,
    ) -> list[Claim]:
        """Persist synthesized claims for a concept page."""
        created: list[Claim] = []

        for synth_claim in synthesized_page.claims:
            claim_id = uow.id_generator.claim_id()

            claim = Claim(
                claim_id=claim_id,
                vault_id=vault_id,
                page_id=page_id,
                created_at=now,
            )

            claim_version = ClaimVersion(
                claim_id=claim_id,
                version=Version(1),
                statement=synth_claim.statement,
                status=ClaimStatus.INFERRED,
                support_type=SupportType.SYNTHESIZED,
                confidence=synth_claim.confidence,
                validated_at=now,
                fresh_until=None,
                created_at=now,
                created_by=self._default_actor,
            )

            await uow.claims.create(claim, claim_version)

            # Set head
            if workbook_id is not None:
                await uow.workbooks.set_claim_head(
                    BranchClaimHead(
                        workbook_id=workbook_id,
                        claim_id=claim_id,
                        head_version=Version(1),
                        base_version=Version(1),
                    )
                )
            else:
                await uow.vaults.set_canonical_claim_head(vault_id, claim_id, 1)

            created.append(claim)

        return created

    async def _persist_synthesis_links(
        self,
        uow: AbstractUnitOfWork,
        vault_id: EntityId,
        concept_page_id: EntityId,
        related_concepts: list[str],
        cluster: list[ConceptCandidate],
        workbook_id: EntityId | None,
        now,
    ) -> list[Link]:
        """Persist BACKLINK and RELATED_CONCEPT links for a synthesized page."""
        created: list[Link] = []

        # Backlinks: concept page <- each source
        seen_sources: set[str] = set()
        for c in cluster:
            if c.source_id._raw in seen_sources:
                continue
            seen_sources.add(c.source_id._raw)

            link_id = uow.id_generator.link_id()
            link = Link(
                link_id=link_id,
                vault_id=vault_id,
                kind=LinkKind.BACKLINK,
                created_at=now,
            )
            link_version = LinkVersion(
                link_id=link_id,
                version=Version(1),
                source_entity=concept_page_id,
                target_entity=c.source_id,
                label="synthesized_from",
                weight=1.0,
                created_at=now,
                created_by=self._default_actor,
            )
            await uow.links.create(link, link_version)

            if workbook_id is not None:
                await uow.workbooks.set_link_head(
                    BranchLinkHead(
                        workbook_id=workbook_id,
                        link_id=link_id,
                        head_version=Version(1),
                        base_version=Version(1),
                    )
                )
            else:
                await uow.vaults.set_canonical_link_head(vault_id, link_id, 1)

            created.append(link)

        # RELATED_CONCEPT links to other concept pages that already exist
        for related_name in related_concepts:
            related_key = f"concepts/{related_name}"
            related_page = await uow.pages.find_by_key(vault_id, related_key)
            if related_page is None:
                continue

            link_id = uow.id_generator.link_id()
            link = Link(
                link_id=link_id,
                vault_id=vault_id,
                kind=LinkKind.RELATED_CONCEPT,
                created_at=now,
            )
            link_version = LinkVersion(
                link_id=link_id,
                version=Version(1),
                source_entity=concept_page_id,
                target_entity=related_page.page_id,
                label="related_concept",
                weight=0.5,
                created_at=now,
                created_by=self._default_actor,
            )
            await uow.links.create(link, link_version)

            if workbook_id is not None:
                await uow.workbooks.set_link_head(
                    BranchLinkHead(
                        workbook_id=workbook_id,
                        link_id=link_id,
                        head_version=Version(1),
                        base_version=Version(1),
                    )
                )
            else:
                await uow.vaults.set_canonical_link_head(vault_id, link_id, 1)

            created.append(link)

        return created


def _cluster_candidates(
    candidates: list[ConceptCandidate],
    policy: SynthesisPolicy,
) -> dict[str, list[ConceptCandidate]]:
    """Group candidates by normalized_name."""
    clusters: dict[str, list[ConceptCandidate]] = defaultdict(list)
    for c in candidates:
        clusters[c.normalized_name].append(c)
    return dict(clusters)


def _should_promote(
    cluster: list[ConceptCandidate],
    policy: SynthesisPolicy,
) -> bool:
    """Determine if a cluster deserves a canonical concept page."""
    unique_sources = len(set(c.source_id._raw for c in cluster))
    max_salience = max(c.salience for c in cluster)
    return (
        unique_sources >= policy.min_sources_for_promotion
        or max_salience >= policy.min_salience_single_source
    )
