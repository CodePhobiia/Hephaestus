# ForgeBase Compiler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the two-tier compiler that turns ingested sources into a living knowledge base — with per-source extraction (Tier 1), vault-wide synthesis (Tier 2), claim-level provenance, and concept candidate tracking.

**Architecture:** Two-tier compiler on top of the Foundation Platform (348 tests, fully operational). Tier 1 is event-driven per-source extraction producing source cards, claims, concept candidates, and dirty markers. Tier 2 is manifest-driven vault-wide synthesis producing concept/mechanism/comparison/timeline/open-question pages. CompilerBackend abstraction keeps LLM calls decoupled. All compilation is branch-aware via existing UoW/workbook infrastructure.

**Tech Stack:** Python 3.11+, aiosqlite, anthropic SDK, pytest-asyncio, existing ForgeBase Foundation Platform

**Spec:** `docs/superpowers/specs/2026-04-04-forgebase-compiler-design.md`

---

## File Structure

```
# New files to create:

src/hephaestus/forgebase/
  domain/enums.py                           # MODIFY — add 4 new enums
  domain/values.py                          # MODIFY — add EvidenceSegmentRef
  domain/models.py                          # MODIFY — add 6 new entities + BackendCallRecord

  repository/concept_candidate_repo.py      # CREATE — ABC
  repository/candidate_evidence_repo.py     # CREATE — ABC
  repository/compile_manifest_repo.py       # CREATE — ABC
  repository/dirty_marker_repo.py           # CREATE — ABC
  repository/uow.py                         # MODIFY — add 4 new repo accessors

  store/sqlite/schema.py                    # MODIFY — add new tables
  store/sqlite/concept_candidate_repo.py    # CREATE
  store/sqlite/candidate_evidence_repo.py   # CREATE
  store/sqlite/compile_manifest_repo.py     # CREATE
  store/sqlite/dirty_marker_repo.py         # CREATE
  store/sqlite/uow.py                       # MODIFY — wire new repos

  ingestion/
    __init__.py                             # CREATE
    normalization.py                        # CREATE — NormalizationPipeline
    markdown_normalizer.py                  # CREATE
    html.py                                 # CREATE
    pdf.py                                  # CREATE — stub
    images.py                               # CREATE — stub

  compiler/
    __init__.py                             # CREATE
    backend.py                              # CREATE — CompilerBackend ABC
    models.py                               # CREATE — extraction result schemas
    policy.py                               # CREATE — SynthesisPolicy
    dirty.py                                # CREATE — dirty marker logic
    tier1.py                                # CREATE — SourceCompiler
    tier2.py                                # CREATE — VaultSynthesizer
    prompts/
      __init__.py                           # CREATE
      claim_extraction.py                   # CREATE
      concept_extraction.py                 # CREATE
      source_card.py                        # CREATE
      evidence_grading.py                   # CREATE
      synthesis.py                          # CREATE
    backends/
      __init__.py                           # CREATE
      anthropic_backend.py                  # CREATE

  research/
    __init__.py                             # CREATE
    augmentor.py                            # CREATE — ResearchAugmentor ABC
    perplexity_augmentor.py                 # CREATE

  factory.py                                # MODIFY — wire compiler components

tests/test_forgebase/
  test_domain/test_values.py                # MODIFY — add EvidenceSegmentRef tests
  test_domain/test_models.py                # MODIFY — add new entity tests
  test_store/test_sqlite_candidate_repo.py  # CREATE
  test_store/test_sqlite_manifest_repo.py   # CREATE
  test_store/test_sqlite_dirty_repo.py      # CREATE
  test_ingestion/
    __init__.py                             # CREATE
    test_normalization.py                   # CREATE
    test_markdown_normalizer.py             # CREATE
    test_html_normalizer.py                 # CREATE
  test_compiler/
    __init__.py                             # CREATE
    conftest.py                             # CREATE — mock backend fixture
    test_models.py                          # CREATE
    test_backend_contract.py                # CREATE
    test_policy.py                          # CREATE
    test_dirty.py                           # CREATE
    test_tier1.py                           # CREATE
    test_tier2.py                           # CREATE
    test_prompts.py                         # CREATE
    test_anthropic_backend.py               # CREATE
  test_research/
    __init__.py                             # CREATE
    test_augmentor.py                       # CREATE
  test_e2e/
    test_compiler_lifecycle.py              # CREATE
```

---

### Task 1: Domain Extensions — Enums, Value Objects, Entities

**Files:**
- Modify: `src/hephaestus/forgebase/domain/enums.py`
- Modify: `src/hephaestus/forgebase/domain/values.py`
- Modify: `src/hephaestus/forgebase/domain/models.py`
- Modify: `tests/test_forgebase/test_domain/test_values.py`
- Modify: `tests/test_forgebase/test_domain/test_models.py`

- [ ] **Step 1: Write failing tests for new enums and EvidenceSegmentRef**

```python
# Append to tests/test_forgebase/test_domain/test_values.py

from hephaestus.forgebase.domain.values import EvidenceSegmentRef
from hephaestus.forgebase.domain.enums import (
    CandidateKind, CandidateStatus, DirtyTargetKind, CompilePhase,
)


class TestEvidenceSegmentRef:
    def test_create(self):
        ref = EvidenceSegmentRef(
            source_id=EntityId("source_01HXYZ12345678901234ABCDEF"),
            source_version=Version(1),
            segment_start=100,
            segment_end=350,
            section_key="3.2",
            preview_text="The SEI layer forms during initial cycling...",
        )
        assert ref.segment_start == 100
        assert ref.segment_end == 350
        assert ref.section_key == "3.2"

    def test_length(self):
        ref = EvidenceSegmentRef(
            source_id=EntityId("source_01HXYZ12345678901234ABCDEF"),
            source_version=Version(1),
            segment_start=0,
            segment_end=200,
            section_key=None,
            preview_text="Preview",
        )
        assert ref.length == 200


class TestNewEnums:
    def test_candidate_kind_values(self):
        assert CandidateKind.CONCEPT == "concept"
        assert CandidateKind.ENTITY == "entity"
        assert CandidateKind.MECHANISM == "mechanism"
        assert CandidateKind.TERM == "term"

    def test_candidate_status_values(self):
        assert CandidateStatus.ACTIVE == "active"
        assert CandidateStatus.SUPERSEDED == "superseded"
        assert CandidateStatus.PROMOTED == "promoted"

    def test_dirty_target_kind_values(self):
        assert DirtyTargetKind.CONCEPT == "concept"
        assert DirtyTargetKind.SOURCE_INDEX == "source_index"

    def test_compile_phase_values(self):
        assert CompilePhase.TIER1_EXTRACTION == "tier1_extraction"
        assert CompilePhase.TIER2_SYNTHESIZE == "tier2_synthesize"
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest tests/test_forgebase/test_domain/test_values.py -v -k "TestEvidenceSegmentRef or TestNewEnums"`
Expected: FAIL — imports not found

