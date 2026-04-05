"""Vault queries — read vault information."""

from __future__ import annotations

from hephaestus.forgebase.domain.models import Vault
from hephaestus.forgebase.domain.values import EntityId
from hephaestus.forgebase.repository.vault_repo import VaultRepository


async def get_vault(
    vaults: VaultRepository,
    vault_id: EntityId,
) -> Vault | None:
    """Get a vault by ID."""
    return await vaults.get(vault_id)


async def list_vaults(
    vaults: VaultRepository,
) -> list[Vault]:
    """List all vaults."""
    return await vaults.list_all()
