# ForgeBase Foundation Platform — Design Spec

## Overview

ForgeBase is a persistent, LLM-maintained, evidence-grounded knowledge foundry for Hephaestus. It ingests raw sources, compiles them into a living markdown knowledge base, powers research and invention runs from that knowledge base, and continuously folds validated outputs back into it.

This spec covers **Sub-project 1: Foundation Platform** — the storage, domain model, provenance, branching, events, internal APIs, run integration hooks, and testing strategy that form the permanent spine of the entire ForgeBase system.

### Product Thesis

Today Hephaestus is a powerful run-based invention/research system. With ForgeBase, Hephaestus becomes a compounding intelligence system:

- Every source ingested increases future capability
- Every research run improves future research
- Every invention run has more context, more prior art grounding, and better cross-domain synthesis
- Every output becomes a durable asset
- Every domain or customer workspace becomes harder to replace over time

### Build Order

ForgeBase is decomposed into 5 sub-projects, each with its own design → plan → implementation cycle:

1. **Foundation Platform** (this spec) — storage, domain model, provenance, branching, events, internal APIs, run hooks
2. **Ingestion + Compiler + Provenance Realization** — full ingestion pipeline, source cards, concept pages, backlinks, indexes, claim extraction, compile manifests
3. **Linting + Research + Workbook Intelligence** — contradiction/stale/unsupported claim detection, workbook-based research runs, evidence gathering, repair proposals
4. **Genesis / DeepForge / Pantheon Integration** — vault-aware invention, prior-art-aware DeepForge, Pantheon knowledge governance, invention pages and feedback loops
5. **Multi-Agent + Fusion + Full Product Surface** — scout/compiler/librarian/skeptic/reporter agents, cross-vault fusion, full web UI, CLI/API completion

---

## Architectural Decisions (Locked)

### 1. Storage Topology: Local-Default Dual-Backend, Postgres-Authoritative

- SQLite is the default deployment mode for single-user / local CLI installs
- Postgres is the canonical shared / team / production backend
- ForgeBase contracts are designed with Postgres-first semantics from day one
- No core feature is allowed to exist only on Postgres
- Postgres is the reference backend for correctness, concurrency, and release gating

**Metadata / graph / jobs / provenance:** Single logical `ForgeBaseStore` contract with two implementations (`SqliteForgeBaseStore`, `PostgresForgeBaseStore`). One schema, two backends.

**Raw artifacts:** Pluggable blob store. Local content-addressed files under `.hephaestus/forgebase/blobs/` by default. S3 / R2 / GCS / MinIO for production. The DB stores metadata and object references, not giant raw blobs.

**Compiled markdown pages:** DB is authoritative for metadata, graph, lineage, claims, state. Artifact storage is authoritative for page content bytes. Git-backed markdown is the versioned, human-readable workspace / mirror / export / projection layer — not the source of truth for system state.

**Design philosophy:** Postgres-first semantics, SQLite-supported deployment. Design for explicit IDs, version fields, optimistic concurrency, branch-aware writes, append-only artifact versions, durable job records, outbox/event patterns, structured queryable relationships. Avoid relying on SQLite quirks, local file assumptions, single-writer assumptions, or ad hoc path-based identity.

**Dual-backend rules:**
1. All release gates run against Postgres
2. Every core integration test runs on both SQLite and Postgres
3. No feature may be "implemented later for SQLite"
4. No Postgres-only query model in the domain layer
5. Migrations must be disciplined from day one — no hand-waved SQLite schema drift

### 2. Branch/Workbook Model: Snapshot-Anchored Copy-on-Write

- A workbook IS a branch (1:1, no separate WorkbookBranch entity)
- Branch creation pins a base vault revision — no eager copy
- Only modified entities get branch-local versions (copy-on-write)
- Tombstones for deletions, not hard deletes
- Stable entity ID separate from immutable versions (`page_id` + `page_version`)
- Merge produces a new canonical vault revision
- Conflict detection at page / claim / link / source granularity against base-version ancestry
- Diffs are derived (computed from branch overrides vs base), not the primary storage model
- Repository / query layer encapsulates overlay logic — no leaking into compiler, linter, research, Genesis

**Merge semantics:**
1. Compare each branch-local changed entity against the branch's `base_version`
2. Compare that `base_version` to the current canonical head version
3. If canonical has not changed for that entity since branch start → clean merge
4. If canonical changed and the branch also changed the same entity → conflict
5. Successful merge creates new canonical versions, a new vault revision, merge audit record, and per-entity events
6. `execute_merge()` must revalidate that canonical head has not advanced since `propose_merge()` — stale proposals are rejected

**Canonical deletion semantics:**
- Branch deletions use tombstones
- When a tombstone merges to canonical, the entity is marked ARCHIVED, not hard-deleted
- Archived entities remain queryable via explicit `include_archived` flag; default queries exclude them
- All versions remain in the version table permanently
- Claims on archived pages retain their provenance chain
- Links to/from archived entities are marked STALE, not deleted
- Hard deletion is an operator-level admin action only, never triggered by merge or automation
- Same rules for pages, claims, links, and sources