- [ ] **Step 3: Add new enums to domain/enums.py**

Append to `src/hephaestus/forgebase/domain/enums.py`:

```python
class CandidateKind(str, Enum):
    CONCEPT = "concept"
    ENTITY = "entity"
    MECHANISM = "mechanism"
    TERM = "term"


class CandidateStatus(str, Enum):
    ACTIVE = "active"
    CLUSTERED = "clustered"
    PROMOTED = "promoted"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class DirtyTargetKind(str, Enum):
    CONCEPT = "concept"
    MECHANISM = "mechanism"
    COMPARISON = "comparison"
    TIMELINE = "timeline"
    OPEN_QUESTION = "open_question"
    SOURCE_INDEX = "source_index"


class CompilePhase(str, Enum):
    TIER1_EXTRACTION = "tier1_extraction"
    TIER1_PERSIST = "tier1_persist"
    TIER2_CLUSTER = "tier2_cluster"
    TIER2_SYNTHESIZE = "tier2_synthesize"
    TIER2_GRAPH = "tier2_graph"
```

- [ ] **Step 4: Add EvidenceSegmentRef to domain/values.py**

Append to `src/hephaestus/forgebase/domain/values.py`:

```python
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
```

- [ ] **Step 5: Write failing tests for new domain models**

Append to `tests/test_forgebase/test_domain/test_models.py`:

```python
from hephaestus.forgebase.domain.enums import (
    CandidateKind, CandidateStatus, DirtyTargetKind,
)
from hephaestus.forgebase.domain.models import (
    BackendCallRecord,
    ConceptCandidate,
    ConceptCandidateEvidence,
    SourceCompileManifest,
    SynthesisDirtyMarker,
    VaultSynthesisManifest,
)
from hephaestus.forgebase.domain.values import EvidenceSegmentRef


class TestBackendCallRecord:
    def test_create(self):
        rec = BackendCallRecord(
            model_name="claude-sonnet-4-5",
            backend_kind="anthropic",
            prompt_id="claim_extraction",
            prompt_version="1.0.0",
            schema_version=1,
            repair_invoked=False,
            input_tokens=500,
            output_tokens=200,
            duration_ms=1200,
            raw_output_ref=None,
        )
        assert rec.model_name == "claude-sonnet-4-5"
        assert not rec.repair_invoked


class TestConceptCandidate:
    def test_create(self):
        cc = ConceptCandidate(
            candidate_id=_eid("cand"),
            vault_id=_eid("vault"),
            workbook_id=None,
            source_id=_eid("source"),
            source_version=Version(1),
            source_compile_job_id=_eid("job"),
            name="Solid Electrolyte Interphase",
            normalized_name="solid electrolyte interphase",
            aliases=["SEI", "SEI layer"],
            candidate_kind=CandidateKind.MECHANISM,
            confidence=0.92,
            salience=0.85,
            status=CandidateStatus.ACTIVE,
            resolved_page_id=None,
            compiler_policy_version="1.0.0",
            created_at=_now(),
        )
        assert cc.status == CandidateStatus.ACTIVE
        assert cc.normalized_name == "solid electrolyte interphase"


class TestConceptCandidateEvidence:
    def test_create(self):
        ev = ConceptCandidateEvidence(
            evidence_id=_eid("cevd"),
            candidate_id=_eid("cand"),
            segment_ref=EvidenceSegmentRef(
                source_id=_eid("source"),
                source_version=Version(1),
                segment_start=100,
                segment_end=300,
                section_key="3.2",
                preview_text="The SEI layer...",
            ),
            role="DEFINITION",
            created_at=_now(),
        )
        assert ev.role == "DEFINITION"
        assert ev.segment_ref.segment_start == 100


class TestSynthesisDirtyMarker:
    def test_create(self):
        dm = SynthesisDirtyMarker(
            marker_id=_eid("dirty"),
            vault_id=_eid("vault"),
            workbook_id=None,
            target_kind=DirtyTargetKind.CONCEPT,
            target_key="solid electrolyte interphase",
            first_dirtied_at=_now(),
            last_dirtied_at=_now(),
            times_dirtied=1,
            last_dirtied_by_source=_eid("source"),
            last_dirtied_by_job=_eid("job"),
            consumed_by_job=None,
            consumed_at=None,
        )
        assert dm.times_dirtied == 1
        assert dm.consumed_by_job is None


class TestSourceCompileManifest:
    def test_create(self):
        m = SourceCompileManifest(
            manifest_id=_eid("mfst"),
            vault_id=_eid("vault"),
            workbook_id=None,
            source_id=_eid("source"),
            source_version=Version(1),
            job_id=_eid("job"),
            compiler_policy_version="1.0.0",
            prompt_versions={"claim_extraction": "1.0.0", "concept_extraction": "1.0.0"},
            backend_calls=[],
            claim_count=5,
            concept_count=3,
            relationship_count=2,
            source_content_hash=ContentHash(sha256="a" * 64),
            created_at=_now(),
        )
        assert m.claim_count == 5
```

- [ ] **Step 6: Add new models to domain/models.py**

Append to `src/hephaestus/forgebase/domain/models.py`:

