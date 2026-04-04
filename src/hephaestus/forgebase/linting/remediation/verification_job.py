"""FindingVerificationJob — verify findings after repair workbook merge."""
from __future__ import annotations

from typing import Callable

from hephaestus.forgebase.domain.enums import (
    FindingDisposition,
    RemediationStatus,
)
from hephaestus.forgebase.domain.values import ActorRef, EntityId
from hephaestus.forgebase.linting.detectors.base import LintDetector
from hephaestus.forgebase.linting.state import VaultLintState
from hephaestus.forgebase.repository.uow import AbstractUnitOfWork
from hephaestus.forgebase.service.lint_service import LintService


class FindingVerificationJob:
    """Durable job: verify findings after a repair workbook is merged.

    For each finding, runs the detector that originally produced it to
    check whether the finding is now resolved in the current canonical
    state.

    Steps:
      1. Build VaultLintState for current canonical state
      2. For each finding:
         a. Get the detector by category
         b. Run detector.detect() to get new findings
         c. Call detector.is_resolved(original, current_state, new_findings)
         d. If resolved: update disposition -> RESOLVED, status -> VERIFIED
         e. If not resolved: reopen finding
      3. Return {finding_id: resolved}
    """

    def __init__(
        self,
        uow_factory: Callable[[], AbstractUnitOfWork],
        detectors: dict[str, LintDetector],  # category name -> detector
        lint_service: LintService,
        default_actor: ActorRef,
    ) -> None:
        self._uow_factory = uow_factory
        self._detectors = detectors
        self._lint_service = lint_service
        self._default_actor = default_actor

    async def execute(
        self,
        finding_ids: list[EntityId],
        vault_id: EntityId,
    ) -> dict[EntityId, bool]:
        """Verify findings and return {finding_id: resolved}."""

        results: dict[EntityId, bool] = {}

        # -- 1. Build VaultLintState for canonical state ------------------
        uow = self._uow_factory()
        async with uow:
            state = VaultLintState(uow, vault_id, workbook_id=None)

            # -- 2. For each finding, run detector-specific verification --
            for finding_id in finding_ids:
                finding = await uow.findings.get(finding_id)
                if finding is None:
                    results[finding_id] = False
                    continue

                category_name = finding.category.value
                detector = self._detectors.get(category_name)
                if detector is None:
                    # No detector for this category -- cannot verify
                    results[finding_id] = False
                    continue

                # 2b. Run detector.detect() on current state
                new_findings = await detector.detect(state)

                # 2c. Check if resolved
                resolved = await detector.is_resolved(
                    finding, state, new_findings,
                )
                results[finding_id] = resolved

            await uow.rollback()

        # -- 3. Update findings based on verification results -------------
        for finding_id, resolved in results.items():
            if resolved:
                # Mark as resolved + verified
                await self._lint_service.update_finding_disposition(
                    finding_id,
                    FindingDisposition.RESOLVED,
                )
                await self._lint_service.update_finding_remediation(
                    finding_id,
                    RemediationStatus.VERIFIED,
                )
            else:
                # Reopen the finding
                await self._lint_service.reopen_finding(finding_id)

        return results