### 3. Event Model: Transactional Outbox with Immutable Domain Events

- Domain events are written in the same transaction as the state changes they describe
- Two-table model: `domain_events` (append-only immutable ledger) + `event_deliveries` (per-consumer mutable delivery state)
- Delivery is at-least-once, consumer processing is idempotent
- Ordering guaranteed per aggregate, not globally
- Events are facts ("source.ingested"), not commands ("run_compiler_now")
- Events trigger creation of durable jobs, not raw agent execution
- Optional post-commit in-memory fanout for low-latency UX — non-authoritative, not relied on for correctness
- No event sourcing — DB state is the source of truth; events are triggers + audit

**Event taxonomy:**

| Family | Event Types |
|--------|-------------|
| Source | `source.ingested`, `source.normalization_requested`, `source.normalized`, `source.ingest_failed` |
| Compilation | `compile.requested`, `page.version_created`, `claim.version_created`, `link.version_created`, `compile.completed`, `compile.failed` |
| Provenance | `claim.support_added`, `claim.support_removed`, `claim.status_changed`, `claim.invalidated`, `claim.freshness_changed` |
| Workbook | `workbook.created`, `workbook.updated`, `merge.proposed`, `merge.conflict_detected`, `workbook.merged`, `workbook.abandoned` |
| Lint | `lint.requested`, `lint.finding_opened`, `lint.finding_resolved`, `lint.completed` |
| Run / Integration | `artifact.attached`, `research.output_committed`, `invention.output_committed`, `pantheon.verdict_recorded` |

**Dispatcher behavior:**
- SQLite local: single embedded dispatcher thread, small batch polling, simple lease/update
- Postgres production: multiple dispatcher workers, lease rows with `FOR UPDATE SKIP LOCKED`, backpressure and retry control
- Subscriber failure does not roll back original state change — event remains pending/retryable, poison events go to dead-letter

---

## Module Organization

```
src/hephaestus/forgebase/
  domain/                     # Pure models, zero I/O, zero imports
    models.py                 # Vault, Source, Page, Claim, Link, Workbook...
    values.py                 # EntityId types, Version, VaultRevisionId, ActorRef, BlobRef, ContentHash
    event_types.py            # Domain event schemas & taxonomy
    enums.py                  # ClaimStatus, PageType, JobStatus, SourceTrustTier...
    merge.py                  # Merge rules, version reconciliation logic
    conflicts.py              # Conflict detection predicates

  repository/                 # Abstract contracts (ABCs), imports only domain/
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
    content_store.py          # Abstract blob/artifact content contract (staged)
    uow.py                    # UnitOfWork: repos + outbox + commit/rollback

  store/                      # Concrete implementations
    sqlite/                   # aiosqlite UoW + repos + content
    postgres/                 # asyncpg UoW + repos + content
    blobs/                    # local FS / S3 content store implementations
    migrations/               # Schema migrations (both backends)

  service/                    # Business logic (commands only), imports domain/ + repository/
    vault_service.py
    ingest_service.py
    page_service.py
    claim_service.py
    link_service.py
    branch_service.py
    merge_service.py
    compile_service.py        # Stub — real logic in sub-project 2
    lint_service.py           # Stub — real logic in sub-project 3
    run_integration_service.py
    id_generator.py           # Injectable ULID generation policy

  events/                     # Delivery infrastructure, wired by factory
    dispatcher.py             # Background outbox poller/deliverer
    consumers.py              # Durable consumer registry
    fanout.py                 # Optional post-commit in-memory fanout

  query/                      # Read-model logic, imports domain/ + repository/
    vault_queries.py
    source_queries.py
    page_queries.py
    claim_queries.py
    link_queries.py
    branch_queries.py         # Branch-state read-through (COW overlay), diff projection

  projection/                 # External materialized projections (side-effecting)
    git_mirror.py             # Git workspace projection

  integration/                # Bridge for upstream Hephaestus systems
    bridge.py                 # ForgeBaseIntegrationBridge interface
    genesis_adapter.py        # Genesis -> ForgeBase translation
    pantheon_adapter.py       # Pantheon -> ForgeBase translation
    research_adapter.py       # Perplexity/Research -> ForgeBase translation

  factory.py                  # Sole composition root: config -> wired ForgeBase instance
```

### Layer Dependency Rules

| Layer | May Import | Key Constraint |
|-------|-----------|----------------|
| `domain/` | nothing | Pure Python. Zero I/O. |
| `repository/` | `domain/` | Abstract contracts only. |
| `store/` | `domain/`, `repository/` | Implements, never leaks backend specifics. |
| `service/` | `domain/`, `repository/` | Owns transactions via UoW. No concrete events/ import. |
| `events/` | `domain/`, `repository/` | Wired by factory, not by service. |
| `query/` | `domain/`, `repository/` | Read-only. Encapsulates branch COW read-through. |
| `projection/` | `domain/`, `repository/` | External side-effects only (Git mirror). |
| `integration/` | `domain/`, `service/` | Bridge interface + adapters for upstream systems. |
| `factory.py` | everything | Sole composition root. |

