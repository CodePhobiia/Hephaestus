"""Tests for finding fingerprint computation and deduplication logic."""
from __future__ import annotations

from datetime import datetime

import pytest

from hephaestus.forgebase.domain.enums import (
    FindingCategory,
    FindingDisposition,
    FindingSeverity,
    FindingStatus,
    RemediationStatus,
)
from hephaestus.forgebase.domain.values import EntityId
from hephaestus.forgebase.linting.detectors.base import RawFinding
from hephaestus.forgebase.linting.fingerprint import (
    compute_fingerprint,
    dedup_findings,
)
from hephaestus.forgebase.domain.models import LintFinding


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _eid(prefix: str, suffix: str) -> EntityId:
    """Build an EntityId with a deterministic 26-char ULID-like string."""
    # Pad/truncate suffix to exactly 26 chars (within 20-30 range)
    padded = (suffix * 5)[:26]
    return EntityId(f"{prefix}_{padded}")


def _raw(
    category: FindingCategory = FindingCategory.UNSUPPORTED_CLAIM,
    severity: FindingSeverity = FindingSeverity.WARNING,
    description: str = "test finding",
    affected_entity_ids: list[EntityId] | None = None,
    normalized_subject: str = "claim about X",
    suggested_action: str | None = None,
    confidence: float = 1.0,
    page_id: EntityId | None = None,
    claim_id: EntityId | None = None,
) -> RawFinding:
    return RawFinding(
        category=category,
        severity=severity,
        description=description,
        affected_entity_ids=affected_entity_ids or [],
        normalized_subject=normalized_subject,
        suggested_action=suggested_action,
        confidence=confidence,
        page_id=page_id,
        claim_id=claim_id,
    )


def _existing_finding(
    finding_id: EntityId,
    job_id: EntityId,
    vault_id: EntityId,
    category: FindingCategory,
    severity: FindingSeverity,
    fingerprint: str,
    status: FindingStatus = FindingStatus.OPEN,
    disposition: FindingDisposition = FindingDisposition.ACTIVE,
    description: str = "existing finding",
    affected_entity_ids: list[EntityId] | None = None,
) -> LintFinding:
    return LintFinding(
        finding_id=finding_id,
        job_id=job_id,
        vault_id=vault_id,
        category=category,
        severity=severity,
        page_id=None,
        claim_id=None,
        description=description,
        suggested_action=None,
        status=status,
        finding_fingerprint=fingerprint,
        disposition=disposition,
        affected_entity_ids=affected_entity_ids or [],
    )


# ---------------------------------------------------------------------------
# compute_fingerprint tests
# ---------------------------------------------------------------------------

