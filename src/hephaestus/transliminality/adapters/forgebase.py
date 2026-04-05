"""ForgeBase adapter — vault access for transliminality.

Bridges the ForgeBase domain layer to transliminality's own types,
providing vault metadata access via UoW.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from hephaestus.forgebase.domain.values import EntityId
from hephaestus.transliminality.domain.models import VaultMetadata

if TYPE_CHECKING:
    from hephaestus.forgebase.domain.models import Vault
    from hephaestus.forgebase.repository.uow import AbstractUnitOfWork

logger = logging.getLogger(__name__)


def _vault_to_metadata(vault: Vault) -> VaultMetadata:
    """Extract routing-relevant metadata from a ForgeBase Vault."""
    config = vault.config or {}
    raw_tags = config.get("tags", [])
    return VaultMetadata(
        vault_id=vault.vault_id,
        name=vault.name,
        description=vault.description,
        domain=str(config.get("domain", "")),
        tags=tuple(str(t) for t in raw_tags if isinstance(t, str)),
    )


class ForgeBaseVaultAdapter:
    """Provides vault metadata access for the transliminality engine.

    Implements the ``VaultMetadataProvider`` protocol defined in
    ``service/engine.py``.
    """

    def __init__(
        self,
        uow_factory: Callable[[], AbstractUnitOfWork],
    ) -> None:
        self._uow_factory = uow_factory

    async def list_vault_metadata(self) -> list[VaultMetadata]:
        """List all vaults with routing-relevant metadata."""
        uow = self._uow_factory()
        async with uow:
            vaults = await uow.vaults.list_all()
            return [_vault_to_metadata(v) for v in vaults]

    async def get_vault_metadata(self, vault_id: EntityId) -> VaultMetadata | None:
        """Get metadata for a single vault."""
        uow = self._uow_factory()
        async with uow:
            vault = await uow.vaults.get(vault_id)
            if vault is None:
                return None
            return _vault_to_metadata(vault)

    async def vault_exists(self, vault_id: EntityId) -> bool:
        """Check whether a vault exists."""
        uow = self._uow_factory()
        async with uow:
            vault = await uow.vaults.get(vault_id)
            return vault is not None