```python
from hephaestus.forgebase.domain.enums import (
    CandidateKind,
    CandidateStatus,
    DirtyTargetKind,
)
from hephaestus.forgebase.domain.values import EvidenceSegmentRef

# ---------------------------------------------------------------------------
# Backend call metadata
# ---------------------------------------------------------------------------

@dataclass
class BackendCallRecord:
    model_name: str
    backend_kind: str
    prompt_id: str
    prompt_version: str
    schema_version: int
    repair_invoked: bool
    input_tokens: int
    output_tokens: int
    duration_ms: int
    raw_output_ref: BlobRef | None = None


# ---------------------------------------------------------------------------
# Concept candidates
# ---------------------------------------------------------------------------

@dataclass
class ConceptCandidate:
    candidate_id: EntityId
    vault_id: EntityId
    workbook_id: EntityId | None
    source_id: EntityId
    source_version: Version
    source_compile_job_id: EntityId
    name: str
    normalized_name: str
    aliases: list[str]
    candidate_kind: CandidateKind
    confidence: float
    salience: float
    status: CandidateStatus
    resolved_page_id: EntityId | None
    compiler_policy_version: str
    created_at: datetime


@dataclass
class ConceptCandidateEvidence:
    evidence_id: EntityId
    candidate_id: EntityId
    segment_ref: EvidenceSegmentRef
    role: str
    created_at: datetime


# ---------------------------------------------------------------------------
# Dirty tracking
# ---------------------------------------------------------------------------

@dataclass
class SynthesisDirtyMarker:
    marker_id: EntityId
    vault_id: EntityId
    workbook_id: EntityId | None
    target_kind: DirtyTargetKind
    target_key: str
    first_dirtied_at: datetime
    last_dirtied_at: datetime
    times_dirtied: int
    last_dirtied_by_source: EntityId
    last_dirtied_by_job: EntityId
    consumed_by_job: EntityId | None
    consumed_at: datetime | None


# ---------------------------------------------------------------------------
# Compile manifests
# ---------------------------------------------------------------------------

@dataclass
class SourceCompileManifest:
    manifest_id: EntityId
    vault_id: EntityId
    workbook_id: EntityId | None
    source_id: EntityId
    source_version: Version
    job_id: EntityId
    compiler_policy_version: str
    prompt_versions: dict[str, str]
    backend_calls: list[BackendCallRecord]
    claim_count: int
    concept_count: int
    relationship_count: int
    source_content_hash: ContentHash
    created_at: datetime


@dataclass
class VaultSynthesisManifest:
    manifest_id: EntityId
    vault_id: EntityId
    workbook_id: EntityId | None
    job_id: EntityId
    base_revision: VaultRevisionId
    synthesis_policy_version: str
    prompt_versions: dict[str, str]
    backend_calls: list[BackendCallRecord]
    candidates_resolved: int
    augmentor_calls: int
    created_at: datetime
```

- [ ] **Step 7: Run all domain tests**

Run: `python -m pytest tests/test_forgebase/test_domain/ -v`
Expected: All PASS (existing + new)

- [ ] **Step 8: Commit**

```bash
git add src/hephaestus/forgebase/domain/ tests/test_forgebase/test_domain/
git commit -m "feat(forgebase): add compiler domain extensions — enums, EvidenceSegmentRef, ConceptCandidate, manifests, dirty markers"
```

---

### Task 2: New Repository Contracts

**Files:**
- Create: `src/hephaestus/forgebase/repository/concept_candidate_repo.py`
- Create: `src/hephaestus/forgebase/repository/candidate_evidence_repo.py`
- Create: `src/hephaestus/forgebase/repository/compile_manifest_repo.py`
- Create: `src/hephaestus/forgebase/repository/dirty_marker_repo.py`
- Modify: `src/hephaestus/forgebase/repository/uow.py`

- [ ] **Step 1: Create all 4 repository ABCs**

```python
# src/hephaestus/forgebase/repository/concept_candidate_repo.py
from __future__ import annotations
from abc import ABC, abstractmethod
from hephaestus.forgebase.domain.enums import CandidateKind, CandidateStatus
from hephaestus.forgebase.domain.models import ConceptCandidate
from hephaestus.forgebase.domain.values import EntityId, Version

class ConceptCandidateRepository(ABC):
    @abstractmethod
    async def create(self, candidate: ConceptCandidate) -> None: ...
    @abstractmethod
    async def get(self, candidate_id: EntityId) -> ConceptCandidate | None: ...
    @abstractmethod
    async def list_active(self, vault_id: EntityId, workbook_id: EntityId | None = None) -> list[ConceptCandidate]: ...
    @abstractmethod
    async def list_by_source(self, source_id: EntityId, source_version: Version) -> list[ConceptCandidate]: ...
    @abstractmethod
    async def list_by_normalized_name(self, vault_id: EntityId, normalized_name: str, workbook_id: EntityId | None = None) -> list[ConceptCandidate]: ...
    @abstractmethod
    async def update_status(self, candidate_id: EntityId, status: CandidateStatus, resolved_page_id: EntityId | None = None) -> None: ...
    @abstractmethod
    async def supersede_by_source(self, source_id: EntityId, source_version: Version) -> int:
        """Mark all candidates from a prior compile of this source as SUPERSEDED. Returns count."""
```

```python
# src/hephaestus/forgebase/repository/candidate_evidence_repo.py
from __future__ import annotations
from abc import ABC, abstractmethod
from hephaestus.forgebase.domain.models import ConceptCandidateEvidence
from hephaestus.forgebase.domain.values import EntityId

class CandidateEvidenceRepository(ABC):
    @abstractmethod
    async def create(self, evidence: ConceptCandidateEvidence) -> None: ...
    @abstractmethod
    async def list_by_candidate(self, candidate_id: EntityId) -> list[ConceptCandidateEvidence]: ...
```

```python
# src/hephaestus/forgebase/repository/compile_manifest_repo.py
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
    async def get_source_manifest_for(self, source_id: EntityId, source_version: Version) -> SourceCompileManifest | None: ...
    @abstractmethod
    async def create_vault_manifest(self, manifest: VaultSynthesisManifest) -> None: ...
    @abstractmethod
    async def get_vault_manifest(self, manifest_id: EntityId) -> VaultSynthesisManifest | None: ...
    @abstractmethod
    async def get_latest_vault_manifest(self, vault_id: EntityId, workbook_id: EntityId | None = None) -> VaultSynthesisManifest | None: ...
    # Join table methods for VaultSynthesisManifest associations
    @abstractmethod
    async def add_synthesis_source_manifest(self, synthesis_id: EntityId, source_manifest_id: EntityId) -> None: ...
    @abstractmethod
    async def add_synthesis_page_created(self, synthesis_id: EntityId, page_id: EntityId) -> None: ...
    @abstractmethod
    async def add_synthesis_page_updated(self, synthesis_id: EntityId, page_id: EntityId) -> None: ...
    @abstractmethod
    async def add_synthesis_dirty_consumed(self, synthesis_id: EntityId, marker_id: EntityId) -> None: ...
```

