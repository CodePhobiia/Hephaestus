"""Repository contract for compile manifests (source + vault synthesis)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from hephaestus.forgebase.domain.models import SourceCompileManifest, VaultSynthesisManifest
from hephaestus.forgebase.domain.values import EntityId, Version


class CompileManifestRepository(ABC):
    @abstractmethod
    async def create_source_manifest(self, manifest: SourceCompileManifest) -> None: ...

    @abstractmethod
    async def get_source_manifest(self, manifest_id: EntityId) -> SourceCompileManifest | None: ...

    @abstractmethod
    async def get_source_manifest_for(
        self,
        source_id: EntityId,
        source_version: Version,
    ) -> SourceCompileManifest | None: ...

    @abstractmethod
    async def create_vault_manifest(self, manifest: VaultSynthesisManifest) -> None: ...

    @abstractmethod
    async def get_vault_manifest(self, manifest_id: EntityId) -> VaultSynthesisManifest | None: ...

    @abstractmethod
    async def get_latest_vault_manifest(
        self,
        vault_id: EntityId,
        workbook_id: EntityId | None = None,
    ) -> VaultSynthesisManifest | None: ...

    # Join table methods for VaultSynthesisManifest associations
    @abstractmethod
    async def add_synthesis_source_manifest(
        self,
        synthesis_id: EntityId,
        source_manifest_id: EntityId,
    ) -> None: ...

    @abstractmethod
    async def add_synthesis_page_created(
        self,
        synthesis_id: EntityId,
        page_id: EntityId,
    ) -> None: ...

    @abstractmethod
    async def add_synthesis_page_updated(
        self,
        synthesis_id: EntityId,
        page_id: EntityId,
    ) -> None: ...

    @abstractmethod
    async def add_synthesis_dirty_consumed(
        self,
        synthesis_id: EntityId,
        marker_id: EntityId,
    ) -> None: ...
