# ForgeBase Foundation Platform Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the production-grade foundation for ForgeBase — storage, domain model, provenance, branching, events, internal APIs, and run integration hooks — that the entire ForgeBase system will build upon.

**Architecture:** Clean layered architecture with strict dependency rules: pure domain models → abstract repository contracts → dual-backend store implementations (SQLite + Postgres) → command services with UoW transactions → transactional outbox events → read-model query layer → integration bridge. Everything is async, branch-aware, and tested on both backends.

**Tech Stack:** Python 3.11+, aiosqlite, asyncpg, pytest-asyncio, dataclasses, ULID generation (custom lightweight)

**Spec:** `docs/superpowers/specs/2026-04-03-forgebase-foundation-platform-design.md`

---

## File Structure

```
src/hephaestus/forgebase/
  __init__.py
  factory.py

  domain/
    __init__.py
    values.py
    enums.py
    models.py
    event_types.py
    merge.py
    conflicts.py

  repository/
    __init__.py
    vault_repo.py
    source_repo.py
    page_repo.py
    claim_repo.py
    claim_support_repo.py
    claim_derivation_repo.py
    link_repo.py
    workbook_repo.py
    merge_proposal_repo.py
    merge_conflict_repo.py
    job_repo.py
    finding_repo.py
    run_ref_repo.py
    run_artifact_repo.py
    content_store.py
    uow.py

  store/
    __init__.py
    sqlite/
      __init__.py
      schema.py
      uow.py
      vault_repo.py
      source_repo.py
      page_repo.py
      claim_repo.py
      claim_support_repo.py
      claim_derivation_repo.py
      link_repo.py
      workbook_repo.py
      merge_proposal_repo.py
      merge_conflict_repo.py
      job_repo.py
      finding_repo.py
      run_ref_repo.py
      run_artifact_repo.py
      event_repo.py
    blobs/
      __init__.py
      local_fs.py
      memory.py

  service/
    __init__.py
    id_generator.py
    vault_service.py
    ingest_service.py
    page_service.py
    claim_service.py
    link_service.py
    branch_service.py
    merge_service.py
    compile_service.py
    lint_service.py
    run_integration_service.py

  events/
    __init__.py
    dispatcher.py
    consumers.py
    fanout.py

  query/
    __init__.py
    vault_queries.py
    source_queries.py
    page_queries.py
    claim_queries.py
    link_queries.py
    branch_queries.py

  projection/
    __init__.py
    git_mirror.py

  integration/
    __init__.py
    bridge.py
    genesis_adapter.py
    pantheon_adapter.py
    research_adapter.py

tests/test_forgebase/
  __init__.py
  conftest.py
  test_domain/
    __init__.py
    test_values.py
    test_enums.py
    test_models.py
    test_event_types.py
    test_merge.py
    test_conflicts.py
  test_store/
    __init__.py
    conftest.py
    test_sqlite_vault_repo.py
    test_sqlite_source_repo.py
    test_sqlite_page_repo.py
    test_sqlite_claim_repo.py
    test_sqlite_link_repo.py
    test_sqlite_workbook_repo.py
    test_sqlite_job_repo.py
    test_sqlite_event_repo.py
    test_sqlite_uow.py
    test_local_fs_content.py
  test_service/
    __init__.py
    test_vault_service.py
    test_ingest_service.py
    test_page_service.py
    test_claim_service.py
    test_link_service.py
    test_branch_service.py
    test_merge_service.py
    test_job_service.py
    test_run_integration_service.py
  test_query/
    __init__.py
    test_page_queries.py
    test_claim_queries.py
    test_branch_queries.py
  test_events/
    __init__.py
    test_dispatcher.py
    test_consumers.py
  test_integration/
    __init__.py
    test_bridge.py
  test_e2e/
    __init__.py
    test_full_lifecycle.py
```

---

### Task 1: Domain Value Objects and Enums

**Files:**
- Create: `src/hephaestus/forgebase/__init__.py`
- Create: `src/hephaestus/forgebase/domain/__init__.py`
- Create: `src/hephaestus/forgebase/domain/values.py`
- Create: `src/hephaestus/forgebase/domain/enums.py`
- Test: `tests/test_forgebase/__init__.py`
- Test: `tests/test_forgebase/test_domain/__init__.py`
- Test: `tests/test_forgebase/test_domain/test_values.py`
- Test: `tests/test_forgebase/test_domain/test_enums.py`

- [ ] **Step 1: Write failing tests for EntityId**

```python
# tests/test_forgebase/test_domain/test_values.py
"""Tests for ForgeBase domain value objects."""
from __future__ import annotations

import pytest

from hephaestus.forgebase.domain.values import (
    ActorRef,
    BlobRef,
    ContentHash,
    EntityId,
    PendingContentRef,
    VaultRevisionId,
    Version,
)
from hephaestus.forgebase.domain.enums import ActorType


class TestEntityId:
    def test_create_with_prefix(self):
        eid = EntityId("vault_01HXYZ1234567890ABCDEF")
        assert eid.prefix == "vault"
        assert len(eid.ulid_part) == 26
        assert str(eid) == "vault_01HXYZ1234567890ABCDEF"

    def test_reject_no_prefix(self):
        with pytest.raises(ValueError, match="prefix"):
            EntityId("01HXYZ1234567890ABCDEF")

    def test_reject_empty(self):
        with pytest.raises(ValueError):
            EntityId("")

    def test_equality(self):
        a = EntityId("page_01HXYZ1234567890ABCDEF")
        b = EntityId("page_01HXYZ1234567890ABCDEF")
        assert a == b
        assert hash(a) == hash(b)

    def test_inequality_different_prefix(self):
        a = EntityId("page_01HXYZ1234567890ABCDEF")
        b = EntityId("claim_01HXYZ1234567890ABCDEF")
        assert a != b


class TestVersion:
    def test_create_positive(self):
        v = Version(1)
        assert v.number == 1

    def test_reject_zero(self):
        with pytest.raises(ValueError):
            Version(0)

    def test_reject_negative(self):
        with pytest.raises(ValueError):
            Version(-1)

    def test_ordering(self):
        assert Version(1) < Version(2)
        assert Version(3) > Version(1)

    def test_next(self):
        v = Version(1)
        assert v.next() == Version(2)


class TestVaultRevisionId:
    def test_create(self):
        rid = VaultRevisionId("rev_01HXYZ1234567890ABCDEF")
        assert rid.prefix == "rev"


class TestContentHash:
    def test_from_bytes(self):
        ch = ContentHash.from_bytes(b"hello world")
        assert len(ch.sha256) == 64
        assert ch.sha256.startswith("b94d27b9")

    def test_equality(self):
        a = ContentHash.from_bytes(b"hello")
        b = ContentHash.from_bytes(b"hello")
        assert a == b


class TestBlobRef:
    def test_create(self):
        ref = BlobRef(
            content_hash=ContentHash(sha256="abc123"),
            size_bytes=1024,
            mime_type="text/markdown",
        )
        assert ref.size_bytes == 1024
        assert ref.mime_type == "text/markdown"


class TestActorRef:
    def test_create(self):
        actor = ActorRef(actor_type=ActorType.USER, actor_id="user-123")
        assert actor.actor_type == ActorType.USER
        assert actor.actor_id == "user-123"

    def test_system_actor(self):
        actor = ActorRef.system()
        assert actor.actor_type == ActorType.SYSTEM
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_forgebase/test_domain/test_values.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Create package init files**

```python
# src/hephaestus/forgebase/__init__.py
"""ForgeBase — persistent knowledge foundry for Hephaestus."""
from __future__ import annotations

# src/hephaestus/forgebase/domain/__init__.py
"""ForgeBase domain layer — pure models, zero I/O."""
from __future__ import annotations

# tests/test_forgebase/__init__.py
# tests/test_forgebase/test_domain/__init__.py
```

- [ ] **Step 4: Implement enums**

```python
# src/hephaestus/forgebase/domain/enums.py
"""ForgeBase domain enumerations."""
from __future__ import annotations

from enum import Enum


class PageType(str, Enum):
    CONCEPT = "concept"
    PROBLEM = "problem"
    MECHANISM = "mechanism"
    COMPARISON = "comparison"
    TIMELINE = "timeline"
    OPEN_QUESTION = "open_question"
    EXPERIMENT = "experiment"
    INVENTION = "invention"
    SOURCE_INDEX = "source_index"
    SOURCE_CARD = "source_card"


class ClaimStatus(str, Enum):
    SUPPORTED = "supported"
    INFERRED = "inferred"
    HYPOTHESIS = "hypothesis"
    CONTESTED = "contested"
    STALE = "stale"


class SupportType(str, Enum):
    DIRECT = "direct"
    SYNTHESIZED = "synthesized"
    GENERATED = "generated"
    INHERITED = "inherited"


class LinkKind(str, Enum):
    BACKLINK = "backlink"
    RELATED_CONCEPT = "related_concept"
    PAGE_TO_PAGE = "page_to_page"
    SUPERSEDES = "supersedes"


class SourceFormat(str, Enum):
    PDF = "pdf"
    URL = "url"
    MARKDOWN = "markdown"
    GITHUB_REPO = "github_repo"
    CSV = "csv"
    JSON = "json"
    SLIDE_DECK = "slide_deck"
    IMAGE = "image"
    TRANSCRIPT = "transcript"
    HEPH_OUTPUT = "heph_output"


class SourceTrustTier(str, Enum):
    AUTHORITATIVE = "authoritative"
    STANDARD = "standard"
    LOW = "low"
    UNTRUSTED = "untrusted"


class SourceStatus(str, Enum):
    INGESTED = "ingested"
    NORMALIZED = "normalized"
    FAILED = "failed"


class WorkbookStatus(str, Enum):
    OPEN = "open"
    MERGED = "merged"
    ABANDONED = "abandoned"
    CONFLICTED = "conflicted"


class BranchPurpose(str, Enum):
    RESEARCH = "research"
    LINT_REPAIR = "lint_repair"
    INVENTION = "invention"
    COMPILATION = "compilation"
    MANUAL = "manual"


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobKind(str, Enum):
    COMPILE = "compile"
    LINT = "lint"
    NORMALIZE = "normalize"
    REINDEX = "reindex"
    MERGE_FOLLOWUP = "merge_followup"