```python
# src/hephaestus/forgebase/repository/dirty_marker_repo.py
from __future__ import annotations
from abc import ABC, abstractmethod
from datetime import datetime
from hephaestus.forgebase.domain.enums import DirtyTargetKind
from hephaestus.forgebase.domain.models import SynthesisDirtyMarker
from hephaestus.forgebase.domain.values import EntityId

class DirtyMarkerRepository(ABC):
    @abstractmethod
    async def upsert(self, marker: SynthesisDirtyMarker) -> None:
        """Insert or update. Preserves first_dirtied_at, increments times_dirtied."""
    @abstractmethod
    async def get(self, marker_id: EntityId) -> SynthesisDirtyMarker | None: ...
    @abstractmethod
    async def list_unconsumed(self, vault_id: EntityId, workbook_id: EntityId | None = None) -> list[SynthesisDirtyMarker]: ...
    @abstractmethod
    async def count_unconsumed(self, vault_id: EntityId, workbook_id: EntityId | None = None) -> int: ...
    @abstractmethod
    async def find_by_target(self, vault_id: EntityId, target_kind: DirtyTargetKind, target_key: str, workbook_id: EntityId | None = None) -> SynthesisDirtyMarker | None: ...
    @abstractmethod
    async def consume(self, marker_id: EntityId, consumed_by_job: EntityId) -> None:
        """Mark a dirty marker as consumed by a synthesis job."""
```

- [ ] **Step 2: Add new repo accessors to AbstractUnitOfWork**

Add to `src/hephaestus/forgebase/repository/uow.py` — import the 4 new repos and add attributes:

```python
from hephaestus.forgebase.repository.concept_candidate_repo import ConceptCandidateRepository
from hephaestus.forgebase.repository.candidate_evidence_repo import CandidateEvidenceRepository
from hephaestus.forgebase.repository.compile_manifest_repo import CompileManifestRepository
from hephaestus.forgebase.repository.dirty_marker_repo import DirtyMarkerRepository

# Inside AbstractUnitOfWork class, add:
    concept_candidates: ConceptCandidateRepository
    candidate_evidence: CandidateEvidenceRepository
    compile_manifests: CompileManifestRepository
    dirty_markers: DirtyMarkerRepository
```

- [ ] **Step 3: Verify imports resolve**

Run: `python -c "from hephaestus.forgebase.repository.uow import AbstractUnitOfWork; print('OK')"`
Expected: OK

- [ ] **Step 4: Commit**

```bash
git add src/hephaestus/forgebase/repository/
git commit -m "feat(forgebase): add compiler repository contracts — candidates, evidence, manifests, dirty markers"
```

---

### Task 3: SQLite Schema Extensions + New Repo Implementations

**Files:**
- Modify: `src/hephaestus/forgebase/store/sqlite/schema.py`
- Create: `src/hephaestus/forgebase/store/sqlite/concept_candidate_repo.py`
- Create: `src/hephaestus/forgebase/store/sqlite/candidate_evidence_repo.py`
- Create: `src/hephaestus/forgebase/store/sqlite/compile_manifest_repo.py`
- Create: `src/hephaestus/forgebase/store/sqlite/dirty_marker_repo.py`
- Modify: `src/hephaestus/forgebase/store/sqlite/uow.py`
- Test: `tests/test_forgebase/test_store/test_sqlite_candidate_repo.py`
- Test: `tests/test_forgebase/test_store/test_sqlite_manifest_repo.py`
- Test: `tests/test_forgebase/test_store/test_sqlite_dirty_repo.py`

- [ ] **Step 1: Add new tables to schema.py**

Append to the `SCHEMA_SQL` string in `src/hephaestus/forgebase/store/sqlite/schema.py`:

```sql
-- Concept candidates
CREATE TABLE IF NOT EXISTS fb_concept_candidates (
    candidate_id TEXT PRIMARY KEY,
    vault_id TEXT NOT NULL,
    workbook_id TEXT,
    source_id TEXT NOT NULL,
    source_version INTEGER NOT NULL,
    source_compile_job_id TEXT NOT NULL,
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    aliases TEXT NOT NULL DEFAULT '[]',
    candidate_kind TEXT NOT NULL,
    confidence REAL NOT NULL,
    salience REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    resolved_page_id TEXT,
    compiler_policy_version TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fb_candidates_vault ON fb_concept_candidates (vault_id, status);
CREATE INDEX IF NOT EXISTS idx_fb_candidates_source ON fb_concept_candidates (source_id, source_version);
CREATE INDEX IF NOT EXISTS idx_fb_candidates_name ON fb_concept_candidates (vault_id, normalized_name);

-- Concept candidate evidence
CREATE TABLE IF NOT EXISTS fb_candidate_evidence (
    evidence_id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    seg_source_id TEXT NOT NULL,
    seg_source_version INTEGER NOT NULL,
    seg_start INTEGER NOT NULL,
    seg_end INTEGER NOT NULL,
    seg_section_key TEXT,
    seg_preview_text TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fb_cand_evidence ON fb_candidate_evidence (candidate_id);

-- Source compile manifests
CREATE TABLE IF NOT EXISTS fb_source_compile_manifests (
    manifest_id TEXT PRIMARY KEY,
    vault_id TEXT NOT NULL,
    workbook_id TEXT,
    source_id TEXT NOT NULL,
    source_version INTEGER NOT NULL,
    job_id TEXT NOT NULL,
    compiler_policy_version TEXT NOT NULL,
    prompt_versions TEXT NOT NULL DEFAULT '{}',
    backend_calls TEXT NOT NULL DEFAULT '[]',
    claim_count INTEGER NOT NULL DEFAULT 0,
    concept_count INTEGER NOT NULL DEFAULT 0,
    relationship_count INTEGER NOT NULL DEFAULT 0,
    source_content_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fb_src_manifest ON fb_source_compile_manifests (source_id, source_version);

-- Vault synthesis manifests
CREATE TABLE IF NOT EXISTS fb_vault_synthesis_manifests (
    manifest_id TEXT PRIMARY KEY,
    vault_id TEXT NOT NULL,
    workbook_id TEXT,
    job_id TEXT NOT NULL,
    base_revision TEXT NOT NULL,
    synthesis_policy_version TEXT NOT NULL,
    prompt_versions TEXT NOT NULL DEFAULT '{}',
    backend_calls TEXT NOT NULL DEFAULT '[]',
    candidates_resolved INTEGER NOT NULL DEFAULT 0,
    augmentor_calls INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

-- Synthesis manifest join tables
CREATE TABLE IF NOT EXISTS fb_synthesis_source_manifests (
    synthesis_manifest_id TEXT NOT NULL,
    source_manifest_id TEXT NOT NULL,
    PRIMARY KEY (synthesis_manifest_id, source_manifest_id)
);
CREATE TABLE IF NOT EXISTS fb_synthesis_pages_created (
    synthesis_manifest_id TEXT NOT NULL,
    page_id TEXT NOT NULL,
    PRIMARY KEY (synthesis_manifest_id, page_id)
);
CREATE TABLE IF NOT EXISTS fb_synthesis_pages_updated (
    synthesis_manifest_id TEXT NOT NULL,
    page_id TEXT NOT NULL,
    PRIMARY KEY (synthesis_manifest_id, page_id)
);
CREATE TABLE IF NOT EXISTS fb_synthesis_dirty_consumed (
    synthesis_manifest_id TEXT NOT NULL,
    marker_id TEXT NOT NULL,
    PRIMARY KEY (synthesis_manifest_id, marker_id)
);

-- Synthesis dirty markers (upsert target)
CREATE TABLE IF NOT EXISTS fb_synthesis_dirty_markers (
    marker_id TEXT PRIMARY KEY,
    vault_id TEXT NOT NULL,
    workbook_id TEXT,
    target_kind TEXT NOT NULL,
    target_key TEXT NOT NULL,
    first_dirtied_at TEXT NOT NULL,
    last_dirtied_at TEXT NOT NULL,
    times_dirtied INTEGER NOT NULL DEFAULT 1,
    last_dirtied_by_source TEXT NOT NULL,
    last_dirtied_by_job TEXT NOT NULL,
    consumed_by_job TEXT,
    consumed_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_fb_dirty_unique ON fb_synthesis_dirty_markers (vault_id, COALESCE(workbook_id, ''), target_kind, target_key);
CREATE INDEX IF NOT EXISTS idx_fb_dirty_unconsumed ON fb_synthesis_dirty_markers (vault_id, consumed_by_job) WHERE consumed_by_job IS NULL;
```