---

## Core Domain Model

### Value Objects (`domain/values.py`)

| Type | Description |
|------|-------------|
| `EntityId` | Prefixed ULID wrapper (`vault_01HXK3...`, `page_01HXK4...`). Type + parse + validate in domain; generation is injectable via `IdGenerator`. |
| `Version` | Monotonic integer per entity (1, 2, 3...). |
| `VaultRevisionId` | Prefixed ULID identifying a point-in-time canonical vault snapshot. |
| `ContentHash` | SHA-256 of artifact/page content bytes. |
| `BlobRef` | Opaque reference to content in blob store (hash + size + mime). |
| `PendingContentRef` | Staged blob ref that resolves to `BlobRef` + `ContentHash` after finalization. |
| `ActorRef` | `{ actor_type: ActorType, actor_id: str }`. Replaces all loose actor pairs. |

### Enumerations (`domain/enums.py`)

| Enum | Values |
|------|--------|
| `PageType` | CONCEPT, PROBLEM, MECHANISM, COMPARISON, TIMELINE, OPEN_QUESTION, EXPERIMENT, INVENTION, SOURCE_INDEX, SOURCE_CARD |
| `ClaimStatus` | SUPPORTED, INFERRED, HYPOTHESIS, CONTESTED, STALE |
| `SupportType` | DIRECT, SYNTHESIZED, GENERATED, INHERITED |
| `LinkKind` | BACKLINK, RELATED_CONCEPT, PAGE_TO_PAGE, SUPERSEDES |
| `SourceFormat` | PDF, URL, MARKDOWN, GITHUB_REPO, CSV, JSON, SLIDE_DECK, IMAGE, TRANSCRIPT, HEPH_OUTPUT |
| `SourceTrustTier` | AUTHORITATIVE, STANDARD, LOW, UNTRUSTED |
| `SourceStatus` | INGESTED, NORMALIZED, FAILED |
| `WorkbookStatus` | OPEN, MERGED, ABANDONED, CONFLICTED |
| `BranchPurpose` | RESEARCH, LINT_REPAIR, INVENTION, COMPILATION, MANUAL |
| `JobStatus` | PENDING, RUNNING, COMPLETED, FAILED, CANCELLED |
| `JobKind` | COMPILE, LINT, NORMALIZE, REINDEX, MERGE_FOLLOWUP |
| `FindingSeverity` | CRITICAL, WARNING, INFO |
| `FindingCategory` | DUPLICATE_PAGE, WEAK_BACKLINK, UNSUPPORTED_CLAIM, CONTRADICTORY_CLAIM, STALE_PAGE, ORPHANED_PAGE, MISSING_CANONICAL, UNRESOLVED_TODO, SOURCE_GAP, MISSING_FIGURE_EXPLANATION, RESOLVABLE_BY_SEARCH |
| `FindingStatus` | OPEN, RESOLVED, WAIVED, DEFERRED |
| `MergeVerdict` | CLEAN, CONFLICTED, REQUIRES_REVIEW |
| `MergeResolution` | ACCEPT_BRANCH, ACCEPT_CANONICAL, MANUAL |
| `EntityKind` | PAGE, CLAIM, LINK, SOURCE |
| `ActorType` | SYSTEM, USER, AGENT, RUN |

### Entities (`domain/models.py`)

#### Vault

| Field | Type | Notes |
|-------|------|-------|
| `vault_id` | `EntityId` | |
| `name` | `str` | |
| `description` | `str` | |
| `head_revision_id` | `VaultRevisionId` | Current canonical head |
| `created_at` | `datetime` | |
| `updated_at` | `datetime` | |
| `config` | `dict` | Vault-level settings |

#### VaultRevision

| Field | Type | Notes |
|-------|------|-------|
| `revision_id` | `VaultRevisionId` | |
| `vault_id` | `EntityId` | |
| `parent_revision_id` | `VaultRevisionId \| None` | Previous revision |
| `created_at` | `datetime` | |
| `created_by` | `ActorRef` | |
| `causation_event_id` | `EntityId \| None` | What caused this revision |
| `summary` | `str` | Human-readable description |

#### Source + SourceVersion

| Field | Type | Notes |
|-------|------|-------|
| **Source** | | |
| `source_id` | `EntityId` | |
| `vault_id` | `EntityId` | |
| `format` | `SourceFormat` | |
| `origin_locator` | `str \| None` | Original URL/path |
| `created_at` | `datetime` | |
| **SourceVersion** | | |
| `source_id` | `EntityId` | |
| `version` | `Version` | |
| `title` | `str` | |
| `authors` | `list[str]` | |
| `url` | `str \| None` | |
| `raw_artifact_ref` | `BlobRef` | Immutable raw content |
| `normalized_ref` | `BlobRef \| None` | Normalized markdown/text |
| `content_hash` | `ContentHash` | |
| `metadata` | `dict` | License, timestamp, custom |
| `trust_tier` | `SourceTrustTier` | |
| `status` | `SourceStatus` | |
| `created_at` | `datetime` | |
| `created_by` | `ActorRef` | |

