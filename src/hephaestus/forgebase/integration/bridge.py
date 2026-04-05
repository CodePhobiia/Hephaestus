"""Integration bridge — ABC, NoOp, and Default implementations.

The bridge is the single entry point for upstream Hephaestus systems
(Genesis, Pantheon, Research) to push artifacts into ForgeBase.

Design invariants:
  - If vault_id is ``None``, every method is a no-op.
  - ForgeBase failures are never propagated to the caller — they are
    caught, logged, and recorded as ``sync_status = "failed"`` on the
    corresponding ``KnowledgeRunRef``.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from hephaestus.forgebase.domain.values import EntityId
from hephaestus.forgebase.integration.genesis_adapter import GenesisAdapter
from hephaestus.forgebase.integration.pantheon_adapter import PantheonAdapter
from hephaestus.forgebase.integration.research_adapter import ResearchAdapter

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Abstract bridge
# ---------------------------------------------------------------------------


class ForgeBaseIntegrationBridge(ABC):
    """Bridge interface for upstream Hephaestus systems to push artifacts into ForgeBase.

    Injected at composition time.  If ``vault_id`` is absent the bridge
    is a no-op.
    """

    @abstractmethod
    async def on_genesis_completed(
        self,
        vault_id: EntityId | None,
        run_id: str,
        report: Any,
    ) -> None: ...

    @abstractmethod
    async def on_pantheon_completed(
        self,
        vault_id: EntityId | None,
        run_id: str,
        state: Any,
    ) -> None: ...

    @abstractmethod
    async def on_research_completed(
        self,
        vault_id: EntityId | None,
        run_id: str,
        artifacts: list[Any],
    ) -> None: ...


# ---------------------------------------------------------------------------
# No-op bridge (ForgeBase not configured)
# ---------------------------------------------------------------------------


class NoOpBridge(ForgeBaseIntegrationBridge):
    """No-op bridge for when ForgeBase is not configured."""

    async def on_genesis_completed(
        self,
        vault_id: EntityId | None,
        run_id: str,
        report: Any,
    ) -> None:
        pass

    async def on_pantheon_completed(
        self,
        vault_id: EntityId | None,
        run_id: str,
        state: Any,
    ) -> None:
        pass

    async def on_research_completed(
        self,
        vault_id: EntityId | None,
        run_id: str,
        artifacts: list[Any],
    ) -> None:
        pass


# ---------------------------------------------------------------------------
# Production bridge — delegates to specialised adapters
# ---------------------------------------------------------------------------


class DefaultForgeBaseBridge(ForgeBaseIntegrationBridge):
    """Production bridge that delegates to specialised adapters.

    Each callback:
      1. Short-circuits when ``vault_id is None``.
      2. Delegates to the adapter in a ``try / except`` block so
         ForgeBase failures never propagate upstream.
    """

    def __init__(
        self,
        genesis_adapter: GenesisAdapter,
        pantheon_adapter: PantheonAdapter,
        research_adapter: ResearchAdapter,
    ) -> None:
        self._genesis = genesis_adapter
        self._pantheon = pantheon_adapter
        self._research = research_adapter

    async def on_genesis_completed(
        self,
        vault_id: EntityId | None,
        run_id: str,
        report: Any,
    ) -> None:
        if vault_id is None:
            return
        try:
            await self._genesis.handle_genesis_completed(vault_id, run_id, report)
        except Exception:
            logger.exception(
                "ForgeBase bridge: Genesis sync failed for run_id=%s, vault_id=%s",
                run_id,
                vault_id,
            )

    async def on_pantheon_completed(
        self,
        vault_id: EntityId | None,
        run_id: str,
        state: Any,
    ) -> None:
        if vault_id is None:
            return
        try:
            await self._pantheon.handle_pantheon_completed(vault_id, run_id, state)
        except Exception:
            logger.exception(
                "ForgeBase bridge: Pantheon sync failed for run_id=%s, vault_id=%s",
                run_id,
                vault_id,
            )

    async def on_research_completed(
        self,
        vault_id: EntityId | None,
        run_id: str,
        artifacts: list[Any],
    ) -> None:
        if vault_id is None:
            return
        try:
            await self._research.handle_research_completed(vault_id, run_id, artifacts)
        except Exception:
            logger.exception(
                "ForgeBase bridge: Research sync failed for run_id=%s, vault_id=%s",
                run_id,
                vault_id,
            )
