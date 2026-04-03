"""Injectable ID generation policy."""
from __future__ import annotations

import os
import struct
import time
from abc import ABC, abstractmethod

from hephaestus.forgebase.domain.values import EntityId, VaultRevisionId

# Crockford's Base32 alphabet for ULID encoding
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _encode_ulid_now() -> str:
    """Generate a 26-char ULID string: 10-char timestamp + 16-char random."""
    ts_ms = int(time.time() * 1000)
    rand = struct.unpack(">Q", b"\x00" + os.urandom(7))[0]
    rand2 = struct.unpack(">H", os.urandom(2))[0]

    chars: list[str] = []
    # Encode 48-bit timestamp in 10 chars
    for _ in range(10):
        chars.append(_CROCKFORD[ts_ms & 0x1F])
        ts_ms >>= 5
    chars.reverse()

    # Encode 80-bit random in 16 chars
    combined = (rand << 16) | rand2
    rand_chars: list[str] = []
    for _ in range(16):
        rand_chars.append(_CROCKFORD[combined & 0x1F])
        combined >>= 5
    rand_chars.reverse()

    return "".join(chars) + "".join(rand_chars)


class IdGenerator(ABC):
    """Abstract ID generator — injectable for testing."""

    @abstractmethod
    def generate(self, prefix: str) -> EntityId:
        """Generate a new EntityId with the given prefix."""

    def vault_id(self) -> EntityId:
        return self.generate("vault")

    def source_id(self) -> EntityId:
        return self.generate("source")

    def page_id(self) -> EntityId:
        return self.generate("page")

    def claim_id(self) -> EntityId:
        return self.generate("claim")

    def link_id(self) -> EntityId:
        return self.generate("link")

    def workbook_id(self) -> EntityId:
        return self.generate("wb")

    def support_id(self) -> EntityId:
        return self.generate("csup")

    def derivation_id(self) -> EntityId:
        return self.generate("cder")

    def merge_id(self) -> EntityId:
        return self.generate("merge")

    def conflict_id(self) -> EntityId:
        return self.generate("conf")

    def job_id(self) -> EntityId:
        return self.generate("job")

    def finding_id(self) -> EntityId:
        return self.generate("find")

    def ref_id(self) -> EntityId:
        return self.generate("ref")

    def event_id(self) -> EntityId:
        return self.generate("evt")

    def revision_id(self) -> VaultRevisionId:
        return VaultRevisionId(f"rev_{_encode_ulid_now()}")


class UlidIdGenerator(IdGenerator):
    """Production ID generator using real ULIDs."""

    def generate(self, prefix: str) -> EntityId:
        return EntityId(f"{prefix}_{_encode_ulid_now()}")


class DeterministicIdGenerator(IdGenerator):
    """Test ID generator producing predictable sequential IDs."""

    def __init__(self, seed: int = 0) -> None:
        self._counter = seed

    def generate(self, prefix: str) -> EntityId:
        self._counter += 1
        # Pad to 26 chars to match ULID length
        ulid_part = f"{self._counter:026d}"
        return EntityId(f"{prefix}_{ulid_part}")

    def revision_id(self) -> VaultRevisionId:
        self._counter += 1
        ulid_part = f"{self._counter:026d}"
        return VaultRevisionId(f"rev_{ulid_part}")