#### Page + PageVersion

| Field | Type | Notes |
|-------|------|-------|
| **Page** | | |
| `page_id` | `EntityId` | |
| `vault_id` | `EntityId` | |
| `page_type` | `PageType` | |
| `page_key` | `str` | Stable slug for paths/backlinks |
| `created_at` | `datetime` | |
| `created_by_run` | `EntityId \| None` | |
| **PageVersion** | | |
| `page_id` | `EntityId` | |
| `version` | `Version` | |
| `title` | `str` | Display title (versioned) |
| `content_ref` | `BlobRef` | Markdown content in blob store |
| `content_hash` | `ContentHash` | |
| `summary` | `str` | Short description of this version |
| `compiled_from` | `list[EntityId]` | Source IDs that contributed |
| `created_at` | `datetime` | |
| `created_by` | `ActorRef` | |
| `schema_version` | `int` | For forward compatibility |

#### Claim + ClaimVersion

| Field | Type | Notes |
|-------|------|-------|
| **Claim** | | |
| `claim_id` | `EntityId` | |
| `vault_id` | `EntityId` | |
| `page_id` | `EntityId` | Which page this claim lives on |
| `created_at` | `datetime` | |
| **ClaimVersion** | | |
| `claim_id` | `EntityId` | |
| `version` | `Version` | |
| `statement` | `str` | The actual assertion text |
| `status` | `ClaimStatus` | |
| `support_type` | `SupportType` | |
| `confidence` | `float` | 0.0 - 1.0 |
| `validated_at` | `datetime` | When evidence was last validated |
| `fresh_until` | `datetime \| None` | Expiry policy |
| `created_at` | `datetime` | |
| `created_by` | `ActorRef` | |

#### ClaimSupport (claim ← source evidence)

| Field | Type | Notes |
|-------|------|-------|
| `support_id` | `EntityId` | |
| `claim_id` | `EntityId` | |
| `source_id` | `EntityId` | |
| `source_segment` | `str \| None` | Specific passage/section |
| `strength` | `float` | How strongly this supports |
| `created_at` | `datetime` | |
| `created_by` | `ActorRef` | |

#### ClaimDerivation (claim ← parent claims)

| Field | Type | Notes |
|-------|------|-------|
| `derivation_id` | `EntityId` | |
| `claim_id` | `EntityId` | |
| `parent_claim_id` | `EntityId` | |
| `relationship` | `str` | SYNTHESIZED_FROM, INFERRED_FROM, REFINED_FROM |
| `created_at` | `datetime` | |
| `created_by` | `ActorRef` | |

#### Link + LinkVersion

| Field | Type | Notes |
|-------|------|-------|
| **Link** | | |
| `link_id` | `EntityId` | |
| `vault_id` | `EntityId` | |
| `kind` | `LinkKind` | |
| `created_at` | `datetime` | |
| **LinkVersion** | | |
| `link_id` | `EntityId` | |
| `version` | `Version` | |
| `source_entity` | `EntityId` | From (page, claim, or source) |
| `target_entity` | `EntityId` | To (page, claim, or source) |
| `label` | `str \| None` | Optional relationship label |
| `weight` | `float` | Strength/relevance |
| `created_at` | `datetime` | |
| `created_by` | `ActorRef` | |

#### Workbook

| Field | Type | Notes |
|-------|------|-------|
| `workbook_id` | `EntityId` | Workbook IS the branch (1:1) |
| `vault_id` | `EntityId` | |
| `name` | `str` | |
| `purpose` | `BranchPurpose` | |
| `status` | `WorkbookStatus` | |
| `base_revision_id` | `VaultRevisionId` | Pinned canonical snapshot |
| `created_at` | `datetime` | |
| `created_by` | `ActorRef` | |
| `created_by_run` | `EntityId \| None` | |

#### Branch Head Tables

| Entity | Fields |
|--------|--------|
| `BranchPageHead` | `workbook_id`, `page_id`, `head_version`, `base_version` |
| `BranchClaimHead` | `workbook_id`, `claim_id`, `head_version`, `base_version` |
| `BranchLinkHead` | `workbook_id`, `link_id`, `head_version`, `base_version` |
| `BranchSourceHead` | `workbook_id`, `source_id`, `head_version`, `base_version` |
| `BranchClaimSupportHead` | `workbook_id`, `support_id`, `created_on_branch: bool` |
| `BranchClaimDerivationHead` | `workbook_id`, `derivation_id`, `created_on_branch: bool` |
| `BranchTombstone` | `workbook_id`, `entity_kind: EntityKind`, `entity_id`, `tombstoned_at` |

Note: `ClaimSupport` and `ClaimDerivation` are branch-aware. Branch-local supports/derivations are tracked so they merge correctly and don't leak into canonical until merged.