- [ ] **Step 2: Write tests for candidate repo, manifest repo, dirty marker repo**

Follow the established test pattern from existing `test_sqlite_*_repo.py` files. Write 3 test files covering:
- **test_sqlite_candidate_repo.py**: create+get, list_active, list_by_source, list_by_normalized_name, update_status, supersede_by_source
- **test_sqlite_manifest_repo.py**: create+get source manifest, create+get vault manifest, get_latest, join table associations
- **test_sqlite_dirty_repo.py**: upsert (new marker), upsert (existing — times_dirtied increments, first_dirtied_at preserved), list_unconsumed, count_unconsumed, find_by_target, consume

- [ ] **Step 3: Implement all 4 SQLite repos**

Follow the established vault_repo.py pattern: constructor takes `aiosqlite.Connection`, static `_row_to_*` methods, EntityId/enum/datetime mapping. The dirty marker repo's `upsert` uses SQLite `INSERT OR REPLACE` with careful handling of `first_dirtied_at` preservation (read first, or use a subquery).

- [ ] **Step 4: Wire into SqliteUnitOfWork**

Add imports and wiring in `store/sqlite/uow.py` for all 4 new repos.

- [ ] **Step 5: Run all tests**

Run: `python -m pytest tests/test_forgebase/ -v`
Expected: All PASS (348 existing + new)

- [ ] **Step 6: Commit**

```bash
git add src/hephaestus/forgebase/store/ tests/test_forgebase/test_store/
git commit -m "feat(forgebase): add SQLite repos for candidates, manifests, dirty markers with schema"
```

---

### Task 4: Compiler Models + CompilerBackend ABC

**Files:**
- Create: `src/hephaestus/forgebase/compiler/__init__.py`
- Create: `src/hephaestus/forgebase/compiler/models.py`
- Create: `src/hephaestus/forgebase/compiler/backend.py`
- Create: `src/hephaestus/forgebase/compiler/policy.py`
- Test: `tests/test_forgebase/test_compiler/__init__.py`
- Test: `tests/test_forgebase/test_compiler/test_models.py`
- Test: `tests/test_forgebase/test_compiler/test_policy.py`

- [ ] **Step 1: Write tests for compiler models**

```python
# tests/test_forgebase/test_compiler/test_models.py
from __future__ import annotations
import pytest
from hephaestus.forgebase.compiler.models import (
    ExtractedClaim, ExtractedConcept, SourceCardContent,
    EvidenceGrade, SynthesizedPage, SynthesizedClaim,
    OpenQuestion, ConceptEvidence,
)
from hephaestus.forgebase.domain.enums import CandidateKind, SupportType
from hephaestus.forgebase.domain.values import EntityId, EvidenceSegmentRef, Version


def _seg() -> EvidenceSegmentRef:
    return EvidenceSegmentRef(
        source_id=EntityId("source_01HXYZ12345678901234ABCDEF"),
        source_version=Version(1),
        segment_start=0, segment_end=100,
        section_key=None, preview_text="Test...",
    )


class TestExtractedClaim:
    def test_create(self):
        c = ExtractedClaim(
            statement="SEI degrades during cycling",
            segment_ref=_seg(),
            confidence=0.9,
            claim_type="factual",
        )
        assert c.statement == "SEI degrades during cycling"


class TestExtractedConcept:
    def test_create(self):
        c = ExtractedConcept(
            name="Solid Electrolyte Interphase",
            aliases=["SEI"],
            kind=CandidateKind.MECHANISM,
            evidence_segments=[_seg()],
            salience=0.85,
        )
        assert c.salience == 0.85


class TestSourceCardContent:
    def test_create(self):
        sc = SourceCardContent(
            summary="Paper on SEI degradation",
            key_claims=["SEI degrades during cycling"],
            methods=["Electrochemical impedance spectroscopy"],
            limitations=["Only tested at room temperature"],
            evidence_quality="strong",
            concepts_mentioned=["SEI", "anode"],
        )
        assert len(sc.key_claims) == 1


class TestSynthesizedPage:
    def test_create(self):
        sp = SynthesizedPage(
            title="Solid Electrolyte Interphase",
            content_markdown="# SEI\n\nThe SEI layer...",
            claims=[SynthesizedClaim(
                statement="SEI is primary degradation mechanism",
                support_type=SupportType.SYNTHESIZED,
                confidence=0.8,
                derived_from_claims=["SEI degrades during cycling"],
            )],
            related_concepts=["anode", "electrolyte"],
        )
        assert len(sp.claims) == 1
```

