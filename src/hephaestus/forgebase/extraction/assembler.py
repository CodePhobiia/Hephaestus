"""VaultContextAssembler — extracts structured knowledge from a vault for invention runs.

Produces three products with different trust levels:
  1. PriorArtBaselinePack  -- for DeepForge extra_blocked_paths (strictest)
  2. DomainContextPack     -- for LensSelector reference_context (broadest)
  3. ConstraintDossierPack -- for Pantheon baseline_dossier (governance-grade)

Each pack is assembled via a separate method so callers can request only
what they need.  ``assemble_all`` is a convenience that returns all three.
"""

from __future__ import annotations

from collections.abc import Callable

from hephaestus.forgebase.domain.values import EntityId
from hephaestus.forgebase.extraction.baseline_pack import extract_baseline_pack
from hephaestus.forgebase.extraction.context_pack import extract_domain_context_pack
from hephaestus.forgebase.extraction.dossier_pack import extract_constraint_dossier_pack
from hephaestus.forgebase.extraction.models import (
    ConstraintDossierPack,
    DomainContextPack,
    PriorArtBaselinePack,
)
from hephaestus.forgebase.extraction.policy import DEFAULT_EXTRACTION_POLICY, ExtractionPolicy
from hephaestus.forgebase.repository.uow import AbstractUnitOfWork


class VaultContextAssembler:
    """Extracts structured knowledge from a vault for invention runs.

    Produces three products with different trust levels:
      1. PriorArtBaselinePack  -- for DeepForge extra_blocked_paths (strictest)
      2. DomainContextPack     -- for LensSelector reference_context (broadest)
      3. ConstraintDossierPack -- for Pantheon baseline_dossier (governance-grade)
    """

    def __init__(
        self,
        uow_factory: Callable[[], AbstractUnitOfWork],
        policy: ExtractionPolicy | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._policy = policy or DEFAULT_EXTRACTION_POLICY

    async def assemble_prior_art_pack(
        self,
        vault_id: EntityId,
        workbook_id: EntityId | None = None,
    ) -> PriorArtBaselinePack:
        """Extract prior-art baselines for DeepForge extra_blocked_paths."""
        uow = self._uow_factory()
        async with uow:
            pack = await extract_baseline_pack(uow, vault_id, self._policy, workbook_id)
            await uow.rollback()  # read-only
        return pack

    async def assemble_domain_context_pack(
        self,
        vault_id: EntityId,
        workbook_id: EntityId | None = None,
    ) -> DomainContextPack:
        """Extract domain context for LensSelector reference_context."""
        uow = self._uow_factory()
        async with uow:
            pack = await extract_domain_context_pack(uow, vault_id, self._policy, workbook_id)
            await uow.rollback()  # read-only
        return pack

    async def assemble_constraint_dossier_pack(
        self,
        vault_id: EntityId,
        workbook_id: EntityId | None = None,
    ) -> ConstraintDossierPack:
        """Extract constraints for Pantheon baseline_dossier."""
        uow = self._uow_factory()
        async with uow:
            pack = await extract_constraint_dossier_pack(uow, vault_id, self._policy, workbook_id)
            await uow.rollback()  # read-only
        return pack

    async def assemble_all(
        self,
        vault_id: EntityId,
        workbook_id: EntityId | None = None,
    ) -> tuple[PriorArtBaselinePack, DomainContextPack, ConstraintDossierPack]:
        """Assemble all three packs. Could optimize to share one UoW, but correctness first."""
        baseline = await self.assemble_prior_art_pack(vault_id, workbook_id)
        context = await self.assemble_domain_context_pack(vault_id, workbook_id)
        dossier = await self.assemble_constraint_dossier_pack(vault_id, workbook_id)
        return baseline, context, dossier
