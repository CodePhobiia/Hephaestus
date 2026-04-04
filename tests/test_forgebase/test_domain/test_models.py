"""Tests for ForgeBase domain models."""
from __future__ import annotations

from datetime import UTC, datetime

from hephaestus.forgebase.domain.enums import (
    ActorType,
    BranchPurpose,
    ClaimStatus,
    EntityKind,
    FindingCategory,
    FindingSeverity,
    FindingStatus,
    JobKind,
    JobStatus,
    LinkKind,
    MergeResolution,
    MergeVerdict,
    PageType,
    SourceFormat,
    SourceStatus,
    SourceTrustTier,
    SupportType,
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
    Claim,
    ClaimDerivation,
    ClaimSupport,
    ClaimVersion,
    DomainEvent,
    EventDelivery,
    Job,
    KnowledgeRunArtifact,
    KnowledgeRunRef,
    Link,
    LinkVersion,
    LintFinding,
    MergeConflict,
    MergeProposal,
    Page,
    PageVersion,
    Source,
    SourceVersion,
    Vault,
    VaultRevision,
    Workbook,
)
from hephaestus.forgebase.domain.values import (
    ActorRef,
    BlobRef,
    ContentHash,
    EntityId,
    VaultRevisionId,
    Version,
)


def _eid(prefix: str, suffix: str = "01HXYZ12345678901234ABCDEF") -> EntityId:
    return EntityId(f"{prefix}_{suffix}")


def _rev(suffix: str = "01HXYZ12345678901234ABCDEF") -> VaultRevisionId:
    return VaultRevisionId(f"rev_{suffix}")


def _actor() -> ActorRef:
    return ActorRef(actor_type=ActorType.SYSTEM, actor_id="test")


def _now() -> datetime:
    return datetime(2026, 4, 3, tzinfo=UTC)


def _blob() -> BlobRef:
    return BlobRef(content_hash=ContentHash(sha256="a" * 64), size_bytes=100, mime_type="text/plain")


class TestVault:
    def test_create(self):
        v = Vault(
            vault_id=_eid("vault"),
            name="test-vault",
            description="A test vault",
            head_revision_id=_rev(),
            created_at=_now(),
            updated_at=_now(),
            config={},
        )
        assert v.name == "test-vault"
        assert v.vault_id.prefix == "vault"


class TestSourceVersion:
    def test_create(self):
        sv = SourceVersion(
            source_id=_eid("source"),
            version=Version(1),
            title="Test Paper",
            authors=["Author A"],
            url="https://example.com",
            raw_artifact_ref=_blob(),
            normalized_ref=None,
            content_hash=ContentHash(sha256="b" * 64),
            metadata={},
            trust_tier=SourceTrustTier.STANDARD,
            status=SourceStatus.INGESTED,
            created_at=_now(),
            created_by=_actor(),
        )
        assert sv.version == Version(1)
        assert sv.trust_tier == SourceTrustTier.STANDARD


class TestPageVersion:
    def test_create(self):
        pv = PageVersion(
            page_id=_eid("page"),
            version=Version(1),
            title="Concept: Pheromone Routing",
            content_ref=_blob(),
            content_hash=ContentHash(sha256="c" * 64),
            summary="Initial version",
            compiled_from=[_eid("source")],
            created_at=_now(),
            created_by=_actor(),
            schema_version=1,
        )
        assert pv.title == "Concept: Pheromone Routing"


class TestClaimVersion:
    def test_create(self):
        cv = ClaimVersion(
            claim_id=_eid("claim"),
            version=Version(1),
            statement="Pheromone decay enables load redistribution",
            status=ClaimStatus.SUPPORTED,
            support_type=SupportType.DIRECT,
            confidence=0.85,
            validated_at=_now(),
            fresh_until=None,
            created_at=_now(),
            created_by=_actor(),
        )
        assert cv.confidence == 0.85


class TestClaimSupport:
    def test_create(self):
        cs = ClaimSupport(
            support_id=_eid("csup"),
            claim_id=_eid("claim"),
            source_id=_eid("source"),
            source_segment="Section 3.2",
            strength=0.9,
            created_at=_now(),
            created_by=_actor(),
        )
        assert cs.strength == 0.9


class TestWorkbook:
    def test_create(self):
        wb = Workbook(
            workbook_id=_eid("wb"),
            vault_id=_eid("vault"),
            name="research-branch",
            purpose=BranchPurpose.RESEARCH,
            status=WorkbookStatus.OPEN,
            base_revision_id=_rev(),
            created_at=_now(),
            created_by=_actor(),
            created_by_run=None,
        )
        assert wb.status == WorkbookStatus.OPEN


class TestBranchPageHead:
    def test_create(self):
        bph = BranchPageHead(
            workbook_id=_eid("wb"),
            page_id=_eid("page"),
            head_version=Version(2),
            base_version=Version(1),
        )
        assert bph.head_version > bph.base_version


class TestBranchTombstone:
    def test_create(self):
        bt = BranchTombstone(
            workbook_id=_eid("wb"),
            entity_kind=EntityKind.PAGE,
            entity_id=_eid("page"),
            tombstoned_at=_now(),
        )
        assert bt.entity_kind == EntityKind.PAGE