#### MergeProposal

| Field | Type | Notes |
|-------|------|-------|
| `merge_id` | `EntityId` | |
| `workbook_id` | `EntityId` | |
| `vault_id` | `EntityId` | |
| `base_revision_id` | `VaultRevisionId` | Branch's pinned base |
| `target_revision_id` | `VaultRevisionId` | Canonical head at proposal time |
| `verdict` | `MergeVerdict` | |
| `resulting_revision` | `VaultRevisionId \| None` | Set after successful merge |
| `proposed_at` | `datetime` | |
| `resolved_at` | `datetime \| None` | |
| `proposed_by` | `ActorRef` | |

#### MergeConflict

| Field | Type | Notes |
|-------|------|-------|
| `conflict_id` | `EntityId` | |
| `merge_id` | `EntityId` | |
| `entity_kind` | `EntityKind` | |
| `entity_id` | `EntityId` | |
| `base_version` | `Version` | |
| `branch_version` | `Version` | |
| `canonical_version` | `Version` | |
| `resolution` | `MergeResolution \| None` | |
| `resolved_at` | `datetime \| None` | |

#### Job (unified compile/lint/normalize/reindex)

| Field | Type | Notes |
|-------|------|-------|
| `job_id` | `EntityId` | |
| `vault_id` | `EntityId` | |
| `workbook_id` | `EntityId \| None` | Null = canonical |
| `kind` | `JobKind` | |
| `status` | `JobStatus` | |
| `config` | `dict` | |
| `idempotency_key` | `str` | Deterministic dedup key |
| `priority` | `int` | Higher = sooner |
| `attempt_count` | `int` | |
| `max_attempts` | `int` | |
| `next_attempt_at` | `datetime \| None` | |
| `leased_until` | `datetime \| None` | |
| `heartbeat_at` | `datetime \| None` | |
| `started_at` | `datetime \| None` | |
| `completed_at` | `datetime \| None` | |
| `error` | `str \| None` | |
| `created_by` | `ActorRef` | |
| `created_by_run` | `EntityId \| None` | |

#### LintFinding

| Field | Type | Notes |
|-------|------|-------|
| `finding_id` | `EntityId` | |
| `job_id` | `EntityId` | |
| `vault_id` | `EntityId` | |
| `category` | `FindingCategory` | |
| `severity` | `FindingSeverity` | |
| `page_id` | `EntityId \| None` | |
| `claim_id` | `EntityId \| None` | |
| `description` | `str` | |
| `suggested_action` | `str \| None` | |
| `status` | `FindingStatus` | |
| `resolved_at` | `datetime \| None` | |

#### KnowledgeRunRef + KnowledgeRunArtifact

| Field | Type | Notes |
|-------|------|-------|
| **KnowledgeRunRef** | | |
| `ref_id` | `EntityId` | |
| `vault_id` | `EntityId` | |
| `run_id` | `str` | From execution.RunRecord |
| `run_type` | `str` | genesis / research / pantheon |
| `upstream_system` | `str` | Which store originated this |
| `upstream_ref` | `str \| None` | Upstream artifact/store reference |
| `source_hash` | `str \| None` | Content hash for replay |
| `sync_status` | `str` | PENDING / SYNCED / FAILED / RETRYING |
| `sync_error` | `str \| None` | |
| `synced_at` | `datetime \| None` | |
| `created_at` | `datetime` | |
| **KnowledgeRunArtifact** | | |
| `ref_id` | `EntityId` | FK to KnowledgeRunRef |
| `entity_kind` | `EntityKind` | |
| `entity_id` | `EntityId` | |
| `role` | `str` | CREATED, UPDATED, REFERENCED |

#### DomainEvent

| Field | Type | Notes |
|-------|------|-------|
| `event_id` | `EntityId` | |
| `event_type` | `str` | From taxonomy above |
| `schema_version` | `int` | |
| `aggregate_type` | `str` | |
| `aggregate_id` | `EntityId` | |
| `aggregate_version` | `Version \| None` | |
| `vault_id` | `EntityId` | |
| `workbook_id` | `EntityId \| None` | |
| `run_id` | `str \| None` | |
| `causation_id` | `EntityId \| None` | |
| `correlation_id` | `str \| None` | |
| `actor_type` | `ActorType` | |
| `actor_id` | `str` | |
| `occurred_at` | `datetime` | |
| `payload` | `dict` | |

#### EventDelivery

| Field | Type | Notes |
|-------|------|-------|
| `event_id` | `EntityId` | |
| `consumer_name` | `str` | |
| `status` | `str` | PENDING, LEASED, DELIVERED, FAILED, DEAD_LETTER |
| `attempt_count` | `int` | |
| `next_attempt_at` | `datetime \| None` | |
| `lease_owner` | `str \| None` | |
| `lease_expires_at` | `datetime \| None` | |
| `last_error` | `str \| None` | |
| `delivered_at` | `datetime \| None` | |

