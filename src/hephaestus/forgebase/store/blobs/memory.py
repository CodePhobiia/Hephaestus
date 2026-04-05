"""In-memory content store for testing."""

from __future__ import annotations

import uuid

from hephaestus.forgebase.domain.values import BlobRef, ContentHash, PendingContentRef
from hephaestus.forgebase.repository.content_store import StagedContentStore


class InMemoryContentStore(StagedContentStore):
    """In-memory staged content store for tests. No filesystem."""

    def __init__(self) -> None:
        self._permanent: dict[str, bytes] = {}  # sha256 -> bytes
        self._staged: dict[str, bytes] = {}  # staging_key -> bytes
        self._staged_refs: list[PendingContentRef] = []

    async def stage(self, content: bytes, mime_type: str) -> PendingContentRef:
        staging_key = uuid.uuid4().hex
        content_hash = ContentHash.from_bytes(content)
        self._staged[staging_key] = content
        ref = PendingContentRef(
            staging_key=staging_key,
            content_hash=content_hash,
            size_bytes=len(content),
            mime_type=mime_type,
        )
        self._staged_refs.append(ref)
        return ref

    async def finalize(self) -> None:
        for ref in self._staged_refs:
            data = self._staged.pop(ref.staging_key, None)
            if data is not None:
                self._permanent[ref.content_hash.sha256] = data
        self._staged_refs.clear()

    async def abort(self) -> None:
        self._staged.clear()
        self._staged_refs.clear()

    async def read(self, ref: BlobRef) -> bytes:
        key = ref.content_hash.sha256
        if key not in self._permanent:
            raise KeyError(f"Content not found: {key[:12]}...")
        return self._permanent[key]

    async def delete(self, ref: BlobRef) -> None:
        self._permanent.pop(ref.content_hash.sha256, None)
