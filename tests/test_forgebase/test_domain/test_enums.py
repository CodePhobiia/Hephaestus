"""Tests for ForgeBase enumerations."""
from __future__ import annotations

from hephaestus.forgebase.domain.enums import (
    ActorType,
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


def test_all_enums_are_string_valued():
    """Every enum must be usable as a plain string for DB storage."""
    for enum_cls in [
        PageType, ClaimStatus, SupportType, LinkKind, SourceFormat,
        SourceTrustTier, SourceStatus, WorkbookStatus, JobStatus, JobKind,
        FindingSeverity, FindingCategory, FindingStatus, MergeVerdict,
        MergeResolution, EntityKind, ActorType,
    ]:
        for member in enum_cls:
            assert isinstance(member.value, str)
            assert member == member.value


def test_page_type_has_source_card():
    assert PageType.SOURCE_CARD == "source_card"


def test_claim_status_values():
    assert set(ClaimStatus) == {
        ClaimStatus.SUPPORTED, ClaimStatus.INFERRED,
        ClaimStatus.HYPOTHESIS, ClaimStatus.CONTESTED, ClaimStatus.STALE,
    }