---

## UnitOfWork Contract

The UoW is the single atomic boundary for state mutation + event emission. Services acquire a fresh UoW per operation and commit within it.

```python
class AbstractUnitOfWork(ABC):
    # --- Full repository surface ---
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

    # --- Event construction ---
    event_factory: EventFactory
    clock: Clock
    id_generator: IdGenerator

    # --- Event buffer ---
    def record_event(self, event: DomainEvent) -> None: ...

    # --- Transaction lifecycle ---
    async def begin(self) -> None: ...
    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...

    # --- Context manager ---
    async def __aenter__(self) -> Self: ...
    async def __aexit__(self, ...) -> None: ...
```

**Commit semantics:**
1. Persist all repo mutations to database
2. Flush buffered events to `domain_events` + `event_deliveries` tables
3. Finalize staged content (promote from staging to permanent storage)
4. All three in one atomic transaction. If any fails, all roll back (including content abort).
5. Commit does NOT dispatch events or fire fanout. That is the event layer's responsibility, wired by factory.

**Rollback semantics:**
1. Roll back database transaction
2. Abort staged content
3. Clear event buffer

**Key rules:**
- One UoW per service operation. No sharing.
- Events are never visible until the transaction succeeds.
- The UoW does not dispatch events — it only persists them to the outbox.

### StagedContentStore Contract

```python
class StagedContentStore(ABC):
    async def stage(self, content: bytes, mime_type: str) -> PendingContentRef: ...
    async def finalize(self) -> None: ...
    async def abort(self) -> None: ...
    async def read(self, ref: BlobRef) -> bytes: ...
    async def delete(self, ref: BlobRef) -> None: ...
```

### EventFactory

```python
class EventFactory:
    def __init__(self, clock: Clock, id_generator: IdGenerator,
                 default_schema_version: int): ...

    def create(self, event_type: str, aggregate_type: str,
               aggregate_id: EntityId, vault_id: EntityId,
               payload: dict, **kwargs) -> DomainEvent: ...
```

Fills in `event_id`, `occurred_at`, `schema_version`, `actor`, `causation_id`, `correlation_id` consistently.

---

## Internal Service API (Commands)

All command methods acquire a UoW from the factory, perform mutations, record events, and commit. Read operations are in the query layer, not here.

### VaultService

| Method | Emits |
|--------|-------|
| `create_vault(name, description, config?) -> Vault` | `vault.created` |
| `update_vault_config(vault_id, config) -> Vault` | `vault.config_updated` |

### IngestService

| Method | Emits |
|--------|-------|
| `ingest_source(vault_id, raw_content, format, metadata, workbook_id?, idempotency_key) -> Source + SourceVersion` | `source.ingested` |
| `normalize_source(source_id, expected_version, workbook_id?, idempotency_key) -> SourceVersion` | `source.normalized` |

### PageService

| Method | Emits |
|--------|-------|
| `create_page(vault_id, page_key, page_type, title, content, compiled_from?, workbook_id?) -> Page + PageVersion` | `page.version_created` |
| `update_page(page_id, expected_version, title?, content?, summary, workbook_id?) -> PageVersion` | `page.version_created` |
| `delete_page(page_id, workbook_id) -> None` | `page.deleted` |

Delete creates a BranchTombstone. Only allowed on branches.

### ClaimService

| Method | Emits |
|--------|-------|
| `create_claim(vault_id, page_id, statement, status, support_type, confidence, workbook_id?) -> Claim + ClaimVersion` | `claim.version_created` |
| `update_claim(claim_id, expected_version, statement?, status?, confidence?, workbook_id?) -> ClaimVersion` | `claim.version_created` + `claim.status_changed` if status changed |
| `add_support(claim_id, source_id, source_segment?, strength, workbook_id?) -> ClaimSupport` | `claim.support_added` |
| `remove_support(support_id, workbook_id?) -> None` | `claim.support_removed` |
| `add_derivation(claim_id, parent_claim_id, relationship, workbook_id?) -> ClaimDerivation` | `claim.derivation_added` |
| `invalidate_claim(claim_id, reason, workbook_id?) -> ClaimVersion` | `claim.invalidated` |

### LinkService

| Method | Emits |
|--------|-------|
| `create_link(vault_id, kind, source_entity, target_entity, label?, weight?, workbook_id?) -> Link + LinkVersion` | `link.version_created` |
| `update_link(link_id, expected_version, label?, weight?, workbook_id?) -> LinkVersion` | `link.version_created` |
| `delete_link(link_id, workbook_id) -> None` | `link.deleted` |

### BranchService

| Method | Emits |
|--------|-------|
| `create_workbook(vault_id, name, purpose, actor?, run_id?) -> Workbook` | `workbook.created` |
| `abandon_workbook(workbook_id) -> Workbook` | `workbook.abandoned` |

### MergeService