class TestComputeFingerprint:
    def test_fingerprint_stable(self) -> None:
        """Same inputs always produce the same hash."""
        fp1 = compute_fingerprint(
            category="unsupported_claim",
            affected_entity_ids=["claim_00000000000000000000000001"],
            normalized_subject="claim about X",
            workbook_id=None,
            detector_version="1.0",
        )
        fp2 = compute_fingerprint(
            category="unsupported_claim",
            affected_entity_ids=["claim_00000000000000000000000001"],
            normalized_subject="claim about X",
            workbook_id=None,
            detector_version="1.0",
        )
        assert fp1 == fp2
        assert isinstance(fp1, str)
        assert len(fp1) == 64  # SHA-256 hex digest

    def test_fingerprint_differs_on_category(self) -> None:
        """Different categories produce different fingerprints."""
        fp1 = compute_fingerprint(
            category="unsupported_claim",
            affected_entity_ids=["claim_00000000000000000000000001"],
            normalized_subject="X",
            workbook_id=None,
            detector_version="1.0",
        )
        fp2 = compute_fingerprint(
            category="stale_evidence",
            affected_entity_ids=["claim_00000000000000000000000001"],
            normalized_subject="X",
            workbook_id=None,
            detector_version="1.0",
        )
        assert fp1 != fp2

    def test_fingerprint_differs_on_entities(self) -> None:
        """Different affected entity IDs produce different fingerprints."""
        fp1 = compute_fingerprint(
            category="unsupported_claim",
            affected_entity_ids=["claim_00000000000000000000000001"],
            normalized_subject="X",
            workbook_id=None,
            detector_version="1.0",
        )
        fp2 = compute_fingerprint(
            category="unsupported_claim",
            affected_entity_ids=["claim_00000000000000000000000002"],
            normalized_subject="X",
            workbook_id=None,
            detector_version="1.0",
        )
        assert fp1 != fp2

    def test_fingerprint_differs_on_workbook(self) -> None:
        """Different workbook IDs produce different fingerprints."""
        fp1 = compute_fingerprint(
            category="unsupported_claim",
            affected_entity_ids=["claim_00000000000000000000000001"],
            normalized_subject="X",
            workbook_id=None,
            detector_version="1.0",
        )
        fp2 = compute_fingerprint(
            category="unsupported_claim",
            affected_entity_ids=["claim_00000000000000000000000001"],
            normalized_subject="X",
            workbook_id="wb_00000000000000000000000099",
            detector_version="1.0",
        )
        assert fp1 != fp2

    def test_fingerprint_differs_on_subject(self) -> None:
        """Different normalized subjects produce different fingerprints."""
        fp1 = compute_fingerprint(
            category="unsupported_claim",
            affected_entity_ids=["claim_00000000000000000000000001"],
            normalized_subject="claim about X",
            workbook_id=None,
            detector_version="1.0",
        )
        fp2 = compute_fingerprint(
            category="unsupported_claim",
            affected_entity_ids=["claim_00000000000000000000000001"],
            normalized_subject="claim about Y",
            workbook_id=None,
            detector_version="1.0",
        )
        assert fp1 != fp2

    def test_fingerprint_differs_on_detector_version(self) -> None:
        """Different detector versions produce different fingerprints."""
        fp1 = compute_fingerprint(
            category="unsupported_claim",
            affected_entity_ids=["claim_00000000000000000000000001"],
            normalized_subject="X",
            workbook_id=None,
            detector_version="1.0",
        )
        fp2 = compute_fingerprint(
            category="unsupported_claim",
            affected_entity_ids=["claim_00000000000000000000000001"],
            normalized_subject="X",
            workbook_id=None,
            detector_version="2.0",
        )
        assert fp1 != fp2

    def test_fingerprint_entity_order_independent(self) -> None:
        """Entity IDs are sorted before hashing, so order doesn't matter."""
        fp1 = compute_fingerprint(
            category="broken_reference",
            affected_entity_ids=["link_aaaaaaaaaaaaaaaaaaaaaaaaaa", "link_bbbbbbbbbbbbbbbbbbbbbbbbbb"],
            normalized_subject="broken ref",
            workbook_id=None,
            detector_version="1.0",
        )
        fp2 = compute_fingerprint(
            category="broken_reference",
            affected_entity_ids=["link_bbbbbbbbbbbbbbbbbbbbbbbbbb", "link_aaaaaaaaaaaaaaaaaaaaaaaaaa"],
            normalized_subject="broken ref",
            workbook_id=None,
            detector_version="1.0",
        )
        assert fp1 == fp2

    def test_fingerprint_empty_entities(self) -> None:
        """Empty entity list is a valid input."""
        fp = compute_fingerprint(
            category="orphaned_page",
            affected_entity_ids=[],
            normalized_subject="orphan",
            workbook_id=None,
            detector_version="1.0",
        )
        assert isinstance(fp, str)
        assert len(fp) == 64


# ---------------------------------------------------------------------------
# dedup_findings tests
# ---------------------------------------------------------------------------

VAULT_ID = _eid("vault", "AAAAAAAAAAAAAAAAAAAAAAAAAA")
JOB_ID = _eid("job", "BBBBBBBBBBBBBBBBBBBBBBBBBB")
WORKBOOK_ID = _eid("wb", "CCCCCCCCCCCCCCCCCCCCCCCCCC")


