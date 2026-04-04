"""Tests for finding batching — grouping, strategies, and fingerprinting."""
from __future__ import annotations

from datetime import datetime

import pytest

from hephaestus.forgebase.domain.enums import (
    FindingCategory,
    FindingSeverity,
    FindingStatus,
)
from hephaestus.forgebase.domain.models import LintFinding
from hephaestus.forgebase.domain.values import EntityId
from hephaestus.forgebase.linting.remediation.batcher import (
    _batch_fingerprint,
    batch_findings,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _eid(prefix: str, suffix: str) -> EntityId:
    """Build an EntityId with a deterministic 26-char ULID-like string."""
    padded = (suffix * 5)[:26]
    return EntityId(f"{prefix}_{padded}")


VAULT_ID = _eid("vault", "AAAAAAAAAAAAAAAAAAAAAAAAAA")
JOB_ID = _eid("job", "BBBBBBBBBBBBBBBBBBBBBBBBBB")
PAGE_A = _eid("page", "PPPPPPPPPPPPPPPPPPPPPPPPPP")
PAGE_B = _eid("page", "QQQQQQQQQQQQQQQQQQQQQQQQQQ")


def _finding(
    finding_id: EntityId,
    category: FindingCategory = FindingCategory.UNSUPPORTED_CLAIM,
    severity: FindingSeverity = FindingSeverity.WARNING,
    page_id: EntityId | None = None,
) -> LintFinding:
    return LintFinding(
        finding_id=finding_id,
        job_id=JOB_ID,
        vault_id=VAULT_ID,
        category=category,
        severity=severity,
        page_id=page_id,
        claim_id=None,
        description="Test finding",
        suggested_action=None,
        status=FindingStatus.OPEN,
    )


# ---------------------------------------------------------------------------
# batch_findings tests
# ---------------------------------------------------------------------------

class TestBatchFindings:
    def test_empty_findings_returns_empty(self) -> None:
        """No findings produces no batches."""
        result = batch_findings([], VAULT_ID, strategy="auto")
        assert result == []

    def test_by_page_groups_same_page(self) -> None:
        """by_page strategy groups findings with the same page_id together."""
        f1 = _finding(_eid("find", "f1f1f1f1f1f1f1f1f1f1f1f1f1"), page_id=PAGE_A)
        f2 = _finding(_eid("find", "f2f2f2f2f2f2f2f2f2f2f2f2f2"), page_id=PAGE_A)
        batches = batch_findings([f1, f2], VAULT_ID, strategy="by_page")
        assert len(batches) == 1
        assert len(batches[0].finding_ids) == 2

    def test_by_page_separates_different_pages(self) -> None:
        """by_page strategy creates separate batches for different page_ids."""
        f1 = _finding(_eid("find", "f1f1f1f1f1f1f1f1f1f1f1f1f1"), page_id=PAGE_A)
        f2 = _finding(_eid("find", "f2f2f2f2f2f2f2f2f2f2f2f2f2"), page_id=PAGE_B)
        batches = batch_findings([f1, f2], VAULT_ID, strategy="by_page")
        assert len(batches) == 2
        batch_sizes = sorted(len(b.finding_ids) for b in batches)
        assert batch_sizes == [1, 1]

    def test_by_category_groups_same_category(self) -> None:
        """by_category strategy groups findings with the same category together."""
        f1 = _finding(
            _eid("find", "f1f1f1f1f1f1f1f1f1f1f1f1f1"),
            category=FindingCategory.UNSUPPORTED_CLAIM,
            page_id=PAGE_A,
        )
        f2 = _finding(
            _eid("find", "f2f2f2f2f2f2f2f2f2f2f2f2f2"),
            category=FindingCategory.UNSUPPORTED_CLAIM,
            page_id=PAGE_B,
        )
        batches = batch_findings([f1, f2], VAULT_ID, strategy="by_category")
        assert len(batches) == 1
        assert len(batches[0].finding_ids) == 2

    def test_by_category_separates_different_categories(self) -> None:
        """by_category strategy creates separate batches for different categories."""
        f1 = _finding(
            _eid("find", "f1f1f1f1f1f1f1f1f1f1f1f1f1"),
            category=FindingCategory.UNSUPPORTED_CLAIM,
        )
        f2 = _finding(
            _eid("find", "f2f2f2f2f2f2f2f2f2f2f2f2f2"),
            category=FindingCategory.BROKEN_REFERENCE,
        )
        batches = batch_findings([f1, f2], VAULT_ID, strategy="by_category")
        assert len(batches) == 2

    def test_auto_prefers_page_then_category(self) -> None:
        """auto strategy groups by page_id if present, falls back to category."""
        f_with_page = _finding(
            _eid("find", "f1f1f1f1f1f1f1f1f1f1f1f1f1"),
            category=FindingCategory.UNSUPPORTED_CLAIM,
            page_id=PAGE_A,
        )
        f_no_page = _finding(
            _eid("find", "f2f2f2f2f2f2f2f2f2f2f2f2f2"),
            category=FindingCategory.ORPHANED_PAGE,
            page_id=None,
        )
        batches = batch_findings([f_with_page, f_no_page], VAULT_ID, strategy="auto")
        assert len(batches) == 2

        # One batch grouped by page, one by category
        strategies = {b.batch_strategy for b in batches}
        assert "auto:page" in strategies
        assert "auto:category" in strategies

    def test_auto_two_findings_same_page_batched_together(self) -> None:
        """auto strategy groups two findings with the same page_id."""
        f1 = _finding(
            _eid("find", "f1f1f1f1f1f1f1f1f1f1f1f1f1"),
            page_id=PAGE_A,
        )
        f2 = _finding(
            _eid("find", "f2f2f2f2f2f2f2f2f2f2f2f2f2"),
            page_id=PAGE_A,
        )
        batches = batch_findings([f1, f2], VAULT_ID, strategy="auto")
        assert len(batches) == 1
        assert len(batches[0].finding_ids) == 2

    def test_batch_fingerprint_stable(self) -> None:
        """The same inputs produce the same fingerprint."""
        f1 = _finding(
            _eid("find", "f1f1f1f1f1f1f1f1f1f1f1f1f1"),
            page_id=PAGE_A,
        )
        f2 = _finding(
            _eid("find", "f2f2f2f2f2f2f2f2f2f2f2f2f2"),
            page_id=PAGE_A,
        )
        batches_a = batch_findings([f1, f2], VAULT_ID, strategy="by_page")
        batches_b = batch_findings([f1, f2], VAULT_ID, strategy="by_page")
        assert len(batches_a) == 1
        assert len(batches_b) == 1
        assert batches_a[0].batch_fingerprint == batches_b[0].batch_fingerprint

    def test_batch_fingerprint_stable_raw(self) -> None:
        """_batch_fingerprint is deterministic for the same inputs."""
        ids = [_eid("find", "f1f1f1f1f1f1f1f1f1f1f1f1f1"), _eid("find", "f2f2f2f2f2f2f2f2f2f2f2f2f2")]
        fp1 = _batch_fingerprint(VAULT_ID, "page:some_page", ids)
        fp2 = _batch_fingerprint(VAULT_ID, "page:some_page", ids)
        assert fp1 == fp2
        assert isinstance(fp1, str)
        assert len(fp1) == 32  # truncated SHA-256

    def test_batch_fingerprint_order_independent(self) -> None:
        """_batch_fingerprint sorts finding_ids, so order doesn't matter."""
        id_a = _eid("find", "aaaaaaaaaaaaaaaaaaaaaaaaaa")
        id_b = _eid("find", "bbbbbbbbbbbbbbbbbbbbbbbbbb")
        fp1 = _batch_fingerprint(VAULT_ID, "page:X", [id_a, id_b])
        fp2 = _batch_fingerprint(VAULT_ID, "page:X", [id_b, id_a])
        assert fp1 == fp2

    def test_batch_has_correct_finding_ids(self) -> None:
        """Each batch contains exactly the finding_ids from its group."""
        f1 = _finding(
            _eid("find", "f1f1f1f1f1f1f1f1f1f1f1f1f1"),
            category=FindingCategory.UNSUPPORTED_CLAIM,
            page_id=PAGE_A,
        )
        f2 = _finding(
            _eid("find", "f2f2f2f2f2f2f2f2f2f2f2f2f2"),
            category=FindingCategory.STALE_EVIDENCE,
            page_id=PAGE_A,
        )
        f3 = _finding(
            _eid("find", "f3f3f3f3f3f3f3f3f3f3f3f3f3"),
            category=FindingCategory.BROKEN_REFERENCE,
            page_id=PAGE_B,
        )
        batches = batch_findings([f1, f2, f3], VAULT_ID, strategy="by_page")
        assert len(batches) == 2

        # Sort batches by number of findings for deterministic assertion
        batches.sort(key=lambda b: len(b.finding_ids), reverse=True)

        # The batch with 2 findings should contain f1 and f2
        batch_2 = batches[0]
        assert len(batch_2.finding_ids) == 2
        assert set(batch_2.finding_ids) == {f1.finding_id, f2.finding_id}

        # The batch with 1 finding should contain f3
        batch_1 = batches[1]
        assert len(batch_1.finding_ids) == 1
        assert batch_1.finding_ids[0] == f3.finding_id

    def test_batch_vault_id_propagated(self) -> None:
        """Each batch carries the correct vault_id."""
        f1 = _finding(
            _eid("find", "f1f1f1f1f1f1f1f1f1f1f1f1f1"),
            page_id=PAGE_A,
        )
        batches = batch_findings([f1], VAULT_ID, strategy="by_page")
        assert len(batches) == 1
        assert batches[0].vault_id == VAULT_ID

    def test_by_page_no_page_falls_back_to_category_key(self) -> None:
        """by_page with findings that have no page_id groups by category key."""
        f1 = _finding(
            _eid("find", "f1f1f1f1f1f1f1f1f1f1f1f1f1"),
            category=FindingCategory.SOURCE_GAP,
            page_id=None,
        )
        f2 = _finding(
            _eid("find", "f2f2f2f2f2f2f2f2f2f2f2f2f2"),
            category=FindingCategory.SOURCE_GAP,
            page_id=None,
        )
        batches = batch_findings([f1, f2], VAULT_ID, strategy="by_page")
        assert len(batches) == 1
        assert len(batches[0].finding_ids) == 2