| Method | Emits |
|--------|-------|
| `propose_merge(workbook_id) -> MergeProposal` | `merge.proposed` + `merge.conflict_detected` if conflicts |
| `resolve_conflict(conflict_id, resolution) -> MergeConflict` | — |
| `execute_merge(merge_id) -> VaultRevision` | `workbook.merged` + per-entity events |

`execute_merge` revalidates that canonical head has not advanced since proposal. Raises `StaleMergeError` if stale.

### CompileService (stub)

| Method | Emits |
|--------|-------|
| `schedule_compile(vault_id, workbook_id?, config?, idempotency_key) -> Job` | `compile.requested` |
| `complete_compile(job_id, result?) -> Job` | `compile.completed` |
| `fail_compile(job_id, error) -> Job` | `compile.failed` |

### LintService (stub)

| Method | Emits |
|--------|-------|
| `schedule_lint(vault_id, workbook_id?, config?, idempotency_key) -> Job` | `lint.requested` |
| `open_finding(job_id, category, severity, description, page_id?, claim_id?, suggested_action?) -> LintFinding` | `lint.finding_opened` |
| `resolve_finding(finding_id) -> LintFinding` | `lint.finding_resolved` |
| `complete_lint(job_id) -> Job` | `lint.completed` |

### RunIntegrationService

| Method | Emits |
|--------|-------|
| `attach_run(vault_id, run_id, run_type, upstream_system, upstream_ref?) -> KnowledgeRunRef` | `artifact.attached` |
| `record_artifact(ref_id, entity_kind, entity_id, role, idempotency_key) -> KnowledgeRunArtifact` | `artifact.attached` |
| `commit_research_output(vault_id, research_artifacts, workbook_id?, idempotency_key) -> list[Source + Page]` | `research.output_committed` |
| `commit_invention_output(vault_id, invention_report, workbook_id?, idempotency_key) -> Page + claims` | `invention.output_committed` |

---

## Query Layer API (Reads)

All query methods take a read-only repository/connection. They implement the COW branch read-through logic (branch head → base revision fallback). No UoW needed.

| Module | Methods |
|--------|---------|
| `vault_queries` | `get_vault(vault_id)`, `list_vaults()` |
| `source_queries` | `get_source(source_id, workbook_id?)`, `list_sources(vault_id, workbook_id?)` |
| `page_queries` | `get_page(page_id, workbook_id?)`, `list_pages(vault_id, workbook_id?, page_type?)` |
| `claim_queries` | `get_claim(claim_id, workbook_id?)` (returns ClaimVersion + supports + derivations), `list_claims(page_id, workbook_id?)` |
| `link_queries` | `list_links(entity_id, direction?, kind?, workbook_id?)`, `get_backlinks(page_id, workbook_id?)` |
| `branch_queries` | `get_workbook(workbook_id)`, `list_workbooks(vault_id, status?)`, `diff_workbook(workbook_id)`, `get_effective_state(workbook_id)` |

---

## Run Integration: Bridge Architecture

ForgeBase integrates with existing Hephaestus systems through a bridge interface, not direct cross-imports. Upstream systems (Genesis, Pantheon, Perplexity) do not know ForgeBase service internals.

### ForgeBaseIntegrationBridge

```python
class ForgeBaseIntegrationBridge(ABC):
    async def on_genesis_completed(self, vault_id, run_id, report) -> None: ...
    async def on_pantheon_completed(self, vault_id, run_id, state) -> None: ...
    async def on_research_completed(self, vault_id, run_id, artifacts) -> None: ...
```

- Injected at composition time via `factory.py`
- Upstream systems call the bridge
- The bridge translates into ForgeBase durable jobs/commands
- If `vault_id` is absent, the bridge is a no-op

### Durable and Asynchronous

Integration hooks are durable and asynchronous by default:

1. Successful upstream completion emits a durable integration job/request
2. ForgeBase ingest/commit happens as follow-on durable work
3. ForgeBase sync failure does NOT mark the upstream run as failed
4. KnowledgeRunRef tracks: upstream run status, ForgeBase sync status, retry state, last sync error

### Idempotency Keys

Every integration flow uses deterministic idempotency keys:

| Flow | Key Pattern |
|------|-------------|
| Genesis artifact ingest | `"{run_id}:{artifact_name}:{artifact_hash}"` |
| Invention commit | `"{run_id}:top_invention:{invention_hash}"` |
| Pantheon verdict sync | `"{run_id}:pantheon:{verdict_version}"` |
| Perplexity source ingest | `"{upstream_artifact_id}:{content_hash}"` |

### Upstream Provenance

Every ForgeBase artifact created from another Hephaestus subsystem carries:

- `upstream_system` — which store originated this (RunStore, ResearchArtifactStore, CouncilArtifactStore, etc.)
- `upstream_ref` — upstream artifact/store reference
- `source_hash` — content hash for replay
- `sync_status` — PENDING / SYNCED / FAILED / RETRYING
- `synced_at` — timestamp

### Coexistence, Not Replacement

ForgeBase does NOT subsume existing stores in sub-project 1:

