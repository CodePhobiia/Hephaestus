"""Finding batching for repair workbook grouping."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import datetime

from hephaestus.forgebase.domain.models import LintFinding, RepairBatch
from hephaestus.forgebase.domain.values import EntityId


def batch_findings(
    findings: list[LintFinding],
    vault_id: EntityId,
    strategy: str = "auto",
    id_generator: object | None = None,
) -> list[RepairBatch]:
    """Group findings into repair batches.

    Strategies:
    - by_page: group by page_id
    - by_category: group by finding category
    - auto: by_page first (for findings with page_id), then by_category for the rest
    """
    if not findings:
        return []

    if strategy == "by_page":
        groups = _group_by_page(findings)
    elif strategy == "by_category":
        groups = _group_by_category(findings)
    else:  # auto
        groups = _group_auto(findings)

    batches = []
    for group_key, group_findings in groups.items():
        finding_ids = [f.finding_id for f in group_findings]
        fingerprint = _batch_fingerprint(vault_id, group_key, finding_ids)

        batch = RepairBatch(
            batch_id=(
                id_generator.batch_id()
                if id_generator
                else EntityId(f"batch_{hashlib.sha256(fingerprint.encode()).hexdigest()[:26]}")
            ),
            vault_id=vault_id,
            batch_fingerprint=fingerprint,
            batch_strategy=(strategy if strategy != "auto" else f"auto:{group_key.split(':')[0]}"),
            batch_reason=f"Grouped {len(group_findings)} findings by {group_key}",
            finding_ids=finding_ids,
            policy_version="1.0.0",
            workbook_id=None,
            created_by_job_id=group_findings[0].job_id,
            created_at=datetime.now(),
        )
        batches.append(batch)

    return batches


def _group_by_page(
    findings: list[LintFinding],
) -> dict[str, list[LintFinding]]:
    groups: dict[str, list[LintFinding]] = defaultdict(list)
    for f in findings:
        key = f"page:{f.page_id}" if f.page_id else f"no_page:{f.category.value}"
        groups[key].append(f)
    return groups


def _group_by_category(
    findings: list[LintFinding],
) -> dict[str, list[LintFinding]]:
    groups: dict[str, list[LintFinding]] = defaultdict(list)
    for f in findings:
        groups[f"category:{f.category.value}"].append(f)
    return groups


def _group_auto(
    findings: list[LintFinding],
) -> dict[str, list[LintFinding]]:
    groups: dict[str, list[LintFinding]] = defaultdict(list)
    for f in findings:
        if f.page_id:
            groups[f"page:{f.page_id}"].append(f)
        else:
            groups[f"category:{f.category.value}"].append(f)
    return groups


def _batch_fingerprint(
    vault_id: EntityId,
    group_key: str,
    finding_ids: list[EntityId],
) -> str:
    parts = [str(vault_id), group_key] + sorted(str(fid) for fid in finding_ids)
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:32]