- [ ] **Step 2: Implement compiler/models.py**

```python
# src/hephaestus/forgebase/compiler/models.py
"""Extraction and synthesis result schemas."""
from __future__ import annotations
from dataclasses import dataclass, field
from hephaestus.forgebase.domain.enums import CandidateKind, SupportType
from hephaestus.forgebase.domain.values import EntityId, EvidenceSegmentRef


@dataclass
class ExtractedClaim:
    statement: str
    segment_ref: EvidenceSegmentRef
    confidence: float
    claim_type: str  # factual, methodological, comparative, limitation


@dataclass
class ExtractedConcept:
    name: str
    aliases: list[str]
    kind: CandidateKind
    evidence_segments: list[EvidenceSegmentRef]
    salience: float


@dataclass
class SourceCardContent:
    summary: str
    key_claims: list[str]
    methods: list[str]
    limitations: list[str]
    evidence_quality: str
    concepts_mentioned: list[str]


@dataclass
class EvidenceGrade:
    strength: float
    methodology_quality: str  # strong, moderate, weak, unknown
    reasoning: str


@dataclass
class SynthesizedClaim:
    statement: str
    support_type: SupportType
    confidence: float
    derived_from_claims: list[str]


@dataclass
class SynthesizedPage:
    title: str
    content_markdown: str
    claims: list[SynthesizedClaim] = field(default_factory=list)
    related_concepts: list[str] = field(default_factory=list)


@dataclass
class OpenQuestion:
    question: str
    context: str
    conflicting_claims: list[str] = field(default_factory=list)
    evidence_gap: str = ""


@dataclass
class ConceptEvidence:
    source_id: EntityId
    source_title: str
    claims: list[str]
    segments: list[EvidenceSegmentRef]
```

- [ ] **Step 3: Implement compiler/backend.py (ABC)**

```python
# src/hephaestus/forgebase/compiler/backend.py
"""CompilerBackend ABC — structured extraction interface."""
from __future__ import annotations
from abc import ABC, abstractmethod
from hephaestus.forgebase.compiler.models import (
    ConceptEvidence, EvidenceGrade, ExtractedClaim, ExtractedConcept,
    OpenQuestion, SourceCardContent, SynthesizedPage,
)
from hephaestus.forgebase.domain.models import BackendCallRecord
from hephaestus.forgebase.domain.values import EvidenceSegmentRef


class CompilerBackend(ABC):
    """Structured extraction backend for the ForgeBase compiler."""

    @abstractmethod
    async def extract_claims(
        self, source_text: str, source_metadata: dict,
    ) -> tuple[list[ExtractedClaim], BackendCallRecord]: ...

    @abstractmethod
    async def extract_concepts(
        self, source_text: str, source_metadata: dict,
    ) -> tuple[list[ExtractedConcept], BackendCallRecord]: ...

    @abstractmethod
    async def generate_source_card(
        self, source_text: str, source_metadata: dict,
        extracted_claims: list[ExtractedClaim],
        extracted_concepts: list[ExtractedConcept],
    ) -> tuple[SourceCardContent, BackendCallRecord]: ...

    @abstractmethod
    async def grade_evidence(
        self, claim: str, segment_ref: EvidenceSegmentRef, source_text: str,
    ) -> tuple[EvidenceGrade, BackendCallRecord]: ...

    @abstractmethod
    async def synthesize_concept_page(
        self, concept_name: str, evidence: list[ConceptEvidence],
        existing_claims: list[str], related_concepts: list[str],
        policy: object,
    ) -> tuple[SynthesizedPage, BackendCallRecord]: ...

    @abstractmethod
    async def synthesize_mechanism_page(
        self, mechanism_name: str, causal_claims: list[str],
        source_evidence: list[ConceptEvidence], policy: object,
    ) -> tuple[SynthesizedPage, BackendCallRecord]: ...

    @abstractmethod
    async def synthesize_comparison_page(
        self, entities: list[str], comparison_data: list[dict],
        policy: object,
    ) -> tuple[SynthesizedPage, BackendCallRecord]: ...

    @abstractmethod
    async def synthesize_timeline_page(
        self, topic: str, temporal_claims: list[str], policy: object,
    ) -> tuple[SynthesizedPage, BackendCallRecord]: ...

    @abstractmethod
    async def identify_open_questions(
        self, contested_claims: list[str], evidence_gaps: list[str],
        policy: object,
    ) -> tuple[list[OpenQuestion], BackendCallRecord]: ...
```

- [ ] **Step 4: Implement compiler/policy.py**

```python
# src/hephaestus/forgebase/compiler/policy.py
"""Versioned synthesis policies."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class SynthesisPolicy:
    policy_version: str = "1.0.0"
    name_similarity_threshold: float = 0.85
    min_sources_for_promotion: int = 2
    min_salience_single_source: float = 0.8
    max_claims_per_page: int = 50
    max_related_concepts: int = 20
    dirty_threshold_for_auto_synthesis: int = 5
    debounce_minutes: float = 10.0
    min_evidence_strength_for_supported: float = 0.3


DEFAULT_POLICY = SynthesisPolicy()
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_forgebase/test_compiler/ -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/hephaestus/forgebase/compiler/ tests/test_forgebase/test_compiler/
git commit -m "feat(forgebase): add CompilerBackend ABC, extraction models, and synthesis policy"
```

---

### Task 5: Versioned Prompts

**Files:**
- Create: `src/hephaestus/forgebase/compiler/prompts/__init__.py`
- Create: `src/hephaestus/forgebase/compiler/prompts/claim_extraction.py`
- Create: `src/hephaestus/forgebase/compiler/prompts/concept_extraction.py`
- Create: `src/hephaestus/forgebase/compiler/prompts/source_card.py`
- Create: `src/hephaestus/forgebase/compiler/prompts/evidence_grading.py`
- Create: `src/hephaestus/forgebase/compiler/prompts/synthesis.py`
- Test: `tests/test_forgebase/test_compiler/test_prompts.py`

Each prompt module exports `PROMPT_ID`, `PROMPT_VERSION`, `SCHEMA_VERSION`, `SYSTEM_PROMPT`, `USER_PROMPT_TEMPLATE`, and `OUTPUT_SCHEMA`. Tests verify all modules export required fields and schemas are valid JSON Schema.

This task creates the actual prompt text for each extraction/synthesis operation with JSON output schemas that the backend enforces. The prompts are the core intellectual property of the compiler — they define what gets extracted and how.