class TestMergeProposal:
    def test_create_clean(self):
        mp = MergeProposal(
            merge_id=_eid("merge"),
            workbook_id=_eid("wb"),
            vault_id=_eid("vault"),
            base_revision_id=_rev("01HXYZ00000000000000000001"),
            target_revision_id=_rev("01HXYZ00000000000000000001"),
            verdict=MergeVerdict.CLEAN,
            resulting_revision=None,
            proposed_at=_now(),
            resolved_at=None,
            proposed_by=_actor(),
        )
        assert mp.verdict == MergeVerdict.CLEAN


class TestJob:
    def test_create(self):
        j = Job(
            job_id=_eid("job"),
            vault_id=_eid("vault"),
            workbook_id=None,
            kind=JobKind.COMPILE,
            status=JobStatus.PENDING,
            config={},
            idempotency_key="compile:vault_01:rev_01",
            priority=0,
            attempt_count=0,
            max_attempts=3,
            next_attempt_at=None,
            leased_until=None,
            heartbeat_at=None,
            started_at=None,
            completed_at=None,
            error=None,
            created_by=_actor(),
            created_by_run=None,
        )
        assert j.status == JobStatus.PENDING
        assert j.attempt_count == 0


class TestDomainEvent:
    def test_create(self):
        ev = DomainEvent(
            event_id=_eid("evt"),
            event_type="source.ingested",
            schema_version=1,
            aggregate_type="source",
            aggregate_id=_eid("source"),
            aggregate_version=Version(1),
            vault_id=_eid("vault"),
            workbook_id=None,
            run_id=None,
            causation_id=None,
            correlation_id=None,
            actor_type=ActorType.SYSTEM,
            actor_id="system",
            occurred_at=_now(),
            payload={"source_id": "source_01HXYZ12345678901234ABCDEF"},
        )
        assert ev.event_type == "source.ingested"


from hephaestus.forgebase.domain.enums import (
    CandidateKind, CandidateStatus, DirtyTargetKind,
)
from hephaestus.forgebase.domain.models import (
    BackendCallRecord,
    ConceptCandidate,
    ConceptCandidateEvidence,
    SourceCompileManifest,
    SynthesisDirtyMarker,
    VaultSynthesisManifest,
)
from hephaestus.forgebase.domain.values import EvidenceSegmentRef


class TestBackendCallRecord:
    def test_create(self):
        rec = BackendCallRecord(
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
        )
        assert rec.model_name == "claude-sonnet-4-5"
        assert not rec.repair_invoked


class TestConceptCandidate:
    def test_create(self):
        cc = ConceptCandidate(
            candidate_id=_eid("cand"),
            vault_id=_eid("vault"),
            workbook_id=None,
            source_id=_eid("source"),
            source_version=Version(1),
            source_compile_job_id=_eid("job"),
            name="Solid Electrolyte Interphase",
            normalized_name="solid electrolyte interphase",
            aliases=["SEI", "SEI layer"],
            candidate_kind=CandidateKind.MECHANISM,
            confidence=0.92,
            salience=0.85,
            status=CandidateStatus.ACTIVE,
            resolved_page_id=None,
            compiler_policy_version="1.0.0",
            created_at=_now(),
        )
        assert cc.status == CandidateStatus.ACTIVE
        assert cc.normalized_name == "solid electrolyte interphase"


class TestConceptCandidateEvidence:
    def test_create(self):
        ev = ConceptCandidateEvidence(
            evidence_id=_eid("cevd"),
            candidate_id=_eid("cand"),
            segment_ref=EvidenceSegmentRef(
                source_id=_eid("source"),
                source_version=Version(1),
                segment_start=100,
                segment_end=300,
                section_key="3.2",
                preview_text="The SEI layer...",
            ),
            role="DEFINITION",
            created_at=_now(),
        )
        assert ev.role == "DEFINITION"
        assert ev.segment_ref.segment_start == 100


class TestSynthesisDirtyMarker:
    def test_create(self):
        dm = SynthesisDirtyMarker(
            marker_id=_eid("dirty"),
            vault_id=_eid("vault"),
            workbook_id=None,
            target_kind=DirtyTargetKind.CONCEPT,
            target_key="solid electrolyte interphase",
            first_dirtied_at=_now(),
            last_dirtied_at=_now(),
            times_dirtied=1,
            last_dirtied_by_source=_eid("source"),
            last_dirtied_by_job=_eid("job"),
            consumed_by_job=None,
            consumed_at=None,
        )
        assert dm.times_dirtied == 1
        assert dm.consumed_by_job is None


class TestSourceCompileManifest:
    def test_create(self):
        m = SourceCompileManifest(
            manifest_id=_eid("mfst"),
            vault_id=_eid("vault"),
            workbook_id=None,
            source_id=_eid("source"),
            source_version=Version(1),
            job_id=_eid("job"),
            compiler_policy_version="1.0.0",
            prompt_versions={"claim_extraction": "1.0.0", "concept_extraction": "1.0.0"},
            backend_calls=[],
            claim_count=5,
            concept_count=3,
            relationship_count=2,
            source_content_hash=ContentHash(sha256="a" * 64),
            created_at=_now(),
        )
        assert m.claim_count == 5


class TestVaultSynthesisManifest:
    def test_create(self):
        m = VaultSynthesisManifest(
            manifest_id=_eid("mfst"),
            vault_id=_eid("vault"),
            workbook_id=None,
            job_id=_eid("job"),
            base_revision=_rev(),
            synthesis_policy_version="1.0.0",
            prompt_versions={"synthesis": "1.0.0"},
            backend_calls=[],
            candidates_resolved=10,
            augmentor_calls=2,
            created_at=_now(),
        )
        assert m.candidates_resolved == 10
        assert m.augmentor_calls == 2
