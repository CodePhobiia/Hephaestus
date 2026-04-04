"""LintEngine -- orchestrates a full vault lint pass.

Ties together detectors, fingerprinting, dedup, triage, scoring,
and LintReport generation into a single ``run_lint()`` operation.
"""
from __future__ import annotations

import logging
from collections import Counter
from typing import Callable

from hephaestus.forgebase.domain.enums import (
    FindingSeverity,
    RemediationStatus,
)
from hephaestus.forgebase.domain.models import LintReport
from hephaestus.forgebase.domain.values import ActorRef, EntityId
from hephaestus.forgebase.linting.detectors.base import LintDetector
from hephaestus.forgebase.linting.fingerprint import compute_fingerprint, dedup_findings
from hephaestus.forgebase.linting.remediation.policy import (
    DEFAULT_REMEDIATION_POLICY,
    RemediationPolicy,
)
from hephaestus.forgebase.linting.remediation.triage import triage_finding
from hephaestus.forgebase.linting.scoring import (
    DEFAULT_DEBT_POLICY,
    DebtScoringPolicy,
    compute_debt_score,
)
from hephaestus.forgebase.linting.state import VaultLintState
from hephaestus.forgebase.repository.uow import AbstractUnitOfWork
from hephaestus.forgebase.service.lint_service import LintService

logger = logging.getLogger(__name__)