class FindingSeverity(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class FindingCategory(str, Enum):
    DUPLICATE_PAGE = "duplicate_page"
    WEAK_BACKLINK = "weak_backlink"
    UNSUPPORTED_CLAIM = "unsupported_claim"
    CONTRADICTORY_CLAIM = "contradictory_claim"
    STALE_PAGE = "stale_page"
    ORPHANED_PAGE = "orphaned_page"
    MISSING_CANONICAL = "missing_canonical"
    UNRESOLVED_TODO = "unresolved_todo"
    SOURCE_GAP = "source_gap"
    MISSING_FIGURE_EXPLANATION = "missing_figure_explanation"
    RESOLVABLE_BY_SEARCH = "resolvable_by_search"


class FindingStatus(str, Enum):
    OPEN = "open"
    RESOLVED = "resolved"
    WAIVED = "waived"
    DEFERRED = "deferred"


class MergeVerdict(str, Enum):
    CLEAN = "clean"
    CONFLICTED = "conflicted"
    REQUIRES_REVIEW = "requires_review"


class MergeResolution(str, Enum):
    ACCEPT_BRANCH = "accept_branch"
    ACCEPT_CANONICAL = "accept_canonical"
    MANUAL = "manual"


class EntityKind(str, Enum):
    PAGE = "page"
    CLAIM = "claim"
    LINK = "link"
    SOURCE = "source"


class ActorType(str, Enum):
    SYSTEM = "system"
    USER = "user"
    AGENT = "agent"
    RUN = "run"
```

- [ ] **Step 5: Implement value objects**

```python
# src/hephaestus/forgebase/domain/values.py
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
            raise ValueError(
                f"EntityId must match '{{prefix}}_{{ulid}}', got: {self._raw!r}"
            )

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
```

- [ ] **Step 6: Write enum tests**

```python
# tests/test_forgebase/test_domain/test_enums.py
"""Tests for ForgeBase enumerations."""
from __future__ import annotations

from hephaestus.forgebase.domain.enums import (
    ActorType,
    ClaimStatus,
    EntityKind,
    FindingCategory,
    FindingSeverity,
    FindingStatus,
    JobKind,
    JobStatus,
    LinkKind,
    MergeResolution,
    MergeVerdict,
    PageType,
    SourceFormat,
    SourceStatus,
    SourceTrustTier,
    SupportType,
    WorkbookStatus,
)


def test_all_enums_are_string_valued():
    """Every enum must be usable as a plain string for DB storage."""
    for enum_cls in [
        PageType, ClaimStatus, SupportType, LinkKind, SourceFormat,
        SourceTrustTier, SourceStatus, WorkbookStatus, JobStatus, JobKind,
        FindingSeverity, FindingCategory, FindingStatus, MergeVerdict,
        MergeResolution, EntityKind, ActorType,
    ]:
        for member in enum_cls:
            assert isinstance(member.value, str)
            assert member == member.value


def test_page_type_has_source_card():
    assert PageType.SOURCE_CARD == "source_card"


def test_claim_status_values():
    assert set(ClaimStatus) == {
        ClaimStatus.SUPPORTED, ClaimStatus.INFERRED,
        ClaimStatus.HYPOTHESIS, ClaimStatus.CONTESTED, ClaimStatus.STALE,
    }
```

- [ ] **Step 7: Run all tests to verify they pass**

Run: `python -m pytest tests/test_forgebase/test_domain/ -v`
Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add src/hephaestus/forgebase/__init__.py src/hephaestus/forgebase/domain/ tests/test_forgebase/
git commit -m "feat(forgebase): add domain value objects and enumerations"
```

---

### Task 2: Domain Models — All Entities

**Files:**
- Create: `src/hephaestus/forgebase/domain/models.py`
- Test: `tests/test_forgebase/test_domain/test_models.py`

- [ ] **Step 1: Write failing tests for core models**

```python
# tests/test_forgebase/test_domain/test_models.py
"""Tests for ForgeBase domain models."""
from __future__ import annotations

from datetime import UTC, datetime

from hephaestus.forgebase.domain.enums import (
    ActorType,
    BranchPurpose,
    ClaimStatus,
    EntityKind,
    FindingCategory,
    FindingSeverity,
    FindingStatus,
    JobKind,
    JobStatus,
    LinkKind,
    MergeResolution,
    MergeVerdict,
    PageType,
    SourceFormat,
    SourceStatus,
    SourceTrustTier,
    SupportType,
    WorkbookStatus,
)
from hephaestus.forgebase.domain.models import (
    BranchClaimDerivationHead,
    BranchClaimHead,
    BranchClaimSupportHead,
    BranchLinkHead,
    BranchPageHead,
    BranchSourceHead,
    BranchTombstone,
    Claim,
    ClaimDerivation,
    ClaimSupport,
    ClaimVersion,
    DomainEvent,
    EventDelivery,
    Job,
    KnowledgeRunArtifact,
    KnowledgeRunRef,
    Link,
    LinkVersion,
    LintFinding,
    MergeConflict,
    MergeProposal,
    Page,
    PageVersion,
    Source,
    SourceVersion,
    Vault,
    VaultRevision,
    Workbook,
)
from hephaestus.forgebase.domain.values import (
    ActorRef,
    BlobRef,
    ContentHash,
    EntityId,
    VaultRevisionId,
    Version,
)


def _eid(prefix: str, suffix: str = "01HXYZ1234567890ABCDEF") -> EntityId:
    return EntityId(f"{prefix}_{suffix}")


def _rev(suffix: str = "01HXYZ1234567890ABCDEF") -> VaultRevisionId:
    return VaultRevisionId(f"rev_{suffix}")


def _actor() -> ActorRef:
    return ActorRef(actor_type=ActorType.SYSTEM, actor_id="test")


def _now() -> datetime:
    return datetime(2026, 4, 3, tzinfo=UTC)


def _blob() -> BlobRef:
    return BlobRef(content_hash=ContentHash(sha256="a" * 64), size_bytes=100, mime_type="text/plain")


class TestVault:
    def test_create(self):
        v = Vault(
            vault_id=_eid("vault"),
            name="test-vault",
            description="A test vault",
            head_revision_id=_rev(),
            created_at=_now(),
            updated_at=_now(),
            config={},
        )
        assert v.name == "test-vault"
        assert v.vault_id.prefix == "vault"


class TestSourceVersion:
    def test_create(self):
        sv = SourceVersion(
            source_id=_eid("source"),
            version=Version(1),
            title="Test Paper",
            authors=["Author A"],
            url="https://example.com",
            raw_artifact_ref=_blob(),
            normalized_ref=None,
            content_hash=ContentHash(sha256="b" * 64),
            metadata={},
            trust_tier=SourceTrustTier.STANDARD,
            status=SourceStatus.INGESTED,
            created_at=_now(),
            created_by=_actor(),
        )
        assert sv.version == Version(1)
        assert sv.trust_tier == SourceTrustTier.STANDARD


class TestPageVersion:
    def test_create(self):
        pv = PageVersion(
            page_id=_eid("page"),
            version=Version(1),
            title="Concept: Pheromone Routing",
            content_ref=_blob(),
            content_hash=ContentHash(sha256="c" * 64),
            summary="Initial version",
            compiled_from=[_eid("source")],
            created_at=_now(),
            created_by=_actor(),
            schema_version=1,
        )
        assert pv.title == "Concept: Pheromone Routing"


class TestClaimVersion:
    def test_create(self):
        cv = ClaimVersion(
            claim_id=_eid("claim"),
            version=Version(1),
            statement="Pheromone decay enables load redistribution",
            status=ClaimStatus.SUPPORTED,
            support_type=SupportType.DIRECT,
            confidence=0.85,
            validated_at=_now(),
            fresh_until=None,
            created_at=_now(),
            created_by=_actor(),
        )
        assert cv.confidence == 0.85


class TestClaimSupport:
    def test_create(self):
        cs = ClaimSupport(
            support_id=_eid("csup"),
            claim_id=_eid("claim"),
            source_id=_eid("source"),
            source_segment="Section 3.2",
            strength=0.9,
            created_at=_now(),
            created_by=_actor(),
        )
        assert cs.strength == 0.9


class TestWorkbook:
    def test_create(self):
        wb = Workbook(
            workbook_id=_eid("wb"),
            vault_id=_eid("vault"),
            name="research-branch",
            purpose=BranchPurpose.RESEARCH,
            status=WorkbookStatus.OPEN,
            base_revision_id=_rev(),
            created_at=_now(),
            created_by=_actor(),
            created_by_run=None,
        )
        assert wb.status == WorkbookStatus.OPEN


class TestBranchPageHead:
    def test_create(self):
        bph = BranchPageHead(
            workbook_id=_eid("wb"),
            page_id=_eid("page"),
            head_version=Version(2),
            base_version=Version(1),
        )
        assert bph.head_version > bph.base_version


class TestBranchTombstone:
    def test_create(self):
        bt = BranchTombstone(
            workbook_id=_eid("wb"),
            entity_kind=EntityKind.PAGE,
            entity_id=_eid("page"),
            tombstoned_at=_now(),
        )
        assert bt.entity_kind == EntityKind.PAGE


class TestMergeProposal:
    def test_create_clean(self):
        mp = MergeProposal(
            merge_id=_eid("merge"),
            workbook_id=_eid("wb"),
            vault_id=_eid("vault"),
            base_revision_id=_rev("01HXYZ0000000000000001"),
            target_revision_id=_rev("01HXYZ0000000000000001"),
            verdict=MergeVerdict.CLEAN,
            resulting_revision=None,
            proposed_at=_now(),
            resolved_at=None,
            proposed_by=_actor(),
        )
        assert mp.verdict == MergeVerdict.CLEAN


class TestJob:
    def test_create(self):
        j = Job(
            job_id=_eid("job"),
            vault_id=_eid("vault"),
            workbook_id=None,
            kind=JobKind.COMPILE,
            status=JobStatus.PENDING,
            config={},
            idempotency_key="compile:vault_01:rev_01",
            priority=0,
            attempt_count=0,
            max_attempts=3,
            next_attempt_at=None,
            leased_until=None,
            heartbeat_at=None,
            started_at=None,
            completed_at=None,
            error=None,
            created_by=_actor(),
            created_by_run=None,
        )
        assert j.status == JobStatus.PENDING
        assert j.attempt_count == 0


class TestDomainEvent:
    def test_create(self):
        ev = DomainEvent(
            event_id=_eid("evt"),
            event_type="source.ingested",
            schema_version=1,
            aggregate_type="source",
            aggregate_id=_eid("source"),
            aggregate_version=Version(1),
            vault_id=_eid("vault"),
            workbook_id=None,
            run_id=None,
            causation_id=None,
            correlation_id=None,
            actor_type=ActorType.SYSTEM,
            actor_id="system",
            occurred_at=_now(),
            payload={"source_id": "source_01HXYZ1234567890ABCDEF"},
        )
        assert ev.event_type == "source.ingested"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_forgebase/test_domain/test_models.py -v`
Expected: FAIL — models module not found

- [ ] **Step 3: Implement all domain models**

```python
# src/hephaestus/forgebase/domain/models.py
"""ForgeBase domain models — all core entities."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from hephaestus.forgebase.domain.enums import (
    ActorType,
    BranchPurpose,
    ClaimStatus,
    EntityKind,
    FindingCategory,
    FindingSeverity,
    FindingStatus,
    JobKind,
    JobStatus,
    LinkKind,
    MergeResolution,
    MergeVerdict,
    PageType,
    SourceFormat,
    SourceStatus,
    SourceTrustTier,
    SupportType,
    WorkbookStatus,
)
from hephaestus.forgebase.domain.values import (
    ActorRef,
    BlobRef,
    ContentHash,
    EntityId,
    VaultRevisionId,
    Version,
)


# ---------------------------------------------------------------------------
# Vault
# ---------------------------------------------------------------------------

@dataclass
class Vault:
    vault_id: EntityId
    name: str
    description: str
    head_revision_id: VaultRevisionId
    created_at: datetime
    updated_at: datetime
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class VaultRevision:
    revision_id: VaultRevisionId
    vault_id: EntityId
    parent_revision_id: VaultRevisionId | None
    created_at: datetime
    created_by: ActorRef
    causation_event_id: EntityId | None
    summary: str


# ---------------------------------------------------------------------------
# Source
# ---------------------------------------------------------------------------

@dataclass
class Source:
    source_id: EntityId
    vault_id: EntityId
    format: SourceFormat
    origin_locator: str | None
    created_at: datetime


@dataclass
class SourceVersion:
    source_id: EntityId
    version: Version
    title: str
    authors: list[str]
    url: str | None
    raw_artifact_ref: BlobRef
    normalized_ref: BlobRef | None
    content_hash: ContentHash
    metadata: dict[str, Any]
    trust_tier: SourceTrustTier
    status: SourceStatus
    created_at: datetime
    created_by: ActorRef


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

@dataclass
class Page:
    page_id: EntityId
    vault_id: EntityId
    page_type: PageType
    page_key: str
    created_at: datetime
    created_by_run: EntityId | None = None


@dataclass
class PageVersion:
    page_id: EntityId
    version: Version
    title: str
    content_ref: BlobRef
    content_hash: ContentHash
    summary: str
    compiled_from: list[EntityId]
    created_at: datetime
    created_by: ActorRef
    schema_version: int = 1


# ---------------------------------------------------------------------------
# Claim
# ---------------------------------------------------------------------------

@dataclass
class Claim:
    claim_id: EntityId
    vault_id: EntityId
    page_id: EntityId
    created_at: datetime


@dataclass
class ClaimVersion:
    claim_id: EntityId
    version: Version
    statement: str
    status: ClaimStatus
    support_type: SupportType
    confidence: float
    validated_at: datetime
    fresh_until: datetime | None
    created_at: datetime
    created_by: ActorRef


@dataclass
class ClaimSupport:
    support_id: EntityId
    claim_id: EntityId
    source_id: EntityId
    source_segment: str | None
    strength: float
    created_at: datetime
    created_by: ActorRef


@dataclass
class ClaimDerivation:
    derivation_id: EntityId
    claim_id: EntityId
    parent_claim_id: EntityId
    relationship: str
    created_at: datetime
    created_by: ActorRef


# ---------------------------------------------------------------------------
# Link
# ---------------------------------------------------------------------------

@dataclass
class Link:
    link_id: EntityId
    vault_id: EntityId
    kind: LinkKind
    created_at: datetime


@dataclass
class LinkVersion:
    link_id: EntityId
    version: Version
    source_entity: EntityId
    target_entity: EntityId
    label: str | None
    weight: float
    created_at: datetime
    created_by: ActorRef


# ---------------------------------------------------------------------------
# Workbook (= Branch)
# ---------------------------------------------------------------------------

@dataclass
class Workbook:
    workbook_id: EntityId
    vault_id: EntityId
    name: str
    purpose: BranchPurpose
    status: WorkbookStatus
    base_revision_id: VaultRevisionId
    created_at: datetime
    created_by: ActorRef
    created_by_run: EntityId | None = None


# ---------------------------------------------------------------------------
# Branch heads and tombstones
# ---------------------------------------------------------------------------

@dataclass
class BranchPageHead:
    workbook_id: EntityId
    page_id: EntityId
    head_version: Version
    base_version: Version


@dataclass
class BranchClaimHead:
    workbook_id: EntityId
    claim_id: EntityId
    head_version: Version
    base_version: Version


@dataclass
class BranchLinkHead:
    workbook_id: EntityId
    link_id: EntityId
    head_version: Version
    base_version: Version


@dataclass
class BranchSourceHead:
    workbook_id: EntityId
    source_id: EntityId
    head_version: Version
    base_version: Version


@dataclass
class BranchClaimSupportHead:
    workbook_id: EntityId
    support_id: EntityId
    created_on_branch: bool


@dataclass
class BranchClaimDerivationHead:
    workbook_id: EntityId
    derivation_id: EntityId
    created_on_branch: bool


@dataclass
class BranchTombstone:
    workbook_id: EntityId
    entity_kind: EntityKind
    entity_id: EntityId
    tombstoned_at: datetime


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------

@dataclass
class MergeProposal:
    merge_id: EntityId
    workbook_id: EntityId
    vault_id: EntityId
    base_revision_id: VaultRevisionId
    target_revision_id: VaultRevisionId
    verdict: MergeVerdict
    resulting_revision: VaultRevisionId | None
    proposed_at: datetime
    resolved_at: datetime | None
    proposed_by: ActorRef


@dataclass
class MergeConflict:
    conflict_id: EntityId
    merge_id: EntityId
    entity_kind: EntityKind
    entity_id: EntityId
    base_version: Version
    branch_version: Version
    canonical_version: Version
    resolution: MergeResolution | None = None
    resolved_at: datetime | None = None


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

@dataclass
class Job:
    job_id: EntityId
    vault_id: EntityId
    workbook_id: EntityId | None
    kind: JobKind
    status: JobStatus
    config: dict[str, Any]
    idempotency_key: str
    priority: int
    attempt_count: int
    max_attempts: int
    next_attempt_at: datetime | None
    leased_until: datetime | None
    heartbeat_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    error: str | None
    created_by: ActorRef
    created_by_run: EntityId | None = None


@dataclass
class LintFinding:
    finding_id: EntityId
    job_id: EntityId
    vault_id: EntityId
    category: FindingCategory
    severity: FindingSeverity
    page_id: EntityId | None
    claim_id: EntityId | None
    description: str
    suggested_action: str | None
    status: FindingStatus
    resolved_at: datetime | None = None


# ---------------------------------------------------------------------------
# Run integration
# ---------------------------------------------------------------------------

@dataclass
class KnowledgeRunRef:
    ref_id: EntityId
    vault_id: EntityId
    run_id: str
    run_type: str
    upstream_system: str
    upstream_ref: str | None
    source_hash: str | None
    sync_status: str
    sync_error: str | None
    synced_at: datetime | None
    created_at: datetime


@dataclass
class KnowledgeRunArtifact:
    ref_id: EntityId
    entity_kind: EntityKind
    entity_id: EntityId
    role: str


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

@dataclass
class DomainEvent:
    event_id: EntityId
    event_type: str
    schema_version: int
    aggregate_type: str
    aggregate_id: EntityId
    aggregate_version: Version | None
    vault_id: EntityId
    workbook_id: EntityId | None
    run_id: str | None
    causation_id: EntityId | None
    correlation_id: str | None
    actor_type: ActorType
    actor_id: str
    occurred_at: datetime
    payload: dict[str, Any]


@dataclass
class EventDelivery:
    event_id: EntityId
    consumer_name: str
    status: str
    attempt_count: int
    next_attempt_at: datetime | None
    lease_owner: str | None
    lease_expires_at: datetime | None
    last_error: str | None
    delivered_at: datetime | None
```

- [ ] **Step 4: Run all domain tests**

Run: `python -m pytest tests/test_forgebase/test_domain/ -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/hephaestus/forgebase/domain/models.py tests/test_forgebase/test_domain/test_models.py
git commit -m "feat(forgebase): add all domain entity models"
```

---

### Task 3: Domain Event Types and EventFactory

**Files:**
- Create: `src/hephaestus/forgebase/domain/event_types.py`
- Create: `src/hephaestus/forgebase/service/__init__.py`
- Create: `src/hephaestus/forgebase/service/id_generator.py`
- Test: `tests/test_forgebase/test_domain/test_event_types.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_forgebase/test_domain/test_event_types.py
"""Tests for domain event types, EventFactory, Clock, and IdGenerator."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from hephaestus.forgebase.domain.enums import ActorType
from hephaestus.forgebase.domain.event_types import (
    EVENT_TAXONOMY,
    Clock,
    EventFactory,
    FixedClock,
)
from hephaestus.forgebase.domain.values import ActorRef, EntityId, Version
from hephaestus.forgebase.service.id_generator import IdGenerator, DeterministicIdGenerator


class TestEventTaxonomy:
    def test_source_events_exist(self):
        assert "source.ingested" in EVENT_TAXONOMY
        assert "source.normalized" in EVENT_TAXONOMY

    def test_page_events_exist(self):
        assert "page.version_created" in EVENT_TAXONOMY

    def test_claim_events_exist(self):
        assert "claim.support_added" in EVENT_TAXONOMY
        assert "claim.invalidated" in EVENT_TAXONOMY

    def test_workbook_events_exist(self):
        assert "workbook.created" in EVENT_TAXONOMY
        assert "workbook.merged" in EVENT_TAXONOMY

    def test_lint_events_exist(self):
        assert "lint.finding_opened" in EVENT_TAXONOMY

    def test_integration_events_exist(self):
        assert "artifact.attached" in EVENT_TAXONOMY
        assert "invention.output_committed" in EVENT_TAXONOMY


class TestFixedClock:
    def test_returns_fixed_time(self):
        t = datetime(2026, 1, 1, tzinfo=UTC)
        clock = FixedClock(t)
        assert clock.now() == t
        assert clock.now() == t

    def test_tick_advances(self):
        t = datetime(2026, 1, 1, tzinfo=UTC)
        clock = FixedClock(t)
        clock.tick()
        assert clock.now() > t


class TestDeterministicIdGenerator:
    def test_produces_valid_entity_ids(self):
        gen = DeterministicIdGenerator()
        eid = gen.generate("vault")
        assert eid.prefix == "vault"

    def test_sequential_ids_are_unique(self):
        gen = DeterministicIdGenerator()
        a = gen.generate("page")
        b = gen.generate("page")
        assert a != b

    def test_shortcut_methods(self):
        gen = DeterministicIdGenerator()
        assert gen.vault_id().prefix == "vault"
        assert gen.page_id().prefix == "page"
        assert gen.source_id().prefix == "source"
        assert gen.claim_id().prefix == "claim"
        assert gen.event_id().prefix == "evt"
        assert gen.revision_id().prefix == "rev"


class TestEventFactory:
    def test_creates_event_with_consistent_fields(self):
        t = datetime(2026, 4, 3, tzinfo=UTC)
        clock = FixedClock(t)
        gen = DeterministicIdGenerator()
        factory = EventFactory(clock=clock, id_generator=gen, default_schema_version=1)

        vault_id = gen.vault_id()
        source_id = gen.source_id()
        actor = ActorRef.system()

        event = factory.create(
            event_type="source.ingested",
            aggregate_type="source",
            aggregate_id=source_id,
            vault_id=vault_id,
            payload={"source_id": str(source_id)},
            actor=actor,
            aggregate_version=Version(1),
        )

        assert event.event_type == "source.ingested"
        assert event.occurred_at == t
        assert event.schema_version == 1
        assert event.aggregate_id == source_id
        assert event.vault_id == vault_id
        assert event.actor_type == ActorType.SYSTEM
        assert event.event_id.prefix == "evt"

    def test_rejects_unknown_event_type(self):
        clock = FixedClock(datetime(2026, 1, 1, tzinfo=UTC))
        gen = DeterministicIdGenerator()
        factory = EventFactory(clock=clock, id_generator=gen, default_schema_version=1)

        with pytest.raises(ValueError, match="Unknown event type"):
            factory.create(
                event_type="bogus.event",
                aggregate_type="x",
                aggregate_id=gen.vault_id(),
                vault_id=gen.vault_id(),
                payload={},
                actor=ActorRef.system(),
            )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_forgebase/test_domain/test_event_types.py -v`
Expected: FAIL — modules not found

- [ ] **Step 3: Implement IdGenerator**

```python
# src/hephaestus/forgebase/service/__init__.py
"""ForgeBase service layer — command-oriented business logic."""
from __future__ import annotations

# src/hephaestus/forgebase/service/id_generator.py
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
```

- [ ] **Step 4: Implement event_types.py with EventFactory and Clock**

```python
# src/hephaestus/forgebase/domain/event_types.py
"""Domain event schemas, taxonomy, EventFactory, and Clock."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from hephaestus.forgebase.domain.models import DomainEvent
from hephaestus.forgebase.domain.values import ActorRef, EntityId, Version

# Complete event taxonomy — every valid event_type
EVENT_TAXONOMY: frozenset[str] = frozenset({
    # Source lifecycle
    "source.ingested",
    "source.normalization_requested",
    "source.normalized",
    "source.ingest_failed",
    # Compilation lifecycle
    "compile.requested",
    "page.version_created",
    "page.deleted",
    "claim.version_created",
    "link.version_created",
    "link.deleted",
    "compile.completed",
    "compile.failed",
    # Provenance lifecycle
    "claim.support_added",
    "claim.support_removed",
    "claim.status_changed",
    "claim.invalidated",
    "claim.freshness_changed",
    "claim.derivation_added",
    # Workbook lifecycle
    "workbook.created",
    "workbook.updated",
    "merge.proposed",
    "merge.conflict_detected",
    "workbook.merged",
    "workbook.abandoned",
    # Lint lifecycle
    "lint.requested",
    "lint.finding_opened",
    "lint.finding_resolved",
    "lint.completed",
    # Run / integration lifecycle
    "artifact.attached",
    "research.output_committed",
    "invention.output_committed",
    "pantheon.verdict_recorded",
    # Vault lifecycle
    "vault.created",
    "vault.config_updated",
})


class Clock(ABC):
    """Injectable time provider."""

    @abstractmethod
    def now(self) -> datetime: ...


class WallClock(Clock):
    """Production clock — real UTC time."""

    def now(self) -> datetime:
        return datetime.now(UTC)


@dataclass
class FixedClock(Clock):
    """Test clock — returns a fixed or manually advanced time."""

    _time: datetime

    def now(self) -> datetime:
        return self._time

    def tick(self, seconds: float = 1.0) -> None:
        self._time = self._time + timedelta(seconds=seconds)

    def set(self, t: datetime) -> None:
        self._time = t


class EventFactory:
    """Centralized event construction with consistent metadata."""

    def __init__(
        self,
        clock: Clock,
        id_generator: object,  # IdGenerator — imported at usage to avoid circular
        default_schema_version: int = 1,
    ) -> None:
        self._clock = clock
        self._id_gen = id_generator
        self._default_schema_version = default_schema_version

    def create(
        self,
        *,
        event_type: str,
        aggregate_type: str,
        aggregate_id: EntityId,
        vault_id: EntityId,
        payload: dict,
        actor: ActorRef,
        aggregate_version: Version | None = None,
        workbook_id: EntityId | None = None,
        run_id: str | None = None,
        causation_id: EntityId | None = None,
        correlation_id: str | None = None,
        schema_version: int | None = None,
    ) -> DomainEvent:
        if event_type not in EVENT_TAXONOMY:
            raise ValueError(f"Unknown event type: {event_type!r}")

        return DomainEvent(
            event_id=self._id_gen.event_id(),  # type: ignore[attr-defined]
            event_type=event_type,
            schema_version=schema_version or self._default_schema_version,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            aggregate_version=aggregate_version,
            vault_id=vault_id,
            workbook_id=workbook_id,
            run_id=run_id,
            causation_id=causation_id,
            correlation_id=correlation_id,
            actor_type=actor.actor_type,
            actor_id=actor.actor_id,
            occurred_at=self._clock.now(),
            payload=payload,
        )
```

- [ ] **Step 5: Run all tests**

Run: `python -m pytest tests/test_forgebase/test_domain/ -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/hephaestus/forgebase/domain/event_types.py src/hephaestus/forgebase/service/ tests/test_forgebase/test_domain/test_event_types.py
git commit -m "feat(forgebase): add event taxonomy, EventFactory, Clock, and IdGenerator"
```

---

### Task 4: Domain Merge and Conflict Logic

**Files:**
- Create: `src/hephaestus/forgebase/domain/merge.py`
- Create: `src/hephaestus/forgebase/domain/conflicts.py`
- Test: `tests/test_forgebase/test_domain/test_merge.py`
- Test: `tests/test_forgebase/test_domain/test_conflicts.py`

- [ ] **Step 1: Write failing tests for conflict detection**

```python
# tests/test_forgebase/test_domain/test_conflicts.py
"""Tests for conflict detection predicates."""
from __future__ import annotations

from hephaestus.forgebase.domain.conflicts import (
    detect_entity_conflict,
    ConflictCheckResult,
)
from hephaestus.forgebase.domain.values import Version


class TestDetectEntityConflict:
    def test_clean_when_canonical_unchanged(self):
        result = detect_entity_conflict(
            base_version=Version(1),
            branch_version=Version(2),
            canonical_version=Version(1),
        )
        assert result == ConflictCheckResult.CLEAN

    def test_conflict_when_both_changed(self):
        result = detect_entity_conflict(
            base_version=Version(1),
            branch_version=Version(2),
            canonical_version=Version(3),
        )
        assert result == ConflictCheckResult.CONFLICTED

    def test_clean_when_only_canonical_changed_and_branch_untouched(self):
        """Branch didn't touch the entity — no branch head exists."""
        result = detect_entity_conflict(
            base_version=Version(1),
            branch_version=None,
            canonical_version=Version(2),
        )
        assert result == ConflictCheckResult.NO_BRANCH_CHANGE

    def test_conflict_when_canonical_deleted_branch_modified(self):
        result = detect_entity_conflict(
            base_version=Version(1),
            branch_version=Version(2),
            canonical_version=None,  # canonical deleted/archived
        )
        assert result == ConflictCheckResult.CONFLICTED
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest tests/test_forgebase/test_domain/test_conflicts.py -v`
Expected: FAIL

- [ ] **Step 3: Implement conflicts.py**

```python
# src/hephaestus/forgebase/domain/conflicts.py
"""Conflict detection predicates for branch merge."""
from __future__ import annotations

from enum import Enum

from hephaestus.forgebase.domain.values import Version


class ConflictCheckResult(str, Enum):
    CLEAN = "clean"
    CONFLICTED = "conflicted"
    NO_BRANCH_CHANGE = "no_branch_change"


def detect_entity_conflict(
    *,
    base_version: Version,
    branch_version: Version | None,
    canonical_version: Version | None,
) -> ConflictCheckResult:
    """Determine if a single entity has a merge conflict.

    Args:
        base_version: The entity version when the branch was created.
        branch_version: The entity's current branch-local head, or None if untouched.
        canonical_version: The entity's current canonical head, or None if archived.

    Returns:
        CLEAN if merge can proceed without conflict.
        CONFLICTED if both branch and canonical diverged from base.
        NO_BRANCH_CHANGE if the branch never touched this entity.
    """
    if branch_version is None:
        return ConflictCheckResult.NO_BRANCH_CHANGE

    if canonical_version is None:
        # Canonical was archived but branch modified — conflict
        return ConflictCheckResult.CONFLICTED

    if canonical_version == base_version:
        # Canonical didn't change — branch wins cleanly
        return ConflictCheckResult.CLEAN

    # Both diverged
    return ConflictCheckResult.CONFLICTED
```

- [ ] **Step 4: Write failing tests for merge rules**

```python
# tests/test_forgebase/test_domain/test_merge.py
"""Tests for merge rules and version reconciliation."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from hephaestus.forgebase.domain.enums import EntityKind, MergeVerdict
from hephaestus.forgebase.domain.merge import (
    MergeAnalysis,
    MergeEntityChange,
    analyze_merge,
)
from hephaestus.forgebase.domain.values import EntityId, Version


def _eid(prefix: str, n: int = 1) -> EntityId:
    return EntityId(f"{prefix}_{n:026d}")


class TestAnalyzeMerge:
    def test_clean_merge_no_canonical_changes(self):
        changes = [
            MergeEntityChange(
                entity_kind=EntityKind.PAGE,
                entity_id=_eid("page"),
                base_version=Version(1),
                branch_version=Version(2),
                canonical_version=Version(1),
            ),
        ]
        result = analyze_merge(changes)
        assert result.verdict == MergeVerdict.CLEAN
        assert len(result.conflicts) == 0
        assert len(result.clean_changes) == 1

    def test_conflicted_merge(self):
        changes = [
            MergeEntityChange(
                entity_kind=EntityKind.PAGE,
                entity_id=_eid("page"),
                base_version=Version(1),
                branch_version=Version(2),
                canonical_version=Version(3),
            ),
        ]
        result = analyze_merge(changes)
        assert result.verdict == MergeVerdict.CONFLICTED
        assert len(result.conflicts) == 1
        assert len(result.clean_changes) == 0

    def test_mixed_clean_and_conflicted(self):
        changes = [
            MergeEntityChange(
                entity_kind=EntityKind.PAGE,
                entity_id=_eid("page", 1),
                base_version=Version(1),
                branch_version=Version(2),
                canonical_version=Version(1),
            ),
            MergeEntityChange(
                entity_kind=EntityKind.CLAIM,
                entity_id=_eid("claim", 2),
                base_version=Version(1),
                branch_version=Version(2),
                canonical_version=Version(4),
            ),
        ]
        result = analyze_merge(changes)
        assert result.verdict == MergeVerdict.CONFLICTED
        assert len(result.clean_changes) == 1
        assert len(result.conflicts) == 1
```

- [ ] **Step 5: Implement merge.py**

```python
# src/hephaestus/forgebase/domain/merge.py
"""Merge rules and version reconciliation logic."""
from __future__ import annotations

from dataclasses import dataclass, field

from hephaestus.forgebase.domain.conflicts import ConflictCheckResult, detect_entity_conflict
from hephaestus.forgebase.domain.enums import EntityKind, MergeVerdict
from hephaestus.forgebase.domain.values import EntityId, Version


@dataclass
class MergeEntityChange:
    """One entity's version state for merge analysis."""

    entity_kind: EntityKind
    entity_id: EntityId
    base_version: Version
    branch_version: Version | None  # None = branch didn't touch
    canonical_version: Version | None  # None = canonical archived


@dataclass
class MergeAnalysis:
    """Result of analyzing all branch changes against canonical."""

    verdict: MergeVerdict
    clean_changes: list[MergeEntityChange] = field(default_factory=list)
    conflicts: list[MergeEntityChange] = field(default_factory=list)
    skipped: list[MergeEntityChange] = field(default_factory=list)


def analyze_merge(changes: list[MergeEntityChange]) -> MergeAnalysis:
    """Analyze a set of branch changes against canonical versions.

    Returns a MergeAnalysis with the overall verdict and per-entity breakdown.
    """
    clean: list[MergeEntityChange] = []
    conflicts: list[MergeEntityChange] = []
    skipped: list[MergeEntityChange] = []

    for change in changes:
        result = detect_entity_conflict(
            base_version=change.base_version,
            branch_version=change.branch_version,
            canonical_version=change.canonical_version,
        )
        if result == ConflictCheckResult.CLEAN:
            clean.append(change)
        elif result == ConflictCheckResult.CONFLICTED:
            conflicts.append(change)
        else:
            skipped.append(change)

    verdict = MergeVerdict.CLEAN if not conflicts else MergeVerdict.CONFLICTED

    return MergeAnalysis(
        verdict=verdict,
        clean_changes=clean,
        conflicts=conflicts,
        skipped=skipped,
    )
```

- [ ] **Step 6: Run all domain tests**

Run: `python -m pytest tests/test_forgebase/test_domain/ -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add src/hephaestus/forgebase/domain/merge.py src/hephaestus/forgebase/domain/conflicts.py tests/test_forgebase/test_domain/test_merge.py tests/test_forgebase/test_domain/test_conflicts.py
git commit -m "feat(forgebase): add merge analysis and conflict detection logic"
```

---

### Task 5: Repository Contracts (ABCs)

**Files:**
- Create: `src/hephaestus/forgebase/repository/__init__.py`
- Create: `src/hephaestus/forgebase/repository/vault_repo.py`
- Create: `src/hephaestus/forgebase/repository/source_repo.py`
- Create: `src/hephaestus/forgebase/repository/page_repo.py`
- Create: `src/hephaestus/forgebase/repository/claim_repo.py`
- Create: `src/hephaestus/forgebase/repository/claim_support_repo.py`
- Create: `src/hephaestus/forgebase/repository/claim_derivation_repo.py`
- Create: `src/hephaestus/forgebase/repository/link_repo.py`
- Create: `src/hephaestus/forgebase/repository/workbook_repo.py`
- Create: `src/hephaestus/forgebase/repository/merge_proposal_repo.py`
- Create: `src/hephaestus/forgebase/repository/merge_conflict_repo.py`
- Create: `src/hephaestus/forgebase/repository/job_repo.py`
- Create: `src/hephaestus/forgebase/repository/finding_repo.py`
- Create: `src/hephaestus/forgebase/repository/run_ref_repo.py`
- Create: `src/hephaestus/forgebase/repository/run_artifact_repo.py`
- Create: `src/hephaestus/forgebase/repository/content_store.py`
- Create: `src/hephaestus/forgebase/repository/uow.py`

No tests for this task — these are ABCs. They get tested transitively via store implementations in Tasks 8-10.

- [ ] **Step 1: Create repository package and vault repo contract**

```python
# src/hephaestus/forgebase/repository/__init__.py
"""ForgeBase repository contracts — abstract interfaces only."""
from __future__ import annotations

# src/hephaestus/forgebase/repository/vault_repo.py
"""Vault repository contract."""
from __future__ import annotations

from abc import ABC, abstractmethod

from hephaestus.forgebase.domain.models import Vault, VaultRevision
from hephaestus.forgebase.domain.values import EntityId, VaultRevisionId


class VaultRepository(ABC):
    @abstractmethod
    async def create(self, vault: Vault, revision: VaultRevision) -> None: ...

    @abstractmethod
    async def get(self, vault_id: EntityId) -> Vault | None: ...

    @abstractmethod
    async def list_all(self) -> list[Vault]: ...

    @abstractmethod
    async def update_head(self, vault_id: EntityId, revision_id: VaultRevisionId) -> None: ...

    @abstractmethod
    async def update_config(self, vault_id: EntityId, config: dict) -> None: ...

    @abstractmethod
    async def get_revision(self, revision_id: VaultRevisionId) -> VaultRevision | None: ...

    @abstractmethod
    async def create_revision(self, revision: VaultRevision) -> None: ...

    @abstractmethod
    async def get_canonical_page_head(self, vault_id: EntityId, page_id: EntityId) -> int | None:
        """Return current canonical version number for a page, or None."""

    @abstractmethod
    async def set_canonical_page_head(self, vault_id: EntityId, page_id: EntityId, version: int) -> None: ...

    @abstractmethod
    async def get_canonical_claim_head(self, vault_id: EntityId, claim_id: EntityId) -> int | None: ...

    @abstractmethod
    async def set_canonical_claim_head(self, vault_id: EntityId, claim_id: EntityId, version: int) -> None: ...

    @abstractmethod
    async def get_canonical_link_head(self, vault_id: EntityId, link_id: EntityId) -> int | None: ...

    @abstractmethod
    async def set_canonical_link_head(self, vault_id: EntityId, link_id: EntityId, version: int) -> None: ...

    @abstractmethod
    async def get_canonical_source_head(self, vault_id: EntityId, source_id: EntityId) -> int | None: ...

    @abstractmethod
    async def set_canonical_source_head(self, vault_id: EntityId, source_id: EntityId, version: int) -> None: ...
```

- [ ] **Step 2: Create remaining entity repository contracts**

Each follows the same pattern: create, get by ID, get head version, create version, list. I'll show the key ones; the rest follow identical patterns.

```python
# src/hephaestus/forgebase/repository/page_repo.py
"""Page repository contract."""
from __future__ import annotations

from abc import ABC, abstractmethod

from hephaestus.forgebase.domain.models import Page, PageVersion
from hephaestus.forgebase.domain.values import EntityId, Version


class PageRepository(ABC):
    @abstractmethod
    async def create(self, page: Page, version: PageVersion) -> None: ...

    @abstractmethod
    async def get(self, page_id: EntityId) -> Page | None: ...

    @abstractmethod
    async def get_version(self, page_id: EntityId, version: Version) -> PageVersion | None: ...

    @abstractmethod
    async def get_head_version(self, page_id: EntityId) -> PageVersion | None:
        """Get the latest version for this page (canonical context)."""

    @abstractmethod
    async def create_version(self, version: PageVersion) -> None: ...

    @abstractmethod
    async def list_by_vault(self, vault_id: EntityId, *, page_type: str | None = None) -> list[Page]: ...

    @abstractmethod
    async def find_by_key(self, vault_id: EntityId, page_key: str) -> Page | None: ...
```

```python
# src/hephaestus/forgebase/repository/source_repo.py
"""Source repository contract."""
from __future__ import annotations

from abc import ABC, abstractmethod

from hephaestus.forgebase.domain.models import Source, SourceVersion
from hephaestus.forgebase.domain.values import EntityId, Version


class SourceRepository(ABC):
    @abstractmethod
    async def create(self, source: Source, version: SourceVersion) -> None: ...

    @abstractmethod
    async def get(self, source_id: EntityId) -> Source | None: ...

    @abstractmethod
    async def get_version(self, source_id: EntityId, version: Version) -> SourceVersion | None: ...

    @abstractmethod
    async def get_head_version(self, source_id: EntityId) -> SourceVersion | None: ...

    @abstractmethod
    async def create_version(self, version: SourceVersion) -> None: ...

    @abstractmethod
    async def list_by_vault(self, vault_id: EntityId) -> list[Source]: ...
```

```python
# src/hephaestus/forgebase/repository/claim_repo.py
"""Claim repository contract."""
from __future__ import annotations

from abc import ABC, abstractmethod

from hephaestus.forgebase.domain.models import Claim, ClaimVersion
from hephaestus.forgebase.domain.values import EntityId, Version


class ClaimRepository(ABC):
    @abstractmethod
    async def create(self, claim: Claim, version: ClaimVersion) -> None: ...

    @abstractmethod
    async def get(self, claim_id: EntityId) -> Claim | None: ...

    @abstractmethod
    async def get_version(self, claim_id: EntityId, version: Version) -> ClaimVersion | None: ...

    @abstractmethod
    async def get_head_version(self, claim_id: EntityId) -> ClaimVersion | None: ...

    @abstractmethod
    async def create_version(self, version: ClaimVersion) -> None: ...

    @abstractmethod
    async def list_by_page(self, page_id: EntityId) -> list[Claim]: ...
```

```python
# src/hephaestus/forgebase/repository/claim_support_repo.py
from __future__ import annotations
from abc import ABC, abstractmethod
from hephaestus.forgebase.domain.models import ClaimSupport
from hephaestus.forgebase.domain.values import EntityId

class ClaimSupportRepository(ABC):
    @abstractmethod
    async def create(self, support: ClaimSupport) -> None: ...
    @abstractmethod
    async def get(self, support_id: EntityId) -> ClaimSupport | None: ...
    @abstractmethod
    async def delete(self, support_id: EntityId) -> None: ...
    @abstractmethod
    async def list_by_claim(self, claim_id: EntityId) -> list[ClaimSupport]: ...

# src/hephaestus/forgebase/repository/claim_derivation_repo.py
from __future__ import annotations
from abc import ABC, abstractmethod
from hephaestus.forgebase.domain.models import ClaimDerivation
from hephaestus.forgebase.domain.values import EntityId

class ClaimDerivationRepository(ABC):
    @abstractmethod
    async def create(self, derivation: ClaimDerivation) -> None: ...
    @abstractmethod
    async def get(self, derivation_id: EntityId) -> ClaimDerivation | None: ...
    @abstractmethod
    async def delete(self, derivation_id: EntityId) -> None: ...
    @abstractmethod
    async def list_by_claim(self, claim_id: EntityId) -> list[ClaimDerivation]: ...

# src/hephaestus/forgebase/repository/link_repo.py
from __future__ import annotations
from abc import ABC, abstractmethod
from hephaestus.forgebase.domain.models import Link, LinkVersion
from hephaestus.forgebase.domain.values import EntityId, Version

class LinkRepository(ABC):
    @abstractmethod
    async def create(self, link: Link, version: LinkVersion) -> None: ...
    @abstractmethod
    async def get(self, link_id: EntityId) -> Link | None: ...
    @abstractmethod
    async def get_version(self, link_id: EntityId, version: Version) -> LinkVersion | None: ...
    @abstractmethod
    async def get_head_version(self, link_id: EntityId) -> LinkVersion | None: ...
    @abstractmethod
    async def create_version(self, version: LinkVersion) -> None: ...
    @abstractmethod
    async def list_by_entity(self, entity_id: EntityId, *, direction: str = "both", kind: str | None = None) -> list[Link]: ...
```

```python
# src/hephaestus/forgebase/repository/workbook_repo.py
from __future__ import annotations
from abc import ABC, abstractmethod
from hephaestus.forgebase.domain.models import (
    BranchClaimDerivationHead, BranchClaimHead, BranchClaimSupportHead,
    BranchLinkHead, BranchPageHead, BranchSourceHead, BranchTombstone, Workbook,
)
from hephaestus.forgebase.domain.enums import EntityKind, WorkbookStatus
from hephaestus.forgebase.domain.values import EntityId, Version

class WorkbookRepository(ABC):
    @abstractmethod
    async def create(self, workbook: Workbook) -> None: ...
    @abstractmethod
    async def get(self, workbook_id: EntityId) -> Workbook | None: ...
    @abstractmethod
    async def list_by_vault(self, vault_id: EntityId, *, status: WorkbookStatus | None = None) -> list[Workbook]: ...
    @abstractmethod
    async def update_status(self, workbook_id: EntityId, status: WorkbookStatus) -> None: ...
    # Branch page heads
    @abstractmethod
    async def set_page_head(self, head: BranchPageHead) -> None: ...
    @abstractmethod
    async def get_page_head(self, workbook_id: EntityId, page_id: EntityId) -> BranchPageHead | None: ...
    @abstractmethod
    async def list_page_heads(self, workbook_id: EntityId) -> list[BranchPageHead]: ...
    # Branch claim heads
    @abstractmethod
    async def set_claim_head(self, head: BranchClaimHead) -> None: ...
    @abstractmethod
    async def get_claim_head(self, workbook_id: EntityId, claim_id: EntityId) -> BranchClaimHead | None: ...
    @abstractmethod
    async def list_claim_heads(self, workbook_id: EntityId) -> list[BranchClaimHead]: ...
    # Branch link heads
    @abstractmethod
    async def set_link_head(self, head: BranchLinkHead) -> None: ...
    @abstractmethod
    async def get_link_head(self, workbook_id: EntityId, link_id: EntityId) -> BranchLinkHead | None: ...
    @abstractmethod
    async def list_link_heads(self, workbook_id: EntityId) -> list[BranchLinkHead]: ...
    # Branch source heads
    @abstractmethod
    async def set_source_head(self, head: BranchSourceHead) -> None: ...
    @abstractmethod
    async def get_source_head(self, workbook_id: EntityId, source_id: EntityId) -> BranchSourceHead | None: ...
    @abstractmethod
    async def list_source_heads(self, workbook_id: EntityId) -> list[BranchSourceHead]: ...
    # Claim support / derivation heads
    @abstractmethod
    async def set_claim_support_head(self, head: BranchClaimSupportHead) -> None: ...
    @abstractmethod
    async def list_claim_support_heads(self, workbook_id: EntityId) -> list[BranchClaimSupportHead]: ...
    @abstractmethod
    async def set_claim_derivation_head(self, head: BranchClaimDerivationHead) -> None: ...
    @abstractmethod
    async def list_claim_derivation_heads(self, workbook_id: EntityId) -> list[BranchClaimDerivationHead]: ...
    # Tombstones
    @abstractmethod
    async def add_tombstone(self, tombstone: BranchTombstone) -> None: ...
    @abstractmethod
    async def get_tombstone(self, workbook_id: EntityId, entity_kind: EntityKind, entity_id: EntityId) -> BranchTombstone | None: ...
    @abstractmethod
    async def list_tombstones(self, workbook_id: EntityId) -> list[BranchTombstone]: ...
```

```python
# src/hephaestus/forgebase/repository/merge_proposal_repo.py
from __future__ import annotations
from abc import ABC, abstractmethod
from hephaestus.forgebase.domain.models import MergeProposal
from hephaestus.forgebase.domain.values import EntityId, VaultRevisionId

class MergeProposalRepository(ABC):
    @abstractmethod
    async def create(self, proposal: MergeProposal) -> None: ...
    @abstractmethod
    async def get(self, merge_id: EntityId) -> MergeProposal | None: ...
    @abstractmethod
    async def set_result(self, merge_id: EntityId, resulting_revision: VaultRevisionId) -> None: ...

# src/hephaestus/forgebase/repository/merge_conflict_repo.py
from __future__ import annotations
from abc import ABC, abstractmethod
from hephaestus.forgebase.domain.models import MergeConflict
from hephaestus.forgebase.domain.enums import MergeResolution
from hephaestus.forgebase.domain.values import EntityId

class MergeConflictRepository(ABC):
    @abstractmethod
    async def create(self, conflict: MergeConflict) -> None: ...
    @abstractmethod
    async def get(self, conflict_id: EntityId) -> MergeConflict | None: ...
    @abstractmethod
    async def list_by_merge(self, merge_id: EntityId) -> list[MergeConflict]: ...
    @abstractmethod
    async def resolve(self, conflict_id: EntityId, resolution: MergeResolution) -> None: ...

# src/hephaestus/forgebase/repository/job_repo.py
from __future__ import annotations
from abc import ABC, abstractmethod
from datetime import datetime
from hephaestus.forgebase.domain.models import Job
from hephaestus.forgebase.domain.enums import JobStatus
from hephaestus.forgebase.domain.values import EntityId

class JobRepository(ABC):
    @abstractmethod
    async def create(self, job: Job) -> None: ...
    @abstractmethod
    async def get(self, job_id: EntityId) -> Job | None: ...
    @abstractmethod
    async def find_by_idempotency_key(self, key: str) -> Job | None: ...
    @abstractmethod
    async def update_status(self, job_id: EntityId, status: JobStatus, *, error: str | None = None, completed_at: datetime | None = None) -> None: ...
    @abstractmethod
    async def increment_attempt(self, job_id: EntityId, next_attempt_at: datetime | None = None) -> None: ...

# src/hephaestus/forgebase/repository/finding_repo.py
from __future__ import annotations
from abc import ABC, abstractmethod
from hephaestus.forgebase.domain.models import LintFinding
from hephaestus.forgebase.domain.enums import FindingStatus
from hephaestus.forgebase.domain.values import EntityId

class FindingRepository(ABC):
    @abstractmethod
    async def create(self, finding: LintFinding) -> None: ...
    @abstractmethod
    async def get(self, finding_id: EntityId) -> LintFinding | None: ...
    @abstractmethod
    async def list_by_job(self, job_id: EntityId) -> list[LintFinding]: ...
    @abstractmethod
    async def update_status(self, finding_id: EntityId, status: FindingStatus) -> None: ...

# src/hephaestus/forgebase/repository/run_ref_repo.py
from __future__ import annotations
from abc import ABC, abstractmethod
from hephaestus.forgebase.domain.models import KnowledgeRunRef
from hephaestus.forgebase.domain.values import EntityId

class KnowledgeRunRefRepository(ABC):
    @abstractmethod
    async def create(self, ref: KnowledgeRunRef) -> None: ...
    @abstractmethod
    async def get(self, ref_id: EntityId) -> KnowledgeRunRef | None: ...
    @abstractmethod
    async def update_sync_status(self, ref_id: EntityId, sync_status: str, *, sync_error: str | None = None) -> None: ...

# src/hephaestus/forgebase/repository/run_artifact_repo.py
from __future__ import annotations
from abc import ABC, abstractmethod
from hephaestus.forgebase.domain.models import KnowledgeRunArtifact
from hephaestus.forgebase.domain.values import EntityId

class KnowledgeRunArtifactRepository(ABC):
    @abstractmethod
    async def create(self, artifact: KnowledgeRunArtifact) -> None: ...
    @abstractmethod
    async def list_by_ref(self, ref_id: EntityId) -> list[KnowledgeRunArtifact]: ...
```

- [ ] **Step 3: Create content store and UoW contracts**

```python
# src/hephaestus/forgebase/repository/content_store.py
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
```

```python
# src/hephaestus/forgebase/repository/uow.py
"""UnitOfWork contract — the single atomic boundary for ForgeBase operations."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Self

from hephaestus.forgebase.domain.event_types import Clock, EventFactory
from hephaestus.forgebase.domain.models import DomainEvent
from hephaestus.forgebase.repository.claim_derivation_repo import ClaimDerivationRepository
from hephaestus.forgebase.repository.claim_repo import ClaimRepository
from hephaestus.forgebase.repository.claim_support_repo import ClaimSupportRepository
from hephaestus.forgebase.repository.content_store import StagedContentStore
from hephaestus.forgebase.repository.finding_repo import FindingRepository
from hephaestus.forgebase.repository.job_repo import JobRepository
from hephaestus.forgebase.repository.link_repo import LinkRepository
from hephaestus.forgebase.repository.merge_conflict_repo import MergeConflictRepository
from hephaestus.forgebase.repository.merge_proposal_repo import MergeProposalRepository
from hephaestus.forgebase.repository.page_repo import PageRepository
from hephaestus.forgebase.repository.run_artifact_repo import KnowledgeRunArtifactRepository
from hephaestus.forgebase.repository.run_ref_repo import KnowledgeRunRefRepository
from hephaestus.forgebase.repository.source_repo import SourceRepository
from hephaestus.forgebase.repository.vault_repo import VaultRepository
from hephaestus.forgebase.repository.workbook_repo import WorkbookRepository
from hephaestus.forgebase.service.id_generator import IdGenerator


class AbstractUnitOfWork(ABC):
    """Atomic transaction boundary: repos + outbox + content staging."""

    # Repository accessors — set by concrete implementations
    vaults: VaultRepository
    sources: SourceRepository
    pages: PageRepository
    claims: ClaimRepository
    claim_supports: ClaimSupportRepository
    claim_derivations: ClaimDerivationRepository
    links: LinkRepository
    workbooks: WorkbookRepository
    merge_proposals: MergeProposalRepository
    merge_conflicts: MergeConflictRepository
    jobs: JobRepository
    findings: FindingRepository
    run_refs: KnowledgeRunRefRepository
    run_artifacts: KnowledgeRunArtifactRepository
    content: StagedContentStore

    # Infrastructure — injected
    event_factory: EventFactory
    clock: Clock
    id_generator: IdGenerator

    def __init__(self) -> None:
        self._event_buffer: list[DomainEvent] = []

    def record_event(self, event: DomainEvent) -> None:
        """Buffer a domain event. Flushed to outbox on commit."""
        self._event_buffer.append(event)

    @property
    def pending_events(self) -> list[DomainEvent]:
        return list(self._event_buffer)

    @abstractmethod
    async def begin(self) -> None: ...

    @abstractmethod
    async def commit(self) -> None:
        """Persist state + flush events to outbox + finalize content. Pure persistence."""

    @abstractmethod
    async def rollback(self) -> None:
        """Roll back state + abort content + clear event buffer."""

    async def __aenter__(self) -> Self:
        await self.begin()
        return self

    async def __aexit__(self, exc_type: type | None, exc_val: object, exc_tb: object) -> None:
        if exc_type is not None:
            await self.rollback()
        elif self._event_buffer:
            # Auto-rollback if events were recorded but not committed
            await self.rollback()
```

- [ ] **Step 4: Verify all imports resolve**

Run: `python -c "from hephaestus.forgebase.repository.uow import AbstractUnitOfWork; print('OK')"`
Expected: OK

- [ ] **Step 5: Commit**

```bash
git add src/hephaestus/forgebase/repository/
git commit -m "feat(forgebase): add all repository contracts and UoW abstract interface"
```

---

### Task 6: SQLite Schema and In-Memory Content Store

**Files:**
- Create: `src/hephaestus/forgebase/store/__init__.py`
- Create: `src/hephaestus/forgebase/store/sqlite/__init__.py`
- Create: `src/hephaestus/forgebase/store/sqlite/schema.py`
- Create: `src/hephaestus/forgebase/store/blobs/__init__.py`
- Create: `src/hephaestus/forgebase/store/blobs/memory.py`
- Test: `tests/test_forgebase/test_store/__init__.py`
- Test: `tests/test_forgebase/test_store/test_local_fs_content.py`

- [ ] **Step 1: Write failing test for in-memory content store**

```python
# tests/test_forgebase/test_store/__init__.py

# tests/test_forgebase/test_store/test_local_fs_content.py
"""Tests for content store implementations."""
from __future__ import annotations

import pytest

from hephaestus.forgebase.store.blobs.memory import InMemoryContentStore


@pytest.mark.asyncio
class TestInMemoryContentStore:
    async def test_stage_and_finalize(self):
        store = InMemoryContentStore()
        ref = await store.stage(b"hello world", "text/plain")
        assert ref.size_bytes == 11
        await store.finalize()
        data = await store.read(ref.to_blob_ref())
        assert data == b"hello world"

    async def test_stage_and_abort(self):
        store = InMemoryContentStore()
        ref = await store.stage(b"hello world", "text/plain")
        await store.abort()
        with pytest.raises(KeyError):
            await store.read(ref.to_blob_ref())

    async def test_read_nonexistent_raises(self):
        store = InMemoryContentStore()
        from hephaestus.forgebase.domain.values import BlobRef, ContentHash
        ref = BlobRef(content_hash=ContentHash(sha256="x" * 64), size_bytes=0, mime_type="text/plain")
        with pytest.raises(KeyError):
            await store.read(ref)

    async def test_multiple_stages_before_finalize(self):
        store = InMemoryContentStore()
        r1 = await store.stage(b"one", "text/plain")
        r2 = await store.stage(b"two", "text/plain")
        await store.finalize()
        assert await store.read(r1.to_blob_ref()) == b"one"
        assert await store.read(r2.to_blob_ref()) == b"two"
```

- [ ] **Step 2: Run test to verify failure**

Run: `python -m pytest tests/test_forgebase/test_store/test_local_fs_content.py -v`
Expected: FAIL

- [ ] **Step 3: Implement InMemoryContentStore**

```python
# src/hephaestus/forgebase/store/__init__.py
"""ForgeBase store implementations."""
from __future__ import annotations

# src/hephaestus/forgebase/store/blobs/__init__.py
"""Blob storage implementations."""
from __future__ import annotations

# src/hephaestus/forgebase/store/blobs/memory.py
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
```

- [ ] **Step 4: Implement SQLite schema**

```python
# src/hephaestus/forgebase/store/sqlite/__init__.py
"""SQLite store implementation for ForgeBase."""
from __future__ import annotations

# src/hephaestus/forgebase/store/sqlite/schema.py
"""SQLite schema definition and initialization for ForgeBase."""
from __future__ import annotations

import aiosqlite

SCHEMA_SQL = """
-- Vaults
CREATE TABLE IF NOT EXISTS fb_vaults (
    vault_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    head_revision_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    config TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS fb_vault_revisions (
    revision_id TEXT PRIMARY KEY,
    vault_id TEXT NOT NULL,
    parent_revision_id TEXT,
    created_at TEXT NOT NULL,
    created_by_type TEXT NOT NULL,
    created_by_id TEXT NOT NULL,
    causation_event_id TEXT,
    summary TEXT NOT NULL DEFAULT ''
);

-- Canonical entity heads
CREATE TABLE IF NOT EXISTS fb_canonical_heads (
    vault_id TEXT NOT NULL,
    entity_kind TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    head_version INTEGER NOT NULL,
    PRIMARY KEY (vault_id, entity_kind, entity_id)
);

-- Sources
CREATE TABLE IF NOT EXISTS fb_sources (
    source_id TEXT PRIMARY KEY,
    vault_id TEXT NOT NULL,
    format TEXT NOT NULL,
    origin_locator TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fb_source_versions (
    source_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    title TEXT NOT NULL,
    authors TEXT NOT NULL DEFAULT '[]',
    url TEXT,
    raw_artifact_hash TEXT NOT NULL,
    raw_artifact_size INTEGER NOT NULL,
    raw_artifact_mime TEXT NOT NULL,
    normalized_hash TEXT,
    normalized_size INTEGER,
    normalized_mime TEXT,
    content_hash TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}',
    trust_tier TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    created_by_type TEXT NOT NULL,
    created_by_id TEXT NOT NULL,
    PRIMARY KEY (source_id, version)
);

-- Pages
CREATE TABLE IF NOT EXISTS fb_pages (
    page_id TEXT PRIMARY KEY,
    vault_id TEXT NOT NULL,
    page_type TEXT NOT NULL,
    page_key TEXT NOT NULL,
    created_at TEXT NOT NULL,
    created_by_run TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_fb_pages_vault_key ON fb_pages (vault_id, page_key);

CREATE TABLE IF NOT EXISTS fb_page_versions (
    page_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    title TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    content_size INTEGER NOT NULL,
    content_mime TEXT NOT NULL,
    content_hash_sha TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    compiled_from TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    created_by_type TEXT NOT NULL,
    created_by_id TEXT NOT NULL,
    schema_version INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (page_id, version)
);

-- Claims
CREATE TABLE IF NOT EXISTS fb_claims (
    claim_id TEXT PRIMARY KEY,
    vault_id TEXT NOT NULL,
    page_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fb_claim_versions (
    claim_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    statement TEXT NOT NULL,
    status TEXT NOT NULL,
    support_type TEXT NOT NULL,
    confidence REAL NOT NULL,
    validated_at TEXT NOT NULL,
    fresh_until TEXT,
    created_at TEXT NOT NULL,
    created_by_type TEXT NOT NULL,
    created_by_id TEXT NOT NULL,
    PRIMARY KEY (claim_id, version)
);

-- Claim provenance
CREATE TABLE IF NOT EXISTS fb_claim_supports (
    support_id TEXT PRIMARY KEY,
    claim_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    source_segment TEXT,
    strength REAL NOT NULL,
    created_at TEXT NOT NULL,
    created_by_type TEXT NOT NULL,
    created_by_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fb_claim_derivations (
    derivation_id TEXT PRIMARY KEY,
    claim_id TEXT NOT NULL,
    parent_claim_id TEXT NOT NULL,
    relationship TEXT NOT NULL,
    created_at TEXT NOT NULL,
    created_by_type TEXT NOT NULL,
    created_by_id TEXT NOT NULL
);

-- Links
CREATE TABLE IF NOT EXISTS fb_links (
    link_id TEXT PRIMARY KEY,
    vault_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fb_link_versions (
    link_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    source_entity TEXT NOT NULL,
    target_entity TEXT NOT NULL,
    label TEXT,
    weight REAL NOT NULL DEFAULT 1.0,
    created_at TEXT NOT NULL,
    created_by_type TEXT NOT NULL,
    created_by_id TEXT NOT NULL,
    PRIMARY KEY (link_id, version)
);

-- Workbooks (= branches)
CREATE TABLE IF NOT EXISTS fb_workbooks (
    workbook_id TEXT PRIMARY KEY,
    vault_id TEXT NOT NULL,
    name TEXT NOT NULL,
    purpose TEXT NOT NULL,
    status TEXT NOT NULL,
    base_revision_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    created_by_type TEXT NOT NULL,
    created_by_id TEXT NOT NULL,
    created_by_run TEXT
);

-- Branch heads (COW overrides)
CREATE TABLE IF NOT EXISTS fb_branch_page_heads (
    workbook_id TEXT NOT NULL,
    page_id TEXT NOT NULL,
    head_version INTEGER NOT NULL,
    base_version INTEGER NOT NULL,
    PRIMARY KEY (workbook_id, page_id)
);

CREATE TABLE IF NOT EXISTS fb_branch_claim_heads (
    workbook_id TEXT NOT NULL,
    claim_id TEXT NOT NULL,
    head_version INTEGER NOT NULL,
    base_version INTEGER NOT NULL,
    PRIMARY KEY (workbook_id, claim_id)
);

CREATE TABLE IF NOT EXISTS fb_branch_link_heads (
    workbook_id TEXT NOT NULL,
    link_id TEXT NOT NULL,
    head_version INTEGER NOT NULL,
    base_version INTEGER NOT NULL,
    PRIMARY KEY (workbook_id, link_id)
);

CREATE TABLE IF NOT EXISTS fb_branch_source_heads (
    workbook_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    head_version INTEGER NOT NULL,
    base_version INTEGER NOT NULL,
    PRIMARY KEY (workbook_id, source_id)
);

CREATE TABLE IF NOT EXISTS fb_branch_claim_support_heads (
    workbook_id TEXT NOT NULL,
    support_id TEXT NOT NULL,
    created_on_branch INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (workbook_id, support_id)
);

CREATE TABLE IF NOT EXISTS fb_branch_claim_derivation_heads (
    workbook_id TEXT NOT NULL,
    derivation_id TEXT NOT NULL,
    created_on_branch INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (workbook_id, derivation_id)
);

CREATE TABLE IF NOT EXISTS fb_branch_tombstones (
    workbook_id TEXT NOT NULL,
    entity_kind TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    tombstoned_at TEXT NOT NULL,
    PRIMARY KEY (workbook_id, entity_kind, entity_id)
);

-- Merge
CREATE TABLE IF NOT EXISTS fb_merge_proposals (
    merge_id TEXT PRIMARY KEY,
    workbook_id TEXT NOT NULL,
    vault_id TEXT NOT NULL,
    base_revision_id TEXT NOT NULL,
    target_revision_id TEXT NOT NULL,
    verdict TEXT NOT NULL,
    resulting_revision TEXT,
    proposed_at TEXT NOT NULL,
    resolved_at TEXT,
    proposed_by_type TEXT NOT NULL,
    proposed_by_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fb_merge_conflicts (
    conflict_id TEXT PRIMARY KEY,
    merge_id TEXT NOT NULL,
    entity_kind TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    base_version INTEGER NOT NULL,
    branch_version INTEGER NOT NULL,
    canonical_version INTEGER NOT NULL,
    resolution TEXT,
    resolved_at TEXT
);

-- Jobs
CREATE TABLE IF NOT EXISTS fb_jobs (
    job_id TEXT PRIMARY KEY,
    vault_id TEXT NOT NULL,
    workbook_id TEXT,
    kind TEXT NOT NULL,
    status TEXT NOT NULL,
    config TEXT NOT NULL DEFAULT '{}',
    idempotency_key TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 0,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    next_attempt_at TEXT,
    leased_until TEXT,
    heartbeat_at TEXT,
    started_at TEXT,
    completed_at TEXT,
    error TEXT,
    created_by_type TEXT NOT NULL,
    created_by_id TEXT NOT NULL,
    created_by_run TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_fb_jobs_idemp ON fb_jobs (idempotency_key);

-- Lint findings
CREATE TABLE IF NOT EXISTS fb_lint_findings (
    finding_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    vault_id TEXT NOT NULL,
    category TEXT NOT NULL,
    severity TEXT NOT NULL,
    page_id TEXT,
    claim_id TEXT,
    description TEXT NOT NULL,
    suggested_action TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    resolved_at TEXT
);

-- Run integration
CREATE TABLE IF NOT EXISTS fb_run_refs (
    ref_id TEXT PRIMARY KEY,
    vault_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    run_type TEXT NOT NULL,
    upstream_system TEXT NOT NULL,
    upstream_ref TEXT,
    source_hash TEXT,
    sync_status TEXT NOT NULL DEFAULT 'pending',
    sync_error TEXT,
    synced_at TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fb_run_artifacts (
    ref_id TEXT NOT NULL,
    entity_kind TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    role TEXT NOT NULL,
    PRIMARY KEY (ref_id, entity_kind, entity_id)
);

-- Domain events (outbox)
CREATE TABLE IF NOT EXISTS fb_domain_events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    schema_version INTEGER NOT NULL,
    aggregate_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    aggregate_version INTEGER,
    vault_id TEXT NOT NULL,
    workbook_id TEXT,
    run_id TEXT,
    causation_id TEXT,
    correlation_id TEXT,
    actor_type TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    payload TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_fb_events_aggregate ON fb_domain_events (aggregate_type, aggregate_id);
CREATE INDEX IF NOT EXISTS idx_fb_events_vault ON fb_domain_events (vault_id);

-- Event deliveries
CREATE TABLE IF NOT EXISTS fb_event_deliveries (
    event_id TEXT NOT NULL,
    consumer_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TEXT,
    lease_owner TEXT,
    lease_expires_at TEXT,
    last_error TEXT,
    delivered_at TEXT,
    PRIMARY KEY (event_id, consumer_name)
);
CREATE INDEX IF NOT EXISTS idx_fb_deliveries_pending ON fb_event_deliveries (consumer_name, status, next_attempt_at);
"""


async def initialize_schema(db: aiosqlite.Connection) -> None:
    """Create all ForgeBase tables."""
    await db.executescript(SCHEMA_SQL)
    await db.execute("PRAGMA journal_mode=WAL")
    await db.commit()
```

- [ ] **Step 5: Run content store tests**

Run: `python -m pytest tests/test_forgebase/test_store/test_local_fs_content.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/hephaestus/forgebase/store/ tests/test_forgebase/test_store/
git commit -m "feat(forgebase): add SQLite schema, in-memory content store"
```

---

### Task 7: SQLite Vault Repository + UoW (First Backend Implementation)

This task implements the SQLite vault repository and the SQLite UoW as the first concrete backend. Subsequent tasks will add remaining entity repositories following this established pattern.

**Files:**
- Create: `src/hephaestus/forgebase/store/sqlite/vault_repo.py`
- Create: `src/hephaestus/forgebase/store/sqlite/uow.py`
- Create: `src/hephaestus/forgebase/store/sqlite/event_repo.py`
- Create: `tests/test_forgebase/conftest.py`
- Create: `tests/test_forgebase/test_store/conftest.py`
- Test: `tests/test_forgebase/test_store/test_sqlite_vault_repo.py`
- Test: `tests/test_forgebase/test_store/test_sqlite_uow.py`

- [ ] **Step 1: Write test fixtures (conftest)**

```python
# tests/test_forgebase/conftest.py
"""Shared test fixtures for ForgeBase."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from hephaestus.forgebase.domain.enums import ActorType
from hephaestus.forgebase.domain.event_types import FixedClock
from hephaestus.forgebase.domain.values import ActorRef
from hephaestus.forgebase.service.id_generator import DeterministicIdGenerator


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(datetime(2026, 4, 3, 12, 0, 0, tzinfo=UTC))


@pytest.fixture
def id_gen() -> DeterministicIdGenerator:
    return DeterministicIdGenerator()


@pytest.fixture
def actor() -> ActorRef:
    return ActorRef(actor_type=ActorType.SYSTEM, actor_id="test")
```

```python
# tests/test_forgebase/test_store/conftest.py
"""SQLite store test fixtures."""
from __future__ import annotations

import tempfile
from pathlib import Path

import aiosqlite
import pytest

from hephaestus.forgebase.store.sqlite.schema import initialize_schema


@pytest.fixture
async def sqlite_db(tmp_path: Path):
    """File-backed SQLite database with WAL mode for realistic testing."""
    db_path = tmp_path / "forgebase_test.db"
    db = await aiosqlite.connect(str(db_path))
    db.row_factory = aiosqlite.Row
    await initialize_schema(db)
    yield db
    await db.close()
```

- [ ] **Step 2: Write failing vault repo tests**

```python
# tests/test_forgebase/test_store/test_sqlite_vault_repo.py
"""Tests for SQLite vault repository."""
from __future__ import annotations

import pytest

from hephaestus.forgebase.domain.models import Vault, VaultRevision
from hephaestus.forgebase.domain.values import ActorRef, EntityId, VaultRevisionId
from hephaestus.forgebase.service.id_generator import DeterministicIdGenerator
from hephaestus.forgebase.store.sqlite.vault_repo import SqliteVaultRepository


@pytest.mark.asyncio
class TestSqliteVaultRepository:
    async def test_create_and_get(self, sqlite_db, clock, id_gen, actor):
        repo = SqliteVaultRepository(sqlite_db)
        vault_id = id_gen.vault_id()
        rev_id = id_gen.revision_id()

        vault = Vault(
            vault_id=vault_id,
            name="test",
            description="test vault",
            head_revision_id=rev_id,
            created_at=clock.now(),
            updated_at=clock.now(),
            config={},
        )
        revision = VaultRevision(
            revision_id=rev_id,
            vault_id=vault_id,
            parent_revision_id=None,
            created_at=clock.now(),
            created_by=actor,
            causation_event_id=None,
            summary="Initial revision",
        )

        await repo.create(vault, revision)
        await sqlite_db.commit()

        got = await repo.get(vault_id)
        assert got is not None
        assert got.name == "test"
        assert got.vault_id == vault_id

    async def test_get_nonexistent_returns_none(self, sqlite_db, id_gen):
        repo = SqliteVaultRepository(sqlite_db)
        assert await repo.get(id_gen.vault_id()) is None

    async def test_list_all(self, sqlite_db, clock, id_gen, actor):
        repo = SqliteVaultRepository(sqlite_db)

        for i in range(3):
            vid = id_gen.vault_id()
            rid = id_gen.revision_id()
            vault = Vault(vault_id=vid, name=f"v{i}", description="", head_revision_id=rid, created_at=clock.now(), updated_at=clock.now(), config={})
            rev = VaultRevision(revision_id=rid, vault_id=vid, parent_revision_id=None, created_at=clock.now(), created_by=actor, causation_event_id=None, summary="init")
            await repo.create(vault, rev)

        await sqlite_db.commit()
        vaults = await repo.list_all()
        assert len(vaults) == 3

    async def test_update_config(self, sqlite_db, clock, id_gen, actor):
        repo = SqliteVaultRepository(sqlite_db)
        vid = id_gen.vault_id()
        rid = id_gen.revision_id()
        vault = Vault(vault_id=vid, name="test", description="", head_revision_id=rid, created_at=clock.now(), updated_at=clock.now(), config={})
        rev = VaultRevision(revision_id=rid, vault_id=vid, parent_revision_id=None, created_at=clock.now(), created_by=actor, causation_event_id=None, summary="init")
        await repo.create(vault, rev)
        await sqlite_db.commit()

        await repo.update_config(vid, {"depth": 5})
        await sqlite_db.commit()

        got = await repo.get(vid)
        assert got is not None
        assert got.config == {"depth": 5}
```

- [ ] **Step 3: Run tests to verify failure**

Run: `python -m pytest tests/test_forgebase/test_store/test_sqlite_vault_repo.py -v`
Expected: FAIL

- [ ] **Step 4: Implement SqliteVaultRepository**

```python
# src/hephaestus/forgebase/store/sqlite/vault_repo.py
"""SQLite implementation of VaultRepository."""
from __future__ import annotations

import json
from datetime import datetime

import aiosqlite

from hephaestus.forgebase.domain.enums import ActorType
from hephaestus.forgebase.domain.models import Vault, VaultRevision
from hephaestus.forgebase.domain.values import ActorRef, EntityId, VaultRevisionId
from hephaestus.forgebase.repository.vault_repo import VaultRepository


class SqliteVaultRepository(VaultRepository):
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def create(self, vault: Vault, revision: VaultRevision) -> None:
        await self._db.execute(
            "INSERT INTO fb_vaults (vault_id, name, description, head_revision_id, created_at, updated_at, config) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (str(vault.vault_id), vault.name, vault.description, str(vault.head_revision_id), vault.created_at.isoformat(), vault.updated_at.isoformat(), json.dumps(vault.config)),
        )
        await self.create_revision(revision)

    async def get(self, vault_id: EntityId) -> Vault | None:
        cursor = await self._db.execute("SELECT * FROM fb_vaults WHERE vault_id = ?", (str(vault_id),))
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_vault(row)

    async def list_all(self) -> list[Vault]:
        cursor = await self._db.execute("SELECT * FROM fb_vaults ORDER BY created_at")
        rows = await cursor.fetchall()
        return [self._row_to_vault(r) for r in rows]

    async def update_head(self, vault_id: EntityId, revision_id: VaultRevisionId) -> None:
        await self._db.execute(
            "UPDATE fb_vaults SET head_revision_id = ?, updated_at = ? WHERE vault_id = ?",
            (str(revision_id), datetime.now().isoformat(), str(vault_id)),
        )

    async def update_config(self, vault_id: EntityId, config: dict) -> None:
        await self._db.execute(
            "UPDATE fb_vaults SET config = ?, updated_at = ? WHERE vault_id = ?",
            (json.dumps(config), datetime.now().isoformat(), str(vault_id)),
        )

    async def get_revision(self, revision_id: VaultRevisionId) -> VaultRevision | None:
        cursor = await self._db.execute("SELECT * FROM fb_vault_revisions WHERE revision_id = ?", (str(revision_id),))
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_revision(row)

    async def create_revision(self, revision: VaultRevision) -> None:
        await self._db.execute(
            "INSERT INTO fb_vault_revisions (revision_id, vault_id, parent_revision_id, created_at, created_by_type, created_by_id, causation_event_id, summary) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (str(revision.revision_id), str(revision.vault_id), str(revision.parent_revision_id) if revision.parent_revision_id else None, revision.created_at.isoformat(), revision.created_by.actor_type.value, revision.created_by.actor_id, str(revision.causation_event_id) if revision.causation_event_id else None, revision.summary),
        )

    async def get_canonical_page_head(self, vault_id: EntityId, page_id: EntityId) -> int | None:
        return await self._get_head(vault_id, "page", page_id)

    async def set_canonical_page_head(self, vault_id: EntityId, page_id: EntityId, version: int) -> None:
        await self._set_head(vault_id, "page", page_id, version)

    async def get_canonical_claim_head(self, vault_id: EntityId, claim_id: EntityId) -> int | None:
        return await self._get_head(vault_id, "claim", claim_id)

    async def set_canonical_claim_head(self, vault_id: EntityId, claim_id: EntityId, version: int) -> None:
        await self._set_head(vault_id, "claim", claim_id, version)

    async def get_canonical_link_head(self, vault_id: EntityId, link_id: EntityId) -> int | None:
        return await self._get_head(vault_id, "link", link_id)

    async def set_canonical_link_head(self, vault_id: EntityId, link_id: EntityId, version: int) -> None:
        await self._set_head(vault_id, "link", link_id, version)

    async def get_canonical_source_head(self, vault_id: EntityId, source_id: EntityId) -> int | None:
        return await self._get_head(vault_id, "source", source_id)

    async def set_canonical_source_head(self, vault_id: EntityId, source_id: EntityId, version: int) -> None:
        await self._set_head(vault_id, "source", source_id, version)

    async def _get_head(self, vault_id: EntityId, kind: str, entity_id: EntityId) -> int | None:
        cursor = await self._db.execute(
            "SELECT head_version FROM fb_canonical_heads WHERE vault_id = ? AND entity_kind = ? AND entity_id = ?",
            (str(vault_id), kind, str(entity_id)),
        )
        row = await cursor.fetchone()
        return row["head_version"] if row else None

    async def _set_head(self, vault_id: EntityId, kind: str, entity_id: EntityId, version: int) -> None:
        await self._db.execute(
            "INSERT OR REPLACE INTO fb_canonical_heads (vault_id, entity_kind, entity_id, head_version) VALUES (?, ?, ?, ?)",
            (str(vault_id), kind, str(entity_id), version),
        )

    @staticmethod
    def _row_to_vault(row: aiosqlite.Row) -> Vault:
        return Vault(
            vault_id=EntityId(row["vault_id"]),
            name=row["name"],
            description=row["description"],
            head_revision_id=VaultRevisionId(row["head_revision_id"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            config=json.loads(row["config"]),
        )

    @staticmethod
    def _row_to_revision(row: aiosqlite.Row) -> VaultRevision:
        return VaultRevision(
            revision_id=VaultRevisionId(row["revision_id"]),
            vault_id=EntityId(row["vault_id"]),
            parent_revision_id=VaultRevisionId(row["parent_revision_id"]) if row["parent_revision_id"] else None,
            created_at=datetime.fromisoformat(row["created_at"]),
            created_by=ActorRef(actor_type=ActorType(row["created_by_type"]), actor_id=row["created_by_id"]),
            causation_event_id=EntityId(row["causation_event_id"]) if row["causation_event_id"] else None,
            summary=row["summary"],
        )
```

- [ ] **Step 5: Run vault repo tests**

Run: `python -m pytest tests/test_forgebase/test_store/test_sqlite_vault_repo.py -v`
Expected: All PASS

- [ ] **Step 6: Implement SQLite event repo (for outbox persistence)**

```python
# src/hephaestus/forgebase/store/sqlite/event_repo.py
"""SQLite event persistence for the transactional outbox."""
from __future__ import annotations

import json
from datetime import datetime

import aiosqlite

from hephaestus.forgebase.domain.enums import ActorType
from hephaestus.forgebase.domain.models import DomainEvent, EventDelivery
from hephaestus.forgebase.domain.values import EntityId, Version


class SqliteEventRepository:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def insert_event(self, event: DomainEvent) -> None:
        await self._db.execute(
            "INSERT INTO fb_domain_events (event_id, event_type, schema_version, aggregate_type, aggregate_id, aggregate_version, vault_id, workbook_id, run_id, causation_id, correlation_id, actor_type, actor_id, occurred_at, payload) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(event.event_id), event.event_type, event.schema_version,
                event.aggregate_type, str(event.aggregate_id),
                event.aggregate_version.number if event.aggregate_version else None,
                str(event.vault_id),
                str(event.workbook_id) if event.workbook_id else None,
                event.run_id,
                str(event.causation_id) if event.causation_id else None,
                event.correlation_id,
                event.actor_type.value, event.actor_id,
                event.occurred_at.isoformat(),
                json.dumps(event.payload),
            ),
        )

    async def insert_delivery(self, event_id: EntityId, consumer_name: str) -> None:
        await self._db.execute(
            "INSERT INTO fb_event_deliveries (event_id, consumer_name, status) VALUES (?, ?, 'pending')",
            (str(event_id), consumer_name),
        )

    async def flush_events(self, events: list[DomainEvent], consumer_names: list[str]) -> None:
        """Persist all buffered events + create delivery rows for each consumer."""
        for event in events:
            await self.insert_event(event)
            for consumer in consumer_names:
                await self.insert_delivery(event.event_id, consumer)
```

- [ ] **Step 7: Implement SQLite UoW**

```python
# src/hephaestus/forgebase/store/sqlite/uow.py
"""SQLite UnitOfWork implementation."""
from __future__ import annotations

import aiosqlite

from hephaestus.forgebase.domain.event_types import Clock, EventFactory
from hephaestus.forgebase.repository.content_store import StagedContentStore
from hephaestus.forgebase.repository.uow import AbstractUnitOfWork
from hephaestus.forgebase.service.id_generator import IdGenerator
from hephaestus.forgebase.store.sqlite.event_repo import SqliteEventRepository
from hephaestus.forgebase.store.sqlite.vault_repo import SqliteVaultRepository


class SqliteUnitOfWork(AbstractUnitOfWork):
    """SQLite-backed UoW: single connection, single-writer."""

    def __init__(
        self,
        db: aiosqlite.Connection,
        content: StagedContentStore,
        clock: Clock,
        id_generator: IdGenerator,
        consumer_names: list[str] | None = None,
    ) -> None:
        super().__init__()
        self._db = db
        self.content = content
        self.clock = clock
        self.id_generator = id_generator
        self.event_factory = EventFactory(clock=clock, id_generator=id_generator)
        self._consumer_names = consumer_names or []
        self._event_repo = SqliteEventRepository(db)

        # Wire up repos
        self.vaults = SqliteVaultRepository(db)
        # Remaining repos will be wired in subsequent tasks as they're implemented

    async def begin(self) -> None:
        await self._db.execute("BEGIN")

    async def commit(self) -> None:
        # Flush events to outbox within the same transaction
        if self._event_buffer:
            await self._event_repo.flush_events(self._event_buffer, self._consumer_names)

        await self._db.commit()

        # Finalize content AFTER db commit succeeds
        await self.content.finalize()

        self._event_buffer.clear()

    async def rollback(self) -> None:
        await self._db.rollback()
        await self.content.abort()
        self._event_buffer.clear()
```

- [ ] **Step 8: Write and run UoW transaction tests**

```python
# tests/test_forgebase/test_store/test_sqlite_uow.py
"""Tests for SQLite UnitOfWork — transaction atomicity."""
from __future__ import annotations

import pytest

from hephaestus.forgebase.domain.event_types import EventFactory, FixedClock
from hephaestus.forgebase.domain.models import Vault, VaultRevision
from hephaestus.forgebase.domain.values import ActorRef
from hephaestus.forgebase.service.id_generator import DeterministicIdGenerator
from hephaestus.forgebase.store.blobs.memory import InMemoryContentStore
from hephaestus.forgebase.store.sqlite.uow import SqliteUnitOfWork


@pytest.mark.asyncio
class TestSqliteUoW:
    async def test_commit_persists_state_and_events(self, sqlite_db, clock, id_gen, actor):
        content = InMemoryContentStore()
        uow = SqliteUnitOfWork(sqlite_db, content, clock, id_gen, consumer_names=["test_consumer"])

        async with uow:
            vault_id = uow.id_generator.vault_id()
            rev_id = uow.id_generator.revision_id()
            vault = Vault(vault_id=vault_id, name="test", description="", head_revision_id=rev_id, created_at=clock.now(), updated_at=clock.now(), config={})
            revision = VaultRevision(revision_id=rev_id, vault_id=vault_id, parent_revision_id=None, created_at=clock.now(), created_by=actor, causation_event_id=None, summary="init")
            await uow.vaults.create(vault, revision)

            event = uow.event_factory.create(
                event_type="vault.created",
                aggregate_type="vault",
                aggregate_id=vault_id,
                vault_id=vault_id,
                payload={"name": "test"},
                actor=actor,
            )
            uow.record_event(event)
            await uow.commit()

        # Verify state persisted
        got = await uow.vaults.get(vault_id)
        assert got is not None
        assert got.name == "test"

        # Verify event persisted
        cursor = await sqlite_db.execute("SELECT COUNT(*) as c FROM fb_domain_events")
        row = await cursor.fetchone()
        assert row["c"] == 1

        # Verify delivery created
        cursor = await sqlite_db.execute("SELECT COUNT(*) as c FROM fb_event_deliveries")
        row = await cursor.fetchone()
        assert row["c"] == 1

    async def test_rollback_discards_state_and_events(self, sqlite_db, clock, id_gen, actor):
        content = InMemoryContentStore()
        uow = SqliteUnitOfWork(sqlite_db, content, clock, id_gen, consumer_names=["test_consumer"])

        vault_id = id_gen.vault_id()
        try:
            async with uow:
                rev_id = uow.id_generator.revision_id()
                vault = Vault(vault_id=vault_id, name="rollback_test", description="", head_revision_id=rev_id, created_at=clock.now(), updated_at=clock.now(), config={})
                revision = VaultRevision(revision_id=rev_id, vault_id=vault_id, parent_revision_id=None, created_at=clock.now(), created_by=actor, causation_event_id=None, summary="init")
                await uow.vaults.create(vault, revision)

                event = uow.event_factory.create(
                    event_type="vault.created",
                    aggregate_type="vault",
                    aggregate_id=vault_id,
                    vault_id=vault_id,
                    payload={},
                    actor=actor,
                )
                uow.record_event(event)
                raise ValueError("Simulated failure")
        except ValueError:
            pass

        # Verify state NOT persisted
        got = await uow.vaults.get(vault_id)
        assert got is None

        # Verify events NOT persisted
        cursor = await sqlite_db.execute("SELECT COUNT(*) as c FROM fb_domain_events")
        row = await cursor.fetchone()
        assert row["c"] == 0

    async def test_content_finalized_on_commit(self, sqlite_db, clock, id_gen, actor):
        content = InMemoryContentStore()
        uow = SqliteUnitOfWork(sqlite_db, content, clock, id_gen)

        async with uow:
            ref = await uow.content.stage(b"test content", "text/plain")
            await uow.commit()

        # Content should be finalized and readable
        data = await content.read(ref.to_blob_ref())
        assert data == b"test content"

    async def test_content_aborted_on_rollback(self, sqlite_db, clock, id_gen, actor):
        content = InMemoryContentStore()
        uow = SqliteUnitOfWork(sqlite_db, content, clock, id_gen)

        try:
            async with uow:
                ref = await uow.content.stage(b"test content", "text/plain")
                raise ValueError("fail")
        except ValueError:
            pass

        with pytest.raises(KeyError):
            await content.read(ref.to_blob_ref())
```

- [ ] **Step 9: Run all store tests**

Run: `python -m pytest tests/test_forgebase/test_store/ -v`
Expected: All PASS

- [ ] **Step 10: Commit**

```bash
git add src/hephaestus/forgebase/store/sqlite/ tests/test_forgebase/conftest.py tests/test_forgebase/test_store/
git commit -m "feat(forgebase): add SQLite vault repo, event repo, UoW with transaction tests"
```

---

### Task 8-14: Remaining SQLite Repository Implementations

Tasks 8-14 follow the exact pattern established in Task 7. Each task implements one or two SQLite repository classes, writes tests, and commits. The pattern is:

1. Write failing repo test (CRUD, version chains, idempotency)
2. Implement the repo class mapping domain models ↔ SQL rows
3. Wire the repo into `SqliteUnitOfWork.__init__`
4. Run tests, commit

**Task 8:** `SqliteSourceRepository` + `SqlitePageRepository`
**Task 9:** `SqliteClaimRepository` + `SqliteClaimSupportRepository` + `SqliteClaimDerivationRepository`
**Task 10:** `SqliteLinkRepository`
**Task 11:** `SqliteWorkbookRepository` (branch heads, tombstones — largest repo)
**Task 12:** `SqliteMergeProposalRepository` + `SqliteMergeConflictRepository`
**Task 13:** `SqliteJobRepository` + `SqliteFindingRepository`
**Task 14:** `SqliteRunRefRepository` + `SqliteRunArtifactRepository`

Each follows the exact same structure as Task 7 Step 4 (vault repo). The key differences per entity:
- **Source/Page/Claim/Link repos**: Row mapping includes BlobRef reconstruction from hash/size/mime columns, Version wrapping, ActorRef reconstruction from type/id columns
- **Workbook repo**: Branch head CRUD (set/get/list for each entity kind), tombstone management
- **Job repo**: `find_by_idempotency_key`, `increment_attempt`, `update_status`
- **Merge repos**: `resolve` conflict, `set_result` on proposal

After all 7 tasks, update `SqliteUnitOfWork.__init__` to wire all repos.

---

### Task 15: VaultService (First Service Implementation)

**Files:**
- Create: `src/hephaestus/forgebase/service/vault_service.py`
- Test: `tests/test_forgebase/test_service/__init__.py`
- Test: `tests/test_forgebase/test_service/test_vault_service.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_forgebase/test_service/__init__.py

# tests/test_forgebase/test_service/test_vault_service.py
"""Tests for VaultService."""
from __future__ import annotations

import pytest

from hephaestus.forgebase.service.vault_service import VaultService
from hephaestus.forgebase.store.blobs.memory import InMemoryContentStore
from hephaestus.forgebase.store.sqlite.uow import SqliteUnitOfWork


@pytest.mark.asyncio
class TestVaultService:
    async def test_create_vault(self, sqlite_db, clock, id_gen, actor):
        content = InMemoryContentStore()

        def uow_factory():
            return SqliteUnitOfWork(sqlite_db, content, clock, id_gen, consumer_names=["test"])

        svc = VaultService(uow_factory=uow_factory, default_actor=actor)
        vault = await svc.create_vault(name="research", description="Battery materials research")

        assert vault.name == "research"
        assert vault.vault_id.prefix == "vault"

        # Verify event was emitted
        cursor = await sqlite_db.execute(
            "SELECT event_type FROM fb_domain_events WHERE vault_id = ?",
            (str(vault.vault_id),),
        )
        row = await cursor.fetchone()
        assert row["event_type"] == "vault.created"
```

- [ ] **Step 2: Run test to verify failure**

Run: `python -m pytest tests/test_forgebase/test_service/test_vault_service.py -v`
Expected: FAIL

- [ ] **Step 3: Implement VaultService**

```python
# src/hephaestus/forgebase/service/vault_service.py
"""Vault service — create and configure vaults."""
from __future__ import annotations

from typing import Any, Callable

from hephaestus.forgebase.domain.models import Vault, VaultRevision
from hephaestus.forgebase.domain.values import ActorRef
from hephaestus.forgebase.repository.uow import AbstractUnitOfWork


class VaultService:
    def __init__(
        self,
        uow_factory: Callable[[], AbstractUnitOfWork],
        default_actor: ActorRef,
    ) -> None:
        self._uow_factory = uow_factory
        self._default_actor = default_actor

    async def create_vault(
        self,
        name: str,
        description: str = "",
        config: dict[str, Any] | None = None,
    ) -> Vault:
        uow = self._uow_factory()
        async with uow:
            vault_id = uow.id_generator.vault_id()
            rev_id = uow.id_generator.revision_id()
            now = uow.clock.now()

            vault = Vault(
                vault_id=vault_id,
                name=name,
                description=description,
                head_revision_id=rev_id,
                created_at=now,
                updated_at=now,
                config=config or {},
            )
            revision = VaultRevision(
                revision_id=rev_id,
                vault_id=vault_id,
                parent_revision_id=None,
                created_at=now,
                created_by=self._default_actor,
                causation_event_id=None,
                summary="Vault created",
            )

            await uow.vaults.create(vault, revision)

            uow.record_event(uow.event_factory.create(
                event_type="vault.created",
                aggregate_type="vault",
                aggregate_id=vault_id,
                vault_id=vault_id,
                payload={"name": name, "description": description},
                actor=self._default_actor,
            ))

            await uow.commit()
        return vault

    async def update_vault_config(self, vault_id: Any, config: dict[str, Any]) -> Vault:
        uow = self._uow_factory()
        async with uow:
            await uow.vaults.update_config(vault_id, config)

            uow.record_event(uow.event_factory.create(
                event_type="vault.config_updated",
                aggregate_type="vault",
                aggregate_id=vault_id,
                vault_id=vault_id,
                payload={"config": config},
                actor=self._default_actor,
            ))

            await uow.commit()

        # Re-read from committed state
        got = await uow.vaults.get(vault_id)
        assert got is not None
        return got
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_forgebase/test_service/test_vault_service.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/hephaestus/forgebase/service/vault_service.py tests/test_forgebase/test_service/
git commit -m "feat(forgebase): add VaultService with create and config update"
```

---

### Tasks 16-21: Remaining Services, Query Layer, Events, Integration

These tasks follow the same TDD pattern. Each implements one service or subsystem:

**Task 16:** `IngestService` + `PageService` — source ingestion with content staging, page CRUD with versioning
**Task 17:** `ClaimService` + `LinkService` — claim CRUD, support/derivation management, link CRUD
**Task 18:** `BranchService` + `MergeService` — workbook creation, merge proposal/execution with conflict detection, stale merge validation
**Task 19:** `CompileService` (stub) + `LintService` (stub) + `RunIntegrationService` — job scheduling, finding management, run ref/artifact tracking
**Task 20:** Event `dispatcher.py` + `consumers.py` — background outbox poller, consumer registry, delivery tracking, dead-letter
**Task 21:** Query layer — `vault_queries`, `page_queries`, `claim_queries`, `branch_queries` with COW read-through, `diff_workbook`

### Task 22: Integration Bridge

**Files:**
- Create: `src/hephaestus/forgebase/integration/bridge.py`
- Create: `src/hephaestus/forgebase/integration/genesis_adapter.py`
- Create: `src/hephaestus/forgebase/integration/pantheon_adapter.py`
- Create: `src/hephaestus/forgebase/integration/research_adapter.py`
- Test: `tests/test_forgebase/test_integration/test_bridge.py`

The bridge defines `ForgeBaseIntegrationBridge(ABC)` with `on_genesis_completed`, `on_pantheon_completed`, `on_research_completed`. Each adapter translates upstream domain objects into ForgeBase durable jobs. Bridge is a no-op when vault_id is absent.

### Task 23: Factory and Bootstrap

**Files:**
- Create: `src/hephaestus/forgebase/factory.py`
- Test: `tests/test_forgebase/test_e2e/__init__.py`
- Test: `tests/test_forgebase/test_e2e/test_full_lifecycle.py`

`factory.py` reads config, instantiates the correct backend (SQLite or Postgres), wires all repos, services, event dispatcher, and returns a ready `ForgeBase` instance.

### Task 24: End-to-End Lifecycle Test

The e2e test executes the 10 minimum real flows from the spec end-to-end:

1. Create vault
2. Ingest raw source → store raw artifact
3. Normalize source
4. Store source card metadata
5. Create/update page with content
6. Attach claims with provenance (supports + derivations)
7. Open workbook branch
8. Propose page/claim/source updates in workbook
9. Diff workbook vs canonical
10. Merge workbook into vault with version record + conflict detection

This validates the entire Foundation Platform works as an integrated system.

---

### Task 25: Postgres Store Implementation + Dual-Backend Test Matrix

After all SQLite-backed tasks pass, implement the Postgres backend:

- Create: `src/hephaestus/forgebase/store/postgres/` — mirror of sqlite/ with asyncpg
- Modify: `tests/test_forgebase/test_store/conftest.py` — add parametrized `uow` fixture

The Postgres schema is identical to SQLite (same table names, same columns). Implementation differences:
- `asyncpg` connection pool instead of single `aiosqlite` connection
- `FOR UPDATE SKIP LOCKED` for job/event leasing
- `$1` parameter syntax instead of `?`
- Real concurrent transaction testing

The parametrized fixture runs ALL existing store/service/query/e2e tests on both backends:

```python
@pytest.fixture(params=["sqlite", "postgres"])
async def uow(request, tmp_path):
    if request.param == "sqlite":
        # existing sqlite setup
    else:
        # asyncpg setup against test container
```

CI gate: Postgres tests must pass before PR merge. SQLite tests run on every commit.

---

### Task 26: Local FS Content Store

- Create: `src/hephaestus/forgebase/store/blobs/local_fs.py`
- Test: `tests/test_forgebase/test_store/test_local_fs_content.py` (extend with FS tests)

Content-addressed files at `.hephaestus/forgebase/blobs/`. Staging writes to `staging/` subdirectory, finalize moves to `permanent/` keyed by content hash. Abort removes staged files.

---

## Implementation Notes

- **Remaining SQLite repo tasks (8-14)** each take the Task 7 pattern and apply it to the remaining entities. The key code is the row↔model mapping and the SQL statements, which follow directly from the schema in Task 6.
- **Postgres implementation** (Task 25) runs after the full SQLite path is validated. The schema is identical; the implementation uses asyncpg. The parametrized test fixture exercises both backends for all tests.
- **Local FS content store** (Task 26) follows the same `StagedContentStore` contract as `InMemoryContentStore` but writes to `.hephaestus/forgebase/blobs/staging/` and `.hephaestus/forgebase/blobs/permanent/`.
- **Git mirror** (`projection/git_mirror.py`) is a stub in sub-project 1 — the projection layer gets real implementation in sub-project 2 when the compiler produces markdown pages worth mirroring.
