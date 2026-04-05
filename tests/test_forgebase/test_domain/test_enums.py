"""Tests for ForgeBase enumerations."""

from __future__ import annotations

from hephaestus.forgebase.domain.enums import (
    ActorType,
    ClaimStatus,
    EntityKind,
    FindingCategory,
    FindingDisposition,
    FindingSeverity,
    FindingStatus,
    InventionEpistemicState,
    JobKind,
    JobStatus,
    LinkKind,
    MergeResolution,
    MergeVerdict,
    PageType,
    ProvenanceKind,
    RemediationRoute,
    RemediationStatus,
    ResearchOutcome,
    RouteSource,
    SourceFormat,
    SourceStatus,
    SourceTrustTier,
    SupportType,
    WorkbookStatus,
)


def test_all_enums_are_string_valued():
    """Every enum must be usable as a plain string for DB storage."""
    for enum_cls in [
        PageType,
        ClaimStatus,
        SupportType,
        LinkKind,
        SourceFormat,
        SourceTrustTier,
        SourceStatus,
        WorkbookStatus,
        JobStatus,
        JobKind,
        FindingSeverity,
        FindingCategory,
        FindingStatus,
        MergeVerdict,
        MergeResolution,
        EntityKind,
        ActorType,
        RemediationStatus,
        RemediationRoute,
        RouteSource,
        FindingDisposition,
        ResearchOutcome,
        InventionEpistemicState,
        ProvenanceKind,
    ]:
        for member in enum_cls:
            assert isinstance(member.value, str)
            assert member == member.value


def test_page_type_has_source_card():
    assert PageType.SOURCE_CARD == "source_card"


def test_claim_status_values():
    assert set(ClaimStatus) == {
        ClaimStatus.SUPPORTED,
        ClaimStatus.INFERRED,
        ClaimStatus.HYPOTHESIS,
        ClaimStatus.CONTESTED,
        ClaimStatus.STALE,
    }


def test_remediation_status_values():
    assert RemediationStatus.OPEN == "open"
    assert RemediationStatus.TRIAGED == "triaged"
    assert RemediationStatus.RESEARCH_PENDING == "research_pending"
    assert RemediationStatus.RESEARCH_COMPLETED == "research_completed"
    assert RemediationStatus.REPAIR_PENDING == "repair_pending"
    assert RemediationStatus.REPAIR_WORKBOOK_CREATED == "repair_workbook_created"
    assert RemediationStatus.AWAITING_REVIEW == "awaiting_review"
    assert RemediationStatus.MERGED_PENDING_VERIFY == "merged_pending_verify"
    assert RemediationStatus.VERIFIED == "verified"
    assert len(RemediationStatus) == 9


def test_remediation_route_values():
    assert RemediationRoute.REPORT_ONLY == "report_only"
    assert RemediationRoute.RESEARCH_ONLY == "research_only"
    assert RemediationRoute.REPAIR_ONLY == "repair_only"
    assert RemediationRoute.RESEARCH_THEN_REPAIR == "research_then_repair"
    assert len(RemediationRoute) == 4


def test_route_source_values():
    assert RouteSource.POLICY == "policy"
    assert RouteSource.USER == "user"
    assert RouteSource.AUTOMATION == "automation"
    assert RouteSource.RETRIAGE == "retriage"
    assert len(RouteSource) == 4


def test_finding_disposition_values():
    assert FindingDisposition.ACTIVE == "active"
    assert FindingDisposition.RESOLVED == "resolved"
    assert FindingDisposition.FALSE_POSITIVE == "false_positive"
    assert FindingDisposition.WONT_FIX == "wont_fix"
    assert FindingDisposition.ABANDONED == "abandoned"
    assert len(FindingDisposition) == 5


def test_research_outcome_values():
    assert ResearchOutcome.SUFFICIENT_FOR_REPAIR == "sufficient_for_repair"
    assert ResearchOutcome.INSUFFICIENT_EVIDENCE == "insufficient_evidence"
    assert ResearchOutcome.NEW_SOURCES_PENDING == "new_sources_pending"
    assert ResearchOutcome.NO_ACTIONABLE_RESULT == "no_actionable_result"
    assert len(ResearchOutcome) == 4


def test_finding_category_renames():
    """Verify STALE_PAGE -> STALE_EVIDENCE and WEAK_BACKLINK -> BROKEN_REFERENCE."""
    assert FindingCategory.STALE_EVIDENCE == "stale_evidence"
    assert FindingCategory.BROKEN_REFERENCE == "broken_reference"
    # Old names should not exist
    assert not hasattr(FindingCategory, "STALE_PAGE")
    assert not hasattr(FindingCategory, "WEAK_BACKLINK")


# ---------------------------------------------------------------------------
# Invention loop enums
# ---------------------------------------------------------------------------


def test_invention_epistemic_state_values():
    assert InventionEpistemicState.PROPOSED == "proposed"
    assert InventionEpistemicState.REVIEWED == "reviewed"
    assert InventionEpistemicState.VERIFIED == "verified"
    assert InventionEpistemicState.CONTESTED == "contested"
    assert InventionEpistemicState.REJECTED == "rejected"
    assert len(InventionEpistemicState) == 5


def test_invention_epistemic_state_is_string_enum():
    for member in InventionEpistemicState:
        assert isinstance(member.value, str)
        assert member == member.value


def test_provenance_kind_values():
    assert ProvenanceKind.GENERATED == "generated"
    assert ProvenanceKind.DERIVED == "derived"
    assert ProvenanceKind.EMPIRICAL == "empirical"
    assert ProvenanceKind.INHERITED == "inherited"
    assert len(ProvenanceKind) == 4


def test_provenance_kind_is_string_enum():
    for member in ProvenanceKind:
        assert isinstance(member.value, str)
        assert member == member.value


def test_link_kind_invention_values():
    """Verify the 6 new LinkKind values for invention loop."""
    assert LinkKind.MOTIVATED_BY == "motivated_by"
    assert LinkKind.MAPS_TO == "maps_to"
    assert LinkKind.DERIVES_FROM == "derives_from"
    assert LinkKind.PRIOR_ART_OF == "prior_art_of"
    assert LinkKind.CONSTRAINED_BY == "constrained_by"
    assert LinkKind.CHALLENGED_BY == "challenged_by"


def test_link_kind_retains_existing_values():
    """Ensure existing LinkKind values still present after additions."""
    assert LinkKind.BACKLINK == "backlink"
    assert LinkKind.RELATED_CONCEPT == "related_concept"
    assert LinkKind.PAGE_TO_PAGE == "page_to_page"
    assert LinkKind.SUPERSEDES == "supersedes"
    assert len(LinkKind) == 10  # 4 original + 6 new
