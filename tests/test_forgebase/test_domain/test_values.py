"""Tests for ForgeBase domain value objects."""

from __future__ import annotations

import pytest

from hephaestus.forgebase.domain.enums import ActorType
from hephaestus.forgebase.domain.values import (
    ActorRef,
    BlobRef,
    ContentHash,
    EntityId,
    VaultRevisionId,
    Version,
)


class TestEntityId:
    def test_create_with_prefix(self):
        eid = EntityId("vault_01HXYZ12345678901234ABCDEF")
        assert eid.prefix == "vault"
        assert len(eid.ulid_part) == 26
        assert str(eid) == "vault_01HXYZ12345678901234ABCDEF"

    def test_reject_no_prefix(self):
        with pytest.raises(ValueError, match="prefix"):
            EntityId("01HXYZ12345678901234ABCDEF")

    def test_reject_empty(self):
        with pytest.raises(ValueError):
            EntityId("")

    def test_equality(self):
        a = EntityId("page_01HXYZ12345678901234ABCDEF")
        b = EntityId("page_01HXYZ12345678901234ABCDEF")
        assert a == b
        assert hash(a) == hash(b)

    def test_inequality_different_prefix(self):
        a = EntityId("page_01HXYZ12345678901234ABCDEF")
        b = EntityId("claim_01HXYZ12345678901234ABCDEF")
        assert a != b


class TestVersion:
    def test_create_positive(self):
        v = Version(1)
        assert v.number == 1

    def test_reject_zero(self):
        with pytest.raises(ValueError):
            Version(0)

    def test_reject_negative(self):
        with pytest.raises(ValueError):
            Version(-1)

    def test_ordering(self):
        assert Version(1) < Version(2)
        assert Version(3) > Version(1)

    def test_next(self):
        v = Version(1)
        assert v.next() == Version(2)


class TestVaultRevisionId:
    def test_create(self):
        rid = VaultRevisionId("rev_01HXYZ12345678901234ABCDEF")
        assert rid.prefix == "rev"


class TestContentHash:
    def test_from_bytes(self):
        ch = ContentHash.from_bytes(b"hello world")
        assert len(ch.sha256) == 64
        assert ch.sha256.startswith("b94d27b9")

    def test_equality(self):
        a = ContentHash.from_bytes(b"hello")
        b = ContentHash.from_bytes(b"hello")
        assert a == b


class TestBlobRef:
    def test_create(self):
        ref = BlobRef(
            content_hash=ContentHash(sha256="abc123"),
            size_bytes=1024,
            mime_type="text/markdown",
        )
        assert ref.size_bytes == 1024
        assert ref.mime_type == "text/markdown"


class TestActorRef:
    def test_create(self):
        actor = ActorRef(actor_type=ActorType.USER, actor_id="user-123")
        assert actor.actor_type == ActorType.USER
        assert actor.actor_id == "user-123"

    def test_system_actor(self):
        actor = ActorRef.system()
        assert actor.actor_type == ActorType.SYSTEM


from hephaestus.forgebase.domain.enums import (
    CandidateKind,
    CandidateStatus,
    CompilePhase,
    DirtyTargetKind,
)
from hephaestus.forgebase.domain.values import EvidenceSegmentRef


class TestEvidenceSegmentRef:
    def test_create(self):
        ref = EvidenceSegmentRef(
            source_id=EntityId("source_01HXYZ12345678901234ABCDEF"),
            source_version=Version(1),
            segment_start=100,
            segment_end=350,
            section_key="3.2",
            preview_text="The SEI layer forms during initial cycling...",
        )
        assert ref.segment_start == 100
        assert ref.segment_end == 350
        assert ref.section_key == "3.2"

    def test_length(self):
        ref = EvidenceSegmentRef(
            source_id=EntityId("source_01HXYZ12345678901234ABCDEF"),
            source_version=Version(1),
            segment_start=0,
            segment_end=200,
            section_key=None,
            preview_text="Preview",
        )
        assert ref.length == 200


class TestNewEnums:
    def test_candidate_kind_values(self):
        assert CandidateKind.CONCEPT == "concept"
        assert CandidateKind.ENTITY == "entity"
        assert CandidateKind.MECHANISM == "mechanism"
        assert CandidateKind.TERM == "term"

    def test_candidate_status_values(self):
        assert CandidateStatus.ACTIVE == "active"
        assert CandidateStatus.SUPERSEDED == "superseded"
        assert CandidateStatus.PROMOTED == "promoted"

    def test_dirty_target_kind_values(self):
        assert DirtyTargetKind.CONCEPT == "concept"
        assert DirtyTargetKind.SOURCE_INDEX == "source_index"

    def test_compile_phase_values(self):
        assert CompilePhase.TIER1_EXTRACTION == "tier1_extraction"
        assert CompilePhase.TIER2_SYNTHESIZE == "tier2_synthesize"
