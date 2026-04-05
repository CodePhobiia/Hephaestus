"""ForgeBase domain value objects — immutable, no I/O."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Self

from hephaestus.forgebase.domain.enums import ActorType

_ENTITY_ID_RE = re.compile(r"^([a-z][a-z0-9]*)_([0-9A-Za-z]{20,30})$")


@dataclass(frozen=True, slots=True)
class EntityId:
    """Prefixed ULID identifier. Format: '{prefix}_{ulid_part}'."""

    _raw: str

    def __post_init__(self) -> None:
        if not self._raw:
            raise ValueError("EntityId cannot be empty")
        m = _ENTITY_ID_RE.match(self._raw)
        if not m:
            raise ValueError(f"EntityId must match '{{prefix}}_{{ulid}}', got: {self._raw!r}")

    @property
    def prefix(self) -> str:
        return self._raw.split("_", 1)[0]

    @property
    def ulid_part(self) -> str:
        return self._raw.split("_", 1)[1]

    def __str__(self) -> str:
        return self._raw

    def __repr__(self) -> str:
        return f"EntityId({self._raw!r})"

    def __hash__(self) -> int:
        return hash(self._raw)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, EntityId):
            return self._raw == other._raw
        return NotImplemented


class VaultRevisionId(EntityId):
    """Typed EntityId for vault revisions. Prefix: 'rev'."""

    pass


@dataclass(frozen=True, slots=True, order=True)
class Version:
    """Monotonic version number (1, 2, 3...)."""

    number: int

    def __post_init__(self) -> None:
        if self.number < 1:
            raise ValueError(f"Version must be >= 1, got {self.number}")

    def next(self) -> Version:
        return Version(self.number + 1)

    def __str__(self) -> str:
        return str(self.number)


@dataclass(frozen=True, slots=True)
class ContentHash:
    """SHA-256 content hash."""

    sha256: str

    @classmethod
    def from_bytes(cls, data: bytes) -> ContentHash:
        return cls(sha256=hashlib.sha256(data).hexdigest())

    def __hash__(self) -> int:
        return hash(self.sha256)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ContentHash):
            return self.sha256 == other.sha256
        return NotImplemented


@dataclass(frozen=True, slots=True)
class BlobRef:
    """Opaque reference to content in blob store."""

    content_hash: ContentHash
    size_bytes: int
    mime_type: str


@dataclass(frozen=True, slots=True)
class PendingContentRef:
    """Staged blob ref — resolves to BlobRef after finalization."""

    staging_key: str
    content_hash: ContentHash
    size_bytes: int
    mime_type: str

    def to_blob_ref(self) -> BlobRef:
        return BlobRef(
            content_hash=self.content_hash,
            size_bytes=self.size_bytes,
            mime_type=self.mime_type,
        )


@dataclass(frozen=True, slots=True)
class ActorRef:
    """Identifies who performed an action."""

    actor_type: ActorType
    actor_id: str

    @classmethod
    def system(cls) -> Self:
        return cls(actor_type=ActorType.SYSTEM, actor_id="system")


@dataclass(frozen=True, slots=True)
class EvidenceSegmentRef:
    """Stable reference into a normalized source artifact."""

    source_id: EntityId
    source_version: Version
    segment_start: int
    segment_end: int
    section_key: str | None
    preview_text: str

    @property
    def length(self) -> int:
        return self.segment_end - self.segment_start
