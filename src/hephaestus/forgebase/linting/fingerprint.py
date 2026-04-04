"""Finding fingerprint computation and deduplication logic.

The fingerprint is a stable SHA-256 hash that uniquely identifies a
finding based on its *semantic identity* — category, affected entities,
normalized subject, optional workbook scope, and detector version.

Two findings with the same fingerprint are considered the same issue.
The ``dedup_findings`` function uses fingerprints to decide which raw
findings are genuinely new, which should reopen a previously-closed
finding, and which are duplicates of currently-open findings (skip).
"""
from __future__ import annotations

import hashlib

from hephaestus.forgebase.domain.enums import FindingDisposition
from hephaestus.forgebase.domain.models import LintFinding
from hephaestus.forgebase.domain.values import EntityId
from hephaestus.forgebase.linting.detectors.base import RawFinding


def compute_fingerprint(
    category: str,
    affected_entity_ids: list[str],
    normalized_subject: str,
    workbook_id: str | None,
    detector_version: str,
) -> str:
    """Compute a stable SHA-256 fingerprint for a finding.

    The inputs are sorted/normalized so that the hash is independent of
    the order in which entity IDs are supplied.

    Parameters
    ----------
    category:
        The finding category value (e.g. ``"unsupported_claim"``).
    affected_entity_ids:
        String representations of affected entity IDs.
    normalized_subject:
        A human-readable subject string that identifies *what* the
        finding is about (e.g. the claim text, page title, etc.).
    workbook_id:
        Optional workbook scope.  ``None`` means canonical/vault scope.
    detector_version:
        Semantic version of the detector that produced this finding.

    Returns
    -------
    str
        A 64-character lowercase hex SHA-256 digest.
    """
    # Sort entity IDs for order independence
    sorted_ids = sorted(affected_entity_ids)

    # Build a canonical string by joining components with a delimiter
    # that is unlikely to appear in any component value.
    parts: list[str] = [
        category,
        ",".join(sorted_ids),
        normalized_subject,
        workbook_id if workbook_id is not None else "",
        detector_version,
    ]
    canonical = "\x00".join(parts)

    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# Dispositions that indicate the finding is closed/inactive and should
# be reopened if the same issue reappears.
_REOPENABLE_DISPOSITIONS: frozenset[FindingDisposition] = frozenset({
    FindingDisposition.RESOLVED,
    FindingDisposition.FALSE_POSITIVE,
    FindingDisposition.WONT_FIX,
})


def dedup_findings(
    raw_findings: list[RawFinding],
    existing_findings: list[LintFinding],
    vault_id: EntityId,
    workbook_id: EntityId | None,
    detector_version: str,
) -> tuple[list[RawFinding], list[LintFinding]]:
    """Deduplicate raw findings against existing persisted findings.

    For each raw finding a fingerprint is computed.  It is then compared
    against the fingerprints of *existing_findings*:

    * **Existing OPEN/ACTIVE finding with same fingerprint** -- skip
      (the issue is already tracked).
    * **Existing RESOLVED/FALSE_POSITIVE/WONT_FIX finding with same
      fingerprint** -- add to the *reopen* list.
    * **No existing finding with that fingerprint** -- add to the *new*
      list.

    If two raw findings produce the same fingerprint, only the first is
    treated as new (the duplicate is silently dropped).

    Parameters
    ----------
    raw_findings:
        Findings just produced by detectors.
    existing_findings:
        Previously persisted ``LintFinding`` records for the vault
        (and optionally workbook).
    vault_id:
        Current vault ID (unused in fingerprint, but scopes the query).
    workbook_id:
        Optional workbook scope (included in fingerprint).
    detector_version:
        The detector version string to embed in fingerprints.

    Returns
    -------
    tuple[list[RawFinding], list[LintFinding]]
        ``(new_findings, findings_to_reopen)``
    """
    wb_str = str(workbook_id) if workbook_id is not None else None

    # Build a lookup from fingerprint -> existing LintFinding
    existing_by_fp: dict[str, LintFinding] = {}
    for ef in existing_findings:
        if ef.finding_fingerprint is not None:
            existing_by_fp[ef.finding_fingerprint] = ef

    new_findings: list[RawFinding] = []
    findings_to_reopen: list[LintFinding] = []
    seen_fps: set[str] = set()

    for raw in raw_findings:
        fp = compute_fingerprint(
            category=raw.category.value,
            affected_entity_ids=[str(eid) for eid in raw.affected_entity_ids],
            normalized_subject=raw.normalized_subject,
            workbook_id=wb_str,
            detector_version=detector_version,
        )

        # Deduplicate within the same raw batch
        if fp in seen_fps:
            continue
        seen_fps.add(fp)

        existing = existing_by_fp.get(fp)
        if existing is None:
            # No prior finding with this fingerprint -- genuinely new
            new_findings.append(raw)
        elif existing.disposition in _REOPENABLE_DISPOSITIONS:
            # Was closed/dismissed but issue resurfaced -- reopen
            findings_to_reopen.append(existing)
        # else: existing is ACTIVE (open) -- skip, already tracked

    return new_findings, findings_to_reopen