class LintEngine:
    """Orchestrates a full vault lint pass."""

    def __init__(
        self,
        uow_factory: Callable[[], AbstractUnitOfWork],
        detectors: list[LintDetector],
        lint_service: LintService,
        default_actor: ActorRef,
        remediation_policy: RemediationPolicy | None = None,
        debt_policy: DebtScoringPolicy | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._detectors = detectors
        self._lint_service = lint_service
        self._default_actor = default_actor
        self._remediation_policy = remediation_policy
        self._debt_policy = debt_policy

    async def run_lint(
        self,
        vault_id: EntityId,
        workbook_id: EntityId | None = None,
        config: dict | None = None,
    ) -> LintReport:
        """Full vault lint pass.

        1. Schedule LintJob via LintService
        2. Acquire UoW for reading state
        3. Build VaultLintState (query facade)
        4. Run each detector -> collect RawFindings
        5. Fingerprint each RawFinding + dedup against existing findings
        6. Open new findings via LintService (with fingerprint, remediation_status=OPEN)
        7. Reopen resolved findings whose fingerprint reappears
        8. Triage: assign remediation route per policy
        9. Compute knowledge debt score
        10. Persist LintReport
        11. Complete lint job
        12. Return LintReport
        """
        # ------------------------------------------------------------------
        # Step 1: Schedule job
        # ------------------------------------------------------------------
        wb_key = str(workbook_id) if workbook_id else "canonical"
        job = await self._lint_service.schedule_lint(
            vault_id,
            workbook_id=workbook_id,
            config=config or {},
            idempotency_key=f"lint:{vault_id}:{wb_key}",
        )

        # ------------------------------------------------------------------
        # Steps 2-3: Build state (read-only UoW)
        # ------------------------------------------------------------------
        from hephaestus.forgebase.linting.detectors.base import RawFinding

        all_raw_findings: list[RawFinding] = []

        uow = self._uow_factory()
        async with uow:
            state = VaultLintState(uow, vault_id, workbook_id)

            # ------------------------------------------------------------------
            # Step 4: Run detectors
            # ------------------------------------------------------------------
            for detector in self._detectors:
                try:
                    findings = await detector.detect(state)
                    all_raw_findings.extend(findings)
                except Exception as e:
                    logger.error("Detector %s failed: %s", detector.name, e)
                    # Continue with other detectors

            # ------------------------------------------------------------------
            # Step 5: Fingerprint + dedup
            # ------------------------------------------------------------------
            existing = await state.existing_findings()

            # Use the first detector's version as default, or "1.0.0"
            detector_version = "1.0.0"

            new_findings, to_reopen = dedup_findings(
                all_raw_findings, existing, vault_id, workbook_id, detector_version
            )

            # Cache pages/claims counts for scoring before closing UoW
            pages_list = await state.pages()
            claims_dict = await state.claims()
            vault_size = len(pages_list) + len(claims_dict)

            await uow.rollback()  # read-only pass, no mutations

        # ------------------------------------------------------------------
        # Step 6: Open new findings
        # ------------------------------------------------------------------
        from hephaestus.forgebase.domain.models import LintFinding

        opened_findings: list[LintFinding] = []
        wb_str = str(workbook_id) if workbook_id is not None else None

        for raw in new_findings:
            fp = compute_fingerprint(
                category=raw.category.value,
                affected_entity_ids=[str(eid) for eid in raw.affected_entity_ids],
                normalized_subject=raw.normalized_subject,
                workbook_id=wb_str,
                detector_version=detector_version,
            )
            finding = await self._lint_service.open_finding(
                job_id=job.job_id,
                vault_id=vault_id,
                category=raw.category,
                severity=raw.severity,
                description=raw.description,
                page_id=raw.page_id,
                claim_id=raw.claim_id,
                suggested_action=raw.suggested_action,
                finding_fingerprint=fp,
                detector_version=detector_version,
                confidence=raw.confidence,
                affected_entity_ids=raw.affected_entity_ids,
            )
            opened_findings.append(finding)

        # ------------------------------------------------------------------
        # Step 7: Reopen resolved findings
        # ------------------------------------------------------------------
        for finding in to_reopen:
            await self._lint_service.reopen_finding(finding.finding_id)

        # ------------------------------------------------------------------
        # Step 8: Triage
        # ------------------------------------------------------------------
        policy = self._remediation_policy or DEFAULT_REMEDIATION_POLICY
        for finding in opened_findings:
            route, source = triage_finding(finding, policy)
            await self._lint_service.update_finding_remediation(
                finding.finding_id,
                remediation_status=RemediationStatus.TRIAGED,
                route=route,
                route_source=source,
            )

        # ------------------------------------------------------------------
        # Step 9: Compute debt score
        # ------------------------------------------------------------------
        # Count all active findings by severity (opened + reopened)
        severity_counter: Counter[FindingSeverity] = Counter()
        for f in opened_findings:
            severity_counter[f.severity] += 1
        for f in to_reopen:
            severity_counter[f.severity] += 1

        findings_by_severity_enum: dict[FindingSeverity, int] = dict(severity_counter)
        debt_pol = self._debt_policy or DEFAULT_DEBT_POLICY
        score = compute_debt_score(findings_by_severity_enum, vault_size, debt_pol)

        # ------------------------------------------------------------------
        # Step 10: Persist LintReport
        # ------------------------------------------------------------------
        # Build category counts
        category_counter: Counter[str] = Counter()
        for f in opened_findings:
            category_counter[f.category.value] += 1
        for f in to_reopen:
            category_counter[f.category.value] += 1

        severity_str_counter: dict[str, int] = {
            sev.value: count for sev, count in severity_counter.items()
        }

        total_finding_count = len(opened_findings) + len(to_reopen)

        uow2 = self._uow_factory()
        async with uow2:
            report = LintReport(
                report_id=uow2.id_generator.report_id(),
                vault_id=vault_id,
                workbook_id=workbook_id,
                job_id=job.job_id,
                finding_count=total_finding_count,
                findings_by_category=dict(category_counter),
                findings_by_severity=severity_str_counter,
                debt_score=score,
                debt_policy_version=debt_pol.policy_version,
                raw_counts={
                    "detectors_run": len(self._detectors),
                    "raw_findings": len(all_raw_findings),
                    "new_findings": len(new_findings),
                    "reopened_findings": len(to_reopen),
                    "deduplicated": len(all_raw_findings) - len(new_findings) - len(to_reopen),
                },
                created_at=uow2.clock.now(),
            )
            await uow2.lint_reports.create(report)
            await uow2.commit()

        # ------------------------------------------------------------------
        # Step 11: Complete lint job
        # ------------------------------------------------------------------
        await self._lint_service.complete_lint(job.job_id)

        # ------------------------------------------------------------------
        # Step 12: Return report
        # ------------------------------------------------------------------
        return report
