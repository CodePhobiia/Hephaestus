"""SourceCompiler — per-source extraction orchestrator (Tier 1).

Turns one normalized source into structured knowledge primitives:
source card page, claims, concept candidates, dirty markers, and manifest.
"""

from __future__ import annotations

from collections.abc import Callable

from hephaestus.forgebase.compiler.backend import CompilerBackend
from hephaestus.forgebase.compiler.dirty import DirtyTracker
from hephaestus.forgebase.compiler.models import (
    ExtractedClaim,
    ExtractedConcept,
    SourceCardContent,
)
from hephaestus.forgebase.domain.enums import (
    CandidateStatus,
    ClaimStatus,
    DirtyTargetKind,
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
    ClaimSupport,
    ClaimVersion,
    ConceptCandidate,
    ConceptCandidateEvidence,
    Link,
    LinkVersion,
    Page,
    PageVersion,
    SourceCompileManifest,
)
from hephaestus.forgebase.domain.values import (
    ActorRef,
    ContentHash,
    EntityId,
    Version,
)
from hephaestus.forgebase.repository.uow import AbstractUnitOfWork


class SourceCompiler:
    """Per-source extraction orchestrator (Tier 1).

    Turns one normalized source into structured knowledge primitives:
    source card page, claims, concept candidates, dirty markers, and manifest.
    """

    def __init__(
        self,
        uow_factory: Callable[[], AbstractUnitOfWork],
        backend: CompilerBackend,
        default_actor: ActorRef,
        policy_version: str = "1.0.0",
    ) -> None:
        self._uow_factory = uow_factory
        self._backend = backend
        self._default_actor = default_actor
        self._policy_version = policy_version

    async def compile_source(
        self,
        source_id: EntityId,
        source_version: Version,
        vault_id: EntityId,
        workbook_id: EntityId | None = None,
        job_id: EntityId | None = None,
    ) -> SourceCompileManifest:
        """Execute full Tier 1 compilation for one source.

        Flow:
        1. Acquire UoW
        2. Read normalized source content from ContentStore
        3. Extract claims (backend.extract_claims)
        4. Extract concepts (backend.extract_concepts)
        5. Generate source card (backend.generate_source_card) -- AFTER claims + concepts
        6. Persist source card page (create or update with no-op check)
        7. Persist claims (ClaimVersion with status=SUPPORTED, support_type=DIRECT)
        8. Persist ClaimSupports linking claims to source
        9. Persist ConceptCandidates (status=ACTIVE)
        10. Persist ConceptCandidateEvidence
        11. Persist source-local Links (backlinks)
        12. Mark dirty for Tier 2 (upsert SynthesisDirtyMarkers)
        13. Write SourceCompileManifest
        14. Emit events + commit
        """
        uow = self._uow_factory()
        async with uow:
            now = uow.clock.now()
            all_call_records: list[BackendCallRecord] = []

            # Resolve job_id — use provided or generate one
            effective_job_id = job_id or uow.id_generator.job_id()

            # ----- 2. Read normalized source content -----
            source_ver = await uow.sources.get_version(source_id, source_version)
            if source_ver is None or source_ver.normalized_ref is None:
                raise ValueError(f"Source {source_id} v{source_version} has no normalized content")
            normalized_bytes = await uow.content.read(source_ver.normalized_ref)
            source_text = normalized_bytes.decode("utf-8")

            source_metadata = {
                "source_id": str(source_id),
                "source_version": source_version.number,
                "title": source_ver.title,
                "authors": source_ver.authors,
                "url": source_ver.url,
            }

            # ----- 3. Extract claims -----
            claims, claims_call = await self._backend.extract_claims(source_text, source_metadata)
            all_call_records.append(claims_call)

            # ----- 4. Extract concepts -----
            concepts, concepts_call = await self._backend.extract_concepts(
                source_text, source_metadata
            )
            all_call_records.append(concepts_call)

            # ----- 5. Generate source card (AFTER claims + concepts) -----
            card, card_call = await self._backend.generate_source_card(
                source_text, source_metadata, claims, concepts
            )
            all_call_records.append(card_call)

            # ----- 6. Persist source card page -----
            source_card_page, source_card_is_new = await self._persist_source_card(
                uow,
                vault_id,
                source_id,
                source_ver.title,
                card,
                workbook_id,
                now,
                [source_id],
            )

            # ----- 7+8. Persist claims + ClaimSupports -----
            claims_created = await self._persist_claims(
                uow,
                vault_id,
                source_card_page.page_id,
                source_id,
                claims,
                workbook_id,
                now,
            )

            # ----- 9+10. Persist concept candidates + evidence -----
            candidates_created = await self._persist_concept_candidates(
                uow,
                vault_id,
                source_id,
                source_version,
                effective_job_id,
                concepts,
                workbook_id,
                now,
            )

            # ----- 11. Persist source-local links (backlink: source card <- source) -----
            links_created = await self._persist_backlinks(
                uow,
                vault_id,
                source_card_page.page_id,
                source_id,
                workbook_id,
                now,
            )

            # ----- 12. Mark dirty for Tier 2 -----
            dirty_tracker = DirtyTracker(
                uow.dirty_markers,
                uow.id_generator,
                uow.clock.now,
            )
            for candidate in candidates_created:
                await dirty_tracker.mark_dirty(
                    vault_id=vault_id,
                    target_kind=DirtyTargetKind.CONCEPT,
                    target_key=candidate.normalized_name,
                    dirtied_by_source=source_id,
                    dirtied_by_job=effective_job_id,
                    workbook_id=workbook_id,
                )

            # ----- 13. Write SourceCompileManifest -----
            prompt_versions = {cr.prompt_id: cr.prompt_version for cr in all_call_records}

            manifest = SourceCompileManifest(
                manifest_id=uow.id_generator.generate("mfst"),
                vault_id=vault_id,
                workbook_id=workbook_id,
                source_id=source_id,
                source_version=source_version,
                job_id=effective_job_id,
                compiler_policy_version=self._policy_version,
                prompt_versions=prompt_versions,
                backend_calls=all_call_records,
                claim_count=len(claims_created),
                concept_count=len(candidates_created),
                relationship_count=len(links_created),
                source_content_hash=ContentHash.from_bytes(normalized_bytes),
                created_at=now,
            )
            await uow.compile_manifests.create_source_manifest(manifest)

            # ----- 14. Emit events + commit -----
            uow.record_event(
                uow.event_factory.create(
                    event_type="compile.completed",
                    aggregate_type="source",
                    aggregate_id=source_id,
                    aggregate_version=source_version,
                    vault_id=vault_id,
                    workbook_id=workbook_id,
                    payload={
                        "manifest_id": str(manifest.manifest_id),
                        "claim_count": manifest.claim_count,
                        "concept_count": manifest.concept_count,
                        "relationship_count": manifest.relationship_count,
                    },
                    actor=self._default_actor,
                )
            )

            await uow.commit()

        return manifest

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _persist_source_card(
        self,
        uow: AbstractUnitOfWork,
        vault_id: EntityId,
        source_id: EntityId,
        source_title: str,
        card: SourceCardContent,
        workbook_id: EntityId | None,
        now,
        compiled_from: list[EntityId],
    ) -> tuple[Page, bool]:
        """Persist or update the source card page. Returns (page, is_new)."""
        source_slug = str(source_id).replace("_", "-").lower()
        page_key = f"source-cards/{source_slug}"

        rendered = _render_source_card(card, source_title)
        new_content = rendered.encode("utf-8")
        new_hash = ContentHash.from_bytes(new_content)

        existing_page = await uow.pages.find_by_key(vault_id, page_key)

        if existing_page is not None:
            # Check if content changed (no-op check)
            existing_version = await uow.pages.get_head_version(existing_page.page_id)
            if existing_version and existing_version.content_hash == new_hash:
                # No-op: content unchanged — skip version creation
                return existing_page, False

            # Update existing page with new version
            new_ver_num = existing_version.version.next() if existing_version else Version(1)
            pending = await uow.content.stage(new_content, "text/markdown")
            blob_ref = pending.to_blob_ref()

            page_version = PageVersion(
                page_id=existing_page.page_id,
                version=new_ver_num,
                title=f"Source: {source_title}",
                content_ref=blob_ref,
                content_hash=new_hash,
                summary=f"Source card for {source_title}",
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
                        base_version=existing_version.version if existing_version else Version(1),
                    )
                )
            else:
                await uow.vaults.set_canonical_page_head(
                    vault_id,
                    existing_page.page_id,
                    new_ver_num.number,
                )

            return existing_page, False
        else:
            # Create new page
            page_id = uow.id_generator.page_id()
            pending = await uow.content.stage(new_content, "text/markdown")
            blob_ref = pending.to_blob_ref()

            page = Page(
                page_id=page_id,
                vault_id=vault_id,
                page_type=PageType.SOURCE_CARD,
                page_key=page_key,
                created_at=now,
            )

            page_version = PageVersion(
                page_id=page_id,
                version=Version(1),
                title=f"Source: {source_title}",
                content_ref=blob_ref,
                content_hash=new_hash,
                summary=f"Source card for {source_title}",
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

            return page, True

    async def _persist_claims(
        self,
        uow: AbstractUnitOfWork,
        vault_id: EntityId,
        page_id: EntityId,
        source_id: EntityId,
        extracted_claims: list[ExtractedClaim],
        workbook_id: EntityId | None,
        now,
    ) -> list[Claim]:
        """Persist claims and their supports. Returns list of created Claims."""
        created: list[Claim] = []

        for extracted_claim in extracted_claims:
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
                statement=extracted_claim.statement,
                status=ClaimStatus.SUPPORTED,
                support_type=SupportType.DIRECT,
                confidence=extracted_claim.confidence,
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

            # Create ClaimSupport linking claim -> source
            support = ClaimSupport(
                support_id=uow.id_generator.support_id(),
                claim_id=claim_id,
                source_id=source_id,
                source_segment=extracted_claim.segment_ref.preview_text,
                strength=extracted_claim.confidence,
                created_at=now,
                created_by=self._default_actor,
            )
            await uow.claim_supports.create(support)

            created.append(claim)

        return created

    async def _persist_concept_candidates(
        self,
        uow: AbstractUnitOfWork,
        vault_id: EntityId,
        source_id: EntityId,
        source_version: Version,
        job_id: EntityId,
        extracted_concepts: list[ExtractedConcept],
        workbook_id: EntityId | None,
        now,
    ) -> list[ConceptCandidate]:
        """Persist concept candidates and their evidence. Returns created list."""
        created: list[ConceptCandidate] = []

        for extracted_concept in extracted_concepts:
            candidate = ConceptCandidate(
                candidate_id=uow.id_generator.generate("cand"),
                vault_id=vault_id,
                workbook_id=workbook_id,
                source_id=source_id,
                source_version=source_version,
                source_compile_job_id=job_id,
                name=extracted_concept.name,
                normalized_name=extracted_concept.name.lower().strip(),
                aliases=extracted_concept.aliases,
                candidate_kind=extracted_concept.kind,
                confidence=extracted_concept.salience,
                salience=extracted_concept.salience,
                status=CandidateStatus.ACTIVE,
                resolved_page_id=None,
                compiler_policy_version=self._policy_version,
                created_at=now,
            )
            await uow.concept_candidates.create(candidate)

            # Create evidence records
            for seg_ref in extracted_concept.evidence_segments:
                evidence = ConceptCandidateEvidence(
                    evidence_id=uow.id_generator.generate("cevd"),
                    candidate_id=candidate.candidate_id,
                    segment_ref=seg_ref,
                    role="USAGE",
                    created_at=now,
                )
                await uow.candidate_evidence.create(evidence)

            created.append(candidate)

        return created

    async def _persist_backlinks(
        self,
        uow: AbstractUnitOfWork,
        vault_id: EntityId,
        page_id: EntityId,
        source_id: EntityId,
        workbook_id: EntityId | None,
        now,
    ) -> list[Link]:
        """Persist source-local backlinks. Returns created links."""
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
            source_entity=page_id,
            target_entity=source_id,
            label="compiled_from",
            weight=1.0,
            created_at=now,
            created_by=self._default_actor,
        )

        await uow.links.create(link, link_version)

        # Set head
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

        return [link]


def _render_source_card(card: SourceCardContent, source_title: str) -> str:
    """Render a SourceCardContent into markdown."""
    lines = [f"# Source: {source_title}", "", "## Summary", "", card.summary, ""]
    if card.key_claims:
        lines += ["## Key Claims", ""]
        for claim in card.key_claims:
            lines.append(f"- {claim}")
        lines.append("")
    if card.methods:
        lines += ["## Methods", ""]
        for method in card.methods:
            lines.append(f"- {method}")
        lines.append("")
    if card.limitations:
        lines += ["## Limitations", ""]
        for lim in card.limitations:
            lines.append(f"- {lim}")
        lines.append("")
    lines += ["## Evidence Quality", "", card.evidence_quality, ""]
    if card.concepts_mentioned:
        lines += ["## Concepts Mentioned", ""]
        for concept in card.concepts_mentioned:
            lines.append(f"- {concept}")
        lines.append("")
    return "\n".join(lines)