class TestDedupFindings:
    def test_dedup_all_new(self) -> None:
        """No existing findings means all raw findings are new."""
        raw = [
            _raw(
                category=FindingCategory.UNSUPPORTED_CLAIM,
                affected_entity_ids=[_eid("claim", "a1a1a1a1a1a1a1a1a1a1a1a1a1")],
                normalized_subject="claim A",
            ),
            _raw(
                category=FindingCategory.STALE_EVIDENCE,
                affected_entity_ids=[_eid("claim", "b2b2b2b2b2b2b2b2b2b2b2b2b2")],
                normalized_subject="claim B",
            ),
        ]
        new, reopen = dedup_findings(
            raw_findings=raw,
            existing_findings=[],
            vault_id=VAULT_ID,
            workbook_id=None,
            detector_version="1.0",
        )
        assert len(new) == 2
        assert len(reopen) == 0

    def test_dedup_skip_existing_open(self) -> None:
        """An existing OPEN finding with the same fingerprint is skipped (neither new nor reopen)."""
        claim_id = _eid("claim", "d4d4d4d4d4d4d4d4d4d4d4d4d4")
        raw = [
            _raw(
                category=FindingCategory.UNSUPPORTED_CLAIM,
                affected_entity_ids=[claim_id],
                normalized_subject="claim X",
            ),
        ]
        # Pre-compute the fingerprint that would be generated for this raw finding
        fp = compute_fingerprint(
            category=FindingCategory.UNSUPPORTED_CLAIM.value,
            affected_entity_ids=[str(claim_id)],
            normalized_subject="claim X",
            workbook_id=None,
            detector_version="1.0",
        )
        existing = [
            _existing_finding(
                finding_id=_eid("find", "e5e5e5e5e5e5e5e5e5e5e5e5e5"),
                job_id=JOB_ID,
                vault_id=VAULT_ID,
                category=FindingCategory.UNSUPPORTED_CLAIM,
                severity=FindingSeverity.WARNING,
                fingerprint=fp,
                status=FindingStatus.OPEN,
                disposition=FindingDisposition.ACTIVE,
                affected_entity_ids=[claim_id],
            ),
        ]
        new, reopen = dedup_findings(
            raw_findings=raw,
            existing_findings=existing,
            vault_id=VAULT_ID,
            workbook_id=None,
            detector_version="1.0",
        )
        assert len(new) == 0
        assert len(reopen) == 0

    def test_dedup_reopen_resolved(self) -> None:
        """An existing RESOLVED finding with the same fingerprint should be reopened."""
        claim_id = _eid("claim", "f6f6f6f6f6f6f6f6f6f6f6f6f6")
        raw = [
            _raw(
                category=FindingCategory.UNSUPPORTED_CLAIM,
                affected_entity_ids=[claim_id],
                normalized_subject="claim Y",
            ),
        ]
        fp = compute_fingerprint(
            category=FindingCategory.UNSUPPORTED_CLAIM.value,
            affected_entity_ids=[str(claim_id)],
            normalized_subject="claim Y",
            workbook_id=None,
            detector_version="1.0",
        )
        existing = [
            _existing_finding(
                finding_id=_eid("find", "g7g7g7g7g7g7g7g7g7g7g7g7g7"),
                job_id=JOB_ID,
                vault_id=VAULT_ID,
                category=FindingCategory.UNSUPPORTED_CLAIM,
                severity=FindingSeverity.WARNING,
                fingerprint=fp,
                status=FindingStatus.RESOLVED,
                disposition=FindingDisposition.RESOLVED,
                affected_entity_ids=[claim_id],
            ),
        ]
        new, reopen = dedup_findings(
            raw_findings=raw,
            existing_findings=existing,
            vault_id=VAULT_ID,
            workbook_id=None,
            detector_version="1.0",
        )
        assert len(new) == 0
        assert len(reopen) == 1
        assert reopen[0].finding_id == _eid("find", "g7g7g7g7g7g7g7g7g7g7g7g7g7")

    def test_dedup_reopen_false_positive(self) -> None:
        """An existing FALSE_POSITIVE finding with the same fingerprint should be reopened."""
        claim_id = _eid("claim", "h8h8h8h8h8h8h8h8h8h8h8h8h8")
        raw = [
            _raw(
                category=FindingCategory.BROKEN_REFERENCE,
                affected_entity_ids=[claim_id],
                normalized_subject="broken ref Z",
            ),
        ]
        fp = compute_fingerprint(
            category=FindingCategory.BROKEN_REFERENCE.value,
            affected_entity_ids=[str(claim_id)],
            normalized_subject="broken ref Z",
            workbook_id=None,
            detector_version="1.0",
        )
        existing = [
            _existing_finding(
                finding_id=_eid("find", "i9i9i9i9i9i9i9i9i9i9i9i9i9"),
                job_id=JOB_ID,
                vault_id=VAULT_ID,
                category=FindingCategory.BROKEN_REFERENCE,
                severity=FindingSeverity.WARNING,
                fingerprint=fp,
                status=FindingStatus.RESOLVED,
                disposition=FindingDisposition.FALSE_POSITIVE,
                affected_entity_ids=[claim_id],
            ),
        ]
        new, reopen = dedup_findings(
            raw_findings=raw,
            existing_findings=existing,
            vault_id=VAULT_ID,
            workbook_id=None,
            detector_version="1.0",
        )
        assert len(new) == 0
        assert len(reopen) == 1

    def test_dedup_reopen_wont_fix(self) -> None:
        """An existing WONT_FIX finding with the same fingerprint should be reopened."""
        claim_id = _eid("claim", "j0j0j0j0j0j0j0j0j0j0j0j0j0")
        raw = [
            _raw(
                category=FindingCategory.ORPHANED_PAGE,
                affected_entity_ids=[claim_id],
                normalized_subject="orphan page",
            ),
        ]
        fp = compute_fingerprint(
            category=FindingCategory.ORPHANED_PAGE.value,
            affected_entity_ids=[str(claim_id)],
            normalized_subject="orphan page",
            workbook_id=None,
            detector_version="1.0",
        )
        existing = [
            _existing_finding(
                finding_id=_eid("find", "k1k1k1k1k1k1k1k1k1k1k1k1k1"),
                job_id=JOB_ID,
                vault_id=VAULT_ID,
                category=FindingCategory.ORPHANED_PAGE,
                severity=FindingSeverity.INFO,
                fingerprint=fp,
                status=FindingStatus.WAIVED,
                disposition=FindingDisposition.WONT_FIX,
                affected_entity_ids=[claim_id],
            ),
        ]
        new, reopen = dedup_findings(
            raw_findings=raw,
            existing_findings=existing,
            vault_id=VAULT_ID,
            workbook_id=None,
            detector_version="1.0",
        )
        assert len(new) == 0
        assert len(reopen) == 1

    def test_dedup_mixed(self) -> None:
        """Combination of new, skip (existing open), and reopen (existing resolved)."""
        claim_a = _eid("claim", "m3m3m3m3m3m3m3m3m3m3m3m3m3")
        claim_b = _eid("claim", "n4n4n4n4n4n4n4n4n4n4n4n4n4")
        claim_c = _eid("claim", "o5o5o5o5o5o5o5o5o5o5o5o5o5")

        # Three raw findings
        raw = [
            _raw(  # Will match existing OPEN -> skip
                category=FindingCategory.UNSUPPORTED_CLAIM,
                affected_entity_ids=[claim_a],
                normalized_subject="claim A",
            ),
            _raw(  # Will match existing RESOLVED -> reopen
                category=FindingCategory.STALE_EVIDENCE,
                affected_entity_ids=[claim_b],
                normalized_subject="claim B",
            ),
            _raw(  # No match -> new
                category=FindingCategory.BROKEN_REFERENCE,
                affected_entity_ids=[claim_c],
                normalized_subject="claim C",
            ),
        ]

        fp_a = compute_fingerprint(
            category=FindingCategory.UNSUPPORTED_CLAIM.value,
            affected_entity_ids=[str(claim_a)],
            normalized_subject="claim A",
            workbook_id=None,
            detector_version="1.0",
        )
        fp_b = compute_fingerprint(
            category=FindingCategory.STALE_EVIDENCE.value,
            affected_entity_ids=[str(claim_b)],
            normalized_subject="claim B",
            workbook_id=None,
            detector_version="1.0",
        )

        existing = [
            _existing_finding(
                finding_id=_eid("find", "p6p6p6p6p6p6p6p6p6p6p6p6p6"),
                job_id=JOB_ID,
                vault_id=VAULT_ID,
                category=FindingCategory.UNSUPPORTED_CLAIM,
                severity=FindingSeverity.WARNING,
                fingerprint=fp_a,
                status=FindingStatus.OPEN,
                disposition=FindingDisposition.ACTIVE,
                affected_entity_ids=[claim_a],
            ),
            _existing_finding(
                finding_id=_eid("find", "q7q7q7q7q7q7q7q7q7q7q7q7q7"),
                job_id=JOB_ID,
                vault_id=VAULT_ID,
                category=FindingCategory.STALE_EVIDENCE,
                severity=FindingSeverity.WARNING,
                fingerprint=fp_b,
                status=FindingStatus.RESOLVED,
                disposition=FindingDisposition.RESOLVED,
                affected_entity_ids=[claim_b],
            ),
        ]

        new, reopen = dedup_findings(
            raw_findings=raw,
            existing_findings=existing,
            vault_id=VAULT_ID,
            workbook_id=None,
            detector_version="1.0",
        )

        # One new (claim_c), zero skipped (claim_a), one reopen (claim_b)
        assert len(new) == 1
        assert new[0].normalized_subject == "claim C"
        assert len(reopen) == 1
        assert reopen[0].finding_id == _eid("find", "q7q7q7q7q7q7q7q7q7q7q7q7q7")

    def test_dedup_with_workbook_id(self) -> None:
        """Dedup works correctly when workbook_id is provided."""
        claim_id = _eid("claim", "r8r8r8r8r8r8r8r8r8r8r8r8r8")
        raw = [
            _raw(
                category=FindingCategory.DUPLICATE_PAGE,
                affected_entity_ids=[claim_id],
                normalized_subject="dup page",
            ),
        ]
        # Fingerprint computed with workbook_id
        fp = compute_fingerprint(
            category=FindingCategory.DUPLICATE_PAGE.value,
            affected_entity_ids=[str(claim_id)],
            normalized_subject="dup page",
            workbook_id=str(WORKBOOK_ID),
            detector_version="1.0",
        )
        existing = [
            _existing_finding(
                finding_id=_eid("find", "s9s9s9s9s9s9s9s9s9s9s9s9s9"),
                job_id=JOB_ID,
                vault_id=VAULT_ID,
                category=FindingCategory.DUPLICATE_PAGE,
                severity=FindingSeverity.WARNING,
                fingerprint=fp,
                status=FindingStatus.OPEN,
                disposition=FindingDisposition.ACTIVE,
                affected_entity_ids=[claim_id],
            ),
        ]
        new, reopen = dedup_findings(
            raw_findings=raw,
            existing_findings=existing,
            vault_id=VAULT_ID,
            workbook_id=WORKBOOK_ID,
            detector_version="1.0",
        )
        assert len(new) == 0
        assert len(reopen) == 0

    def test_dedup_duplicate_raw_findings(self) -> None:
        """If two raw findings produce the same fingerprint, only the first is treated as new."""
        claim_id = _eid("claim", "t0t0t0t0t0t0t0t0t0t0t0t0t0")
        raw = [
            _raw(
                category=FindingCategory.UNSUPPORTED_CLAIM,
                affected_entity_ids=[claim_id],
                normalized_subject="same claim",
            ),
            _raw(
                category=FindingCategory.UNSUPPORTED_CLAIM,
                affected_entity_ids=[claim_id],
                normalized_subject="same claim",
            ),
        ]
        new, reopen = dedup_findings(
            raw_findings=raw,
            existing_findings=[],
            vault_id=VAULT_ID,
            workbook_id=None,
            detector_version="1.0",
        )
        assert len(new) == 1
        assert len(reopen) == 0
