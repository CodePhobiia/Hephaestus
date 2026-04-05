"""Abstract content/blob storage contract with staging semantics."""

from __future__ import annotations

from abc import ABC, abstractmethod

from hephaestus.forgebase.domain.values import BlobRef, PendingContentRef


class StagedContentStore(ABC):
    """Staged blob store — stage on write, finalize on commit, abort on rollback."""

    @abstractmethod
    async def stage(self, content: bytes, mime_type: str) -> PendingContentRef: ...

    @abstractmethod
    async def finalize(self) -> None:
        """Promote all staged content to permanent storage."""

    @abstractmethod
    async def abort(self) -> None:
        """Discard all staged content."""

    @abstractmethod
    async def read(self, ref: BlobRef) -> bytes: ...

    @abstractmethod
    async def delete(self, ref: BlobRef) -> None: ...