- [ ] **Step 1-6: Write prompts, tests, commit**

Follow the pattern in the spec: each module exports versioned metadata + prompt text + JSON schema. Tests verify structural correctness (all required exports present, schemas valid).

```bash
git commit -m "feat(forgebase): add versioned compiler prompts for extraction and synthesis"
```

---

### Task 6: Normalization Pipeline

**Files:**
- Create: `src/hephaestus/forgebase/ingestion/__init__.py`
- Create: `src/hephaestus/forgebase/ingestion/normalization.py`
- Create: `src/hephaestus/forgebase/ingestion/markdown_normalizer.py`
- Create: `src/hephaestus/forgebase/ingestion/html.py`
- Create: `src/hephaestus/forgebase/ingestion/pdf.py`
- Create: `src/hephaestus/forgebase/ingestion/images.py`
- Test: `tests/test_forgebase/test_ingestion/__init__.py`
- Test: `tests/test_forgebase/test_ingestion/test_normalization.py`
- Test: `tests/test_forgebase/test_ingestion/test_markdown_normalizer.py`
- Test: `tests/test_forgebase/test_ingestion/test_html_normalizer.py`

The normalization pipeline dispatches by `SourceFormat` and produces clean markdown bytes. Markdown normalizer handles cleanup/section splitting. HTML normalizer strips tags (extends patterns from existing `research/ingestion.py`). PDF and images are stubs.

- [ ] **Step 1-6: Write normalizers, tests, commit**

```bash
git commit -m "feat(forgebase): add source normalization pipeline — markdown, HTML, PDF stub, images stub"
```

---

### Task 7: Mock CompilerBackend + Test Fixtures

**Files:**
- Create: `tests/test_forgebase/test_compiler/conftest.py`

A `MockCompilerBackend` that returns deterministic extraction results for testing Tier 1 and Tier 2 without real LLM calls. This is critical — all compiler orchestration tests use this mock.

```python
# tests/test_forgebase/test_compiler/conftest.py
"""Mock compiler backend for testing."""
from __future__ import annotations
from hephaestus.forgebase.compiler.backend import CompilerBackend
from hephaestus.forgebase.compiler.models import *
from hephaestus.forgebase.domain.models import BackendCallRecord
from hephaestus.forgebase.domain.enums import CandidateKind, SupportType
from hephaestus.forgebase.domain.values import EvidenceSegmentRef, EntityId, Version
import pytest


class MockCompilerBackend(CompilerBackend):
    """Returns deterministic results for testing."""

    def _call_record(self, prompt_id: str) -> BackendCallRecord:
        return BackendCallRecord(
            model_name="mock", backend_kind="mock",
            prompt_id=prompt_id, prompt_version="1.0.0",
            schema_version=1, repair_invoked=False,
            input_tokens=100, output_tokens=50, duration_ms=10,
            raw_output_ref=None,
        )

    async def extract_claims(self, source_text, source_metadata):
        claims = [ExtractedClaim(
            statement=f"Claim from: {source_text[:30]}",
            segment_ref=EvidenceSegmentRef(
                source_id=EntityId(source_metadata.get("source_id", "source_00000000000000000000000001")),
                source_version=Version(source_metadata.get("source_version", 1)),
                segment_start=0, segment_end=min(100, len(source_text)),
                section_key=None, preview_text=source_text[:100],
            ),
            confidence=0.9, claim_type="factual",
        )]
        return claims, self._call_record("claim_extraction")

    async def extract_concepts(self, source_text, source_metadata):
        concepts = [ExtractedConcept(
            name="Test Concept",
            aliases=["TC"],
            kind=CandidateKind.CONCEPT,
            evidence_segments=[EvidenceSegmentRef(
                source_id=EntityId(source_metadata.get("source_id", "source_00000000000000000000000001")),
                source_version=Version(source_metadata.get("source_version", 1)),
                segment_start=0, segment_end=50,
                section_key=None, preview_text=source_text[:50],
            )],
            salience=0.85,
        )]
        return concepts, self._call_record("concept_extraction")

    async def generate_source_card(self, source_text, source_metadata, extracted_claims, extracted_concepts):
        card = SourceCardContent(
            summary=f"Summary of source with {len(extracted_claims)} claims",
            key_claims=[c.statement for c in extracted_claims],
            methods=["Test method"],
            limitations=["Test limitation"],
            evidence_quality="moderate",
            concepts_mentioned=[c.name for c in extracted_concepts],
        )
        return card, self._call_record("source_card")

    async def grade_evidence(self, claim, segment_ref, source_text):
        return EvidenceGrade(strength=0.8, methodology_quality="moderate", reasoning="Mock"), self._call_record("evidence_grading")

    async def synthesize_concept_page(self, concept_name, evidence, existing_claims, related_concepts, policy):
        page = SynthesizedPage(
            title=concept_name,
            content_markdown=f"# {concept_name}\n\nSynthesized from {len(evidence)} sources.",
            claims=[SynthesizedClaim(
                statement=f"{concept_name} is well-established",
                support_type=SupportType.SYNTHESIZED,
                confidence=0.85,
                derived_from_claims=[c for e in evidence for c in e.claims[:1]],
            )],
            related_concepts=related_concepts[:3],
        )
        return page, self._call_record("synthesis")

    async def synthesize_mechanism_page(self, mechanism_name, causal_claims, source_evidence, policy):
        page = SynthesizedPage(title=mechanism_name, content_markdown=f"# {mechanism_name}\n\nMechanism.")
        return page, self._call_record("synthesis")

    async def synthesize_comparison_page(self, entities, comparison_data, policy):
        page = SynthesizedPage(title=f"Comparison: {', '.join(entities)}", content_markdown="# Comparison")
        return page, self._call_record("synthesis")

    async def synthesize_timeline_page(self, topic, temporal_claims, policy):
        page = SynthesizedPage(title=f"Timeline: {topic}", content_markdown="# Timeline")
        return page, self._call_record("synthesis")

    async def identify_open_questions(self, contested_claims, evidence_gaps, policy):
        questions = [OpenQuestion(
            question="What are the long-term effects?",
            context="Insufficient longitudinal data",
            evidence_gap="No studies > 5 years",
        )]
        return questions, self._call_record("synthesis")


@pytest.fixture
def mock_backend() -> MockCompilerBackend:
    return MockCompilerBackend()
```

- [ ] **Step 1: Create conftest, commit**