- `RunStore` (execution/) — continues owning run lifecycle
- `ResearchArtifactStore` — continues owning per-run research cache
- `CouncilArtifactStore` — continues owning Pantheon deliberation
- `ConvergenceDatabase` — continues owning banality patterns
- `AntiMemory` — continues owning convergence prevention vectors

ForgeBase sits alongside them with durable, idempotent integration hooks.

---

## Testing Strategy

### Dual-Backend Test Matrix

```
@pytest.fixture(params=["sqlite", "postgres"])
async def uow(request) -> AbstractUnitOfWork:
    if request.param == "sqlite":
        return SqliteUnitOfWork(db_path)  # file-backed, WAL mode
    else:
        return PostgresUnitOfWork(test_pg_dsn)
```

**CI gates:**
- SQLite tests on every commit / PR (fast, no infra)
- Postgres tests on every PR **before merge** (requires test container)
- Merge is blocked if Postgres matrix is red
- Release gates require both green

### Test Layers

**1. Domain model tests** (pure unit tests, no I/O)
- Value object parsing/validation
- Enum coverage
- Merge conflict detection predicates (`domain/conflicts.py`)
- Version reconciliation rules (`domain/merge.py`)
- Event type construction via EventFactory

**2. Repository contract tests** (parametrized dual-backend)
- CRUD for every entity
- Version chain integrity
- Branch head read-through
- Tombstone behavior
- Optimistic concurrency rejection
- Idempotency dedup

**3. UoW transaction tests** (parametrized dual-backend)
- Commit atomicity: state + events both persisted
- Rollback atomicity: state + events + content all discarded
- Content staging: finalize on commit, abort on rollback
- Event buffer isolation between UoW instances

**4. Service integration tests** (parametrized dual-backend)
- Full lifecycle: create vault → ingest → create page → create claims → create workbook → modify on branch → propose merge → resolve conflicts → execute merge
- Idempotency: duplicate calls return same result
- Optimistic concurrency: stale writes rejected
- Stale merge detection
- Event emission verification per operation

**5. Branch scenario tests** (parametrized dual-backend)
- Clean merge (no canonical changes during branch)
- Conflicted merge (canonical advanced on same entities)
- Multi-entity conflict (page + claim + link + source diverged)
- Tombstone merge to canonical (archive behavior)
- Branch-born entities adopted into canonical
- Read-through correctness (branch overlay + fallback)

**6. Event outbox tests**
- Events visible only after commit
- Events absent after rollback
- Dispatcher delivery + consumer idempotency
- Dead-letter on repeated failure
- Per-aggregate ordering preserved

**7. Content store tests**
- Stage + finalize → content readable
- Stage + abort → content gone
- Orphan detection (staged but never finalized)
- Local FS backend
- (S3 backend in integration suite, not unit)

**8. Query layer tests** (parametrized dual-backend)
- Branch-aware reads return correct version
- Tombstoned entities excluded from default queries
- Archived entities excluded unless `include_archived`
- Backlink traversal accuracy
- Diff correctness against known branch state

**9. Integration bridge contract tests** (new)
- `vault_id` absent → no ForgeBase sync request
- `vault_id` present → one durable sync request created
- Duplicate hook invocation → idempotent result
- Upstream success + ForgeBase sync failure → upstream remains successful, sync moves to retry/error state

**10. SQLite realism tests** (new)
- File-backed SQLite with WAL mode for transaction/concurrency/UoW tests
- `:memory:` only for fast unit-style checks
- Covers real locking and transaction behavior that in-memory can hide

### Test Fixtures

| Fixture | Contents |
|---------|----------|
| Deterministic `IdGenerator` | Produces predictable IDs for assertions |
| Deterministic `Clock` | Frozen or stepped time for event ordering |
| In-memory `ContentStore` | Avoids filesystem in unit tests |
| `empty_vault` | Vault + initial revision |
| `seeded_vault` | 5 sources, 10 pages, 30 claims, links |
| `branched_vault` | Seeded vault + open workbook with modifications |

---

## What Is NOT In Sub-project 1

Not because it is removed — because it depends on a correct foundation:

- Advanced compiler logic (sub-project 2)
- Research orchestration (sub-project 2)
- Lint detection intelligence (sub-project 3)
- Multi-agent teams (sub-project 5)
- Genesis/DeepForge vault-aware invention logic (sub-project 4)
- Cross-vault fusion (sub-project 5)
- Full web UI (sub-project 5)
- Full CLI surface (sub-project 5)
- Distillation/fine-tuning layer (future)

These should sit on top of the Foundation Platform's stable contracts.

---

## What Gets Implemented In Sub-project 1

### Backend
- Production database schema (SQLite + Postgres)
- Migrations framework
- All repository implementations (both backends)
- UoW implementations (both backends)
- Staged content store (local FS)
- Event outbox + dispatcher + consumer framework
- All service layer methods
- All query layer methods
- Integration bridge interface + adapters (Genesis, Pantheon, Research)
- Factory/bootstrap

### Minimum Real Flows (must work end-to-end)
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