```bash
git commit -m "feat(forgebase): add MockCompilerBackend test fixture"
```

---

### Task 8: Dirty Marker Logic

**Files:**
- Create: `src/hephaestus/forgebase/compiler/dirty.py`
- Test: `tests/test_forgebase/test_compiler/test_dirty.py`

Higher-level dirty tracking logic that uses the `DirtyMarkerRepository` with upsert semantics. Provides helpers for Tier 1 (mark dirty) and Tier 2 (consume).

- [ ] **Step 1-4: Write dirty logic + tests, commit**

```bash
git commit -m "feat(forgebase): add dirty marker upsert/consume logic"
```

---

### Task 9: Tier 1 — SourceCompiler

**Files:**
- Create: `src/hephaestus/forgebase/compiler/tier1.py`
- Test: `tests/test_forgebase/test_compiler/test_tier1.py`

The SourceCompiler orchestrates the full Tier 1 flow: read normalized source → extract claims → extract concepts → generate source card → persist everything → mark dirty → write manifest → emit events.

Tests use `MockCompilerBackend` and verify: source card page created, claims created with SUPPORTED status, concept candidates created as ACTIVE, dirty markers upserted, manifest written, events emitted, no-op on re-compile with same content hash.

This is the largest single task in the plan — the SourceCompiler is ~200-300 lines of orchestration. The agent should implement it methodically, one step at a time.

- [ ] **Step 1-6: Write SourceCompiler + tests, commit**

```bash
git commit -m "feat(forgebase): add Tier 1 SourceCompiler — per-source extraction orchestrator"
```

---

### Task 10: Tier 2 — VaultSynthesizer

**Files:**
- Create: `src/hephaestus/forgebase/compiler/tier2.py`
- Test: `tests/test_forgebase/test_compiler/test_tier2.py`

The VaultSynthesizer orchestrates Tier 2: read active candidates → cluster → synthesize concept pages → create synthesized claims with derivations → update links → schedule follow-on research jobs → write manifest → consume dirty markers.

Tests use `MockCompilerBackend` and verify: concept pages created from candidates across multiple sources, candidates promoted, dirty markers consumed, no-op when content unchanged, synthesis manifest written.

- [ ] **Step 1-6: Write VaultSynthesizer + tests, commit**

```bash
git commit -m "feat(forgebase): add Tier 2 VaultSynthesizer — vault-wide synthesis orchestrator"
```

---

### Task 11: Anthropic CompilerBackend

**Files:**
- Create: `src/hephaestus/forgebase/compiler/backends/__init__.py`
- Create: `src/hephaestus/forgebase/compiler/backends/anthropic_backend.py`
- Test: `tests/test_forgebase/test_compiler/test_anthropic_backend.py`

The first real backend implementation. Uses the Anthropic SDK with JSON schema-constrained outputs, low temperature, validate/repair pattern. Tests mock the Anthropic client to verify prompt construction, schema enforcement, and repair flow.

- [ ] **Step 1-6: Write AnthropicCompilerBackend + tests, commit**

```bash
git commit -m "feat(forgebase): add Anthropic compiler backend with JSON schema extraction"
```

---

### Task 12: ResearchAugmentor

**Files:**
- Create: `src/hephaestus/forgebase/research/__init__.py`
- Create: `src/hephaestus/forgebase/research/augmentor.py`
- Create: `src/hephaestus/forgebase/research/perplexity_augmentor.py`
- Test: `tests/test_forgebase/test_research/__init__.py`
- Test: `tests/test_forgebase/test_research/test_augmentor.py`

ResearchAugmentor ABC + PerplexityAugmentor wrapping existing `hephaestus.research.perplexity.PerplexityClient`. Tests mock the Perplexity client.

- [ ] **Step 1-6: Write augmentor + tests, commit**

```bash
git commit -m "feat(forgebase): add ResearchAugmentor ABC and Perplexity implementation"
```

---

### Task 13: Factory Updates + Event Consumer Wiring

**Files:**
- Modify: `src/hephaestus/forgebase/factory.py`
- Modify: `tests/test_forgebase/test_e2e/test_factory.py`

Update the factory to wire: SourceCompiler, VaultSynthesizer, CompilerBackend (default: Anthropic if API key available, else MockCompilerBackend), normalization pipeline, synthesis policy, research augmentor. Register event consumers that schedule Tier 1 jobs on `source.normalized` events.

- [ ] **Step 1-4: Update factory + tests, commit**

```bash
git commit -m "feat(forgebase): wire compiler components into ForgeBase factory"
```

---

### Task 14: End-to-End Compiler Lifecycle Test

**Files:**
- Create: `tests/test_forgebase/test_e2e/test_compiler_lifecycle.py`

Exercises all 7 minimum real flows from the spec:

1. Ingest markdown source → normalize → Tier 1 produces source card + claims + candidates + dirty markers
2. Ingest second source → Tier 1 runs → shared concepts detected via candidates
3. Run Tier 2 → concept pages synthesized from candidates across both sources
4. Verify claim provenance chain: synthesized claim → derivation → source claims → evidence segments
5. Verify dirty markers consumed after synthesis
6. Verify no-op: re-run Tier 2 → no new page versions
7. Compile on workbook branch → all output branch-scoped → merge to canonical

Uses `MockCompilerBackend` and `create_forgebase()` with deterministic fixtures.

- [ ] **Step 1-4: Write e2e test, commit**

```bash
git commit -m "feat(forgebase): add end-to-end compiler lifecycle test"
```

---

## Implementation Notes

- **Tasks 1-3** (domain + repos + schema) are foundation work — can be dispatched to one agent
- **Task 4** (models + backend ABC + policy) is independent of Tasks 1-3 in code but depends on domain types
- **Tasks 5-6** (prompts + normalization) can run in parallel — they have no shared dependencies
- **Task 7** (mock backend) must precede Tasks 9-10 (Tier 1/2) since they use the mock in tests
- **Tasks 9-10** (Tier 1 + Tier 2) are the core — largest tasks, most complex orchestration
- **Task 11** (Anthropic backend) can run in parallel with Tasks 9-10 since it implements the ABC independently
- **Tasks 13-14** (factory + e2e) must come last

**Parallelization opportunities:**
- Tasks 5 + 6 in parallel
- Tasks 9 + 11 in parallel (Tier 1 + Anthropic backend)
- Task 10 after Task 9 (Tier 2 builds on Tier 1 patterns)
