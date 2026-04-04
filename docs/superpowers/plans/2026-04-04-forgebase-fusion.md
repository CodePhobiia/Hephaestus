# ForgeBase Cross-Vault Fusion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the three-stage cross-vault fusion pipeline — embedding-based candidate generation, FusionAnalyzer structural analogy validation, and policy-governed synthesis with provenance-aware pack merging — making ForgeBase a true cross-domain invention substrate.

**Architecture:** Stage 1 generates typed, diversified bridge candidates via persistent embedding index. Stage 2 validates structural analogies via a dedicated FusionAnalyzer ABC (separate from CompilerBackend and LintAnalyzer). Stage 3 ranks, deduplicates, and merges context packs from multiple vaults with provenance-aware fingerprinting. FusionOrchestrator drives the pipeline from FusionRequest to FusionResult. Shared contracts in `forgebase/contracts/` survive sub-projects 5a-5d.

**Tech Stack:** Python 3.11+, aiosqlite, sentence-transformers, numpy, pytest-asyncio, existing ForgeBase (954 tests)

**Spec:** `docs/superpowers/specs/2026-04-04-forgebase-fusion-design.md`

---

## File Structure

```
# New files to create:

src/hephaestus/forgebase/
  contracts/
    __init__.py                              # CREATE
    fusion.py                                # CREATE — FusionRequest, FusionResult, PairFusionResult
    query.py                                 # CREATE — VaultQuery, QueryResult stubs
    agent.py                                 # CREATE — AgentTask, AgentRun stubs
    views.py                                 # CREATE — VaultSummary, WorkbookDiffView, LintReportView

  domain/enums.py                            # MODIFY — add FusionMode, BridgeCandidateKind, AnalogyVerdict
  domain/models.py                           # MODIFY — add FusionRun
  domain/event_types.py                      # MODIFY — add 8 fusion events

  fusion/
    __init__.py                              # CREATE
    models.py                                # CREATE — BridgeCandidate, AnalogicalMap, TransferOpportunity, etc.
    enums.py                                 # CREATE — (re-export from domain/enums for convenience)
    policy.py                                # CREATE — FusionPolicy
    embeddings.py                            # CREATE — EmbeddingIndex persistent cache
    candidates.py                            # CREATE — Stage 1
    analyzer.py                              # CREATE — FusionAnalyzer ABC
    analyzers/
      __init__.py                            # CREATE
      anthropic_analyzer.py                  # CREATE
      mock_analyzer.py                       # CREATE
    synthesis.py                             # CREATE — Stage 3
    orchestrator.py                          # CREATE — FusionOrchestrator

  repository/fusion_run_repo.py              # CREATE — ABC
  repository/embedding_cache_repo.py         # CREATE — ABC
  repository/uow.py                          # MODIFY — add fusion_runs, embedding_cache
  store/sqlite/schema.py                     # MODIFY — add fb_fusion_runs, fb_embedding_cache
  store/sqlite/fusion_run_repo.py            # CREATE
  store/sqlite/embedding_cache_repo.py       # CREATE
  store/sqlite/uow.py                        # MODIFY — wire new repos

  factory.py                                 # MODIFY — wire fusion components

tests/test_forgebase/
  test_contracts/
    __init__.py                              # CREATE
    test_fusion_contracts.py                 # CREATE
    test_views.py                            # CREATE
  test_fusion/
    __init__.py                              # CREATE
    conftest.py                              # CREATE — mock analyzer + seeded vaults
    test_models.py                           # CREATE
    test_policy.py                           # CREATE
    test_embeddings.py                       # CREATE
    test_candidates.py                       # CREATE
    test_analyzer_contract.py                # CREATE
    test_mock_analyzer.py                    # CREATE
    test_anthropic_analyzer.py               # CREATE
    test_synthesis.py                        # CREATE
    test_orchestrator.py                     # CREATE
  test_e2e/
    test_fusion_lifecycle.py                 # CREATE
```

---

### Task 1: Shared Contracts + Domain Extensions

**Files:**
- Create: `src/hephaestus/forgebase/contracts/__init__.py`
- Create: `src/hephaestus/forgebase/contracts/fusion.py`
- Create: `src/hephaestus/forgebase/contracts/query.py`
- Create: `src/hephaestus/forgebase/contracts/agent.py`
- Create: `src/hephaestus/forgebase/contracts/views.py`
- Modify: `src/hephaestus/forgebase/domain/enums.py`
- Modify: `src/hephaestus/forgebase/domain/models.py`
- Modify: `src/hephaestus/forgebase/domain/event_types.py`
- Test: `tests/test_forgebase/test_contracts/`

**contracts/fusion.py** — `FusionRequest`, `FusionResult`, `PairFusionResult` dataclasses from the spec.

**contracts/query.py** — `VaultQuery`, `QueryResult`, `QueryScope` stubs (for 5b).

**contracts/agent.py** — `AgentTask`, `AgentRun`, `AgentRole` stubs (for 5c).

**contracts/views.py** — `VaultSummary`, `WorkbookDiffView`, `LintReportView` read models.

**domain/enums.py** — Append: `FusionMode` (STRICT, EXPLORATORY), `BridgeCandidateKind` (CONCEPT, MECHANISM, CLAIM_CLUSTER, PAGE_THEME, EXPLORATORY), `AnalogyVerdict` (STRONG_ANALOGY, WEAK_ANALOGY, NO_ANALOGY, INVALID).

**domain/models.py** — Add `FusionRun` dataclass with all fields from spec.

**domain/event_types.py** — Add 8 fusion events to EVENT_TAXONOMY.

Tests verify all contracts constructible, enums have correct values, FusionRun model.

- [ ] **Step 1-6: Write tests → implement → run full suite → commit**

```bash
git commit -m "feat(forgebase): add shared contracts, fusion enums, FusionRun model, 8 fusion events"
```

---

### Task 2: Fusion Domain Models

**Files:**
- Create: `src/hephaestus/forgebase/fusion/__init__.py`
- Create: `src/hephaestus/forgebase/fusion/models.py`
- Create: `src/hephaestus/forgebase/fusion/policy.py`
- Test: `tests/test_forgebase/test_fusion/__init__.py`
- Test: `tests/test_forgebase/test_fusion/test_models.py`
- Test: `tests/test_forgebase/test_fusion/test_policy.py`

**fusion/models.py** — All fusion-specific dataclasses:
- `BridgeCandidate` with left/right provenance, typed kinds, revision refs
- `ComponentMapping`, `ConstraintMapping`, `AnalogyBreak` value objects
- `AnalogicalMap` with verdict, structured mappings, page/claim refs
- `TransferOpportunity` with structured caveats, confidence, refs
- `FusionManifest`, `PairFusionManifest`

**fusion/policy.py** — `FusionPolicy` dataclass with all configurable fields from spec + `DEFAULT_FUSION_POLICY`.

Tests verify model construction, policy defaults, typed enums.

- [ ] **Step 1-6: Write tests → implement → commit**

```bash
git commit -m "feat(forgebase): add fusion domain models — BridgeCandidate, AnalogicalMap, TransferOpportunity, FusionPolicy"
```

---

### Task 3: Fusion Repository + Schema + Embedding Cache

**Files:**
- Create: `src/hephaestus/forgebase/repository/fusion_run_repo.py`
- Create: `src/hephaestus/forgebase/repository/embedding_cache_repo.py`
- Modify: `src/hephaestus/forgebase/repository/uow.py`
- Modify: `src/hephaestus/forgebase/store/sqlite/schema.py`
- Create: `src/hephaestus/forgebase/store/sqlite/fusion_run_repo.py`
- Create: `src/hephaestus/forgebase/store/sqlite/embedding_cache_repo.py`
- Modify: `src/hephaestus/forgebase/store/sqlite/uow.py`
- Test: `tests/test_forgebase/test_store/test_sqlite_fusion_run_repo.py`
- Test: `tests/test_forgebase/test_store/test_sqlite_embedding_cache_repo.py`

**FusionRunRepository ABC**: create, get, list_by_vaults, update_status, list_by_problem
**EmbeddingCacheRepository ABC**: get(entity_id, version), put(entity_id, version, embedding), invalidate(entity_id), batch_get

**Schema**: `fb_fusion_runs` table (all FusionRun fields), `fb_embedding_cache` table (entity_id TEXT, version INTEGER, embedding_blob BLOB, computed_at TEXT, PRIMARY KEY (entity_id, version))

SQLite implementations following established patterns. Wire into UoW.

Tests: CRUD for fusion runs, embedding cache hit/miss/invalidation, version-pinned retrieval.

- [ ] **Step 1-6: Write tests → implement → wire UoW → commit**

```bash
git commit -m "feat(forgebase): add fusion run + embedding cache repos with SQLite schema"
```

---

### Task 4: EmbeddingIndex (Persistent Cache Layer)

**Files:**
- Create: `src/hephaestus/forgebase/fusion/embeddings.py`
- Test: `tests/test_forgebase/test_fusion/test_embeddings.py`

```python
class EmbeddingIndex:
    """Persistent, version-pinned embedding cache."""
    
    def __init__(
        self,
        uow_factory: Callable[[], AbstractUnitOfWork],
        model_name: str = "all-MiniLM-L6-v2",
    ) -> None: ...

    async def get_or_compute(
        self, entity_id: EntityId, version: Version, text: str,
    ) -> NDArray[np.float32]:
        """Return cached embedding or compute + cache."""

    async def batch_get_or_compute(
        self, items: list[tuple[EntityId, Version, str]],
    ) -> list[NDArray[np.float32]]:
        """Batch: return cached or compute for each item."""

    async def invalidate(self, entity_id: EntityId) -> None:
        """Remove cached embeddings for an entity."""
```

Uses `sentence-transformers` (lazy-loaded, same pattern as existing `deepforge/pressure.py`). Stores embeddings as numpy float32 blobs via `EmbeddingCacheRepository`.

Tests: cache miss → compute + store, cache hit → return stored, version change → recompute, invalidate works, batch operations.

- [ ] **Step 1-6: Write tests → implement → commit**

```bash
git commit -m "feat(forgebase): add EmbeddingIndex with persistent version-pinned cache"
```

---

### Task 5: Stage 1 — Bridge Candidate Generation

**Files:**
- Create: `src/hephaestus/forgebase/fusion/candidates.py`
- Test: `tests/test_forgebase/test_fusion/test_candidates.py`

```python
async def generate_bridge_candidates(
    uow: AbstractUnitOfWork,
    left_vault_id: EntityId,
    right_vault_id: EntityId,
    embedding_index: EmbeddingIndex,
    policy: FusionPolicy,
    problem: str | None = None,
    fusion_mode: FusionMode = FusionMode.STRICT,
) -> list[BridgeCandidate]:
```

Implementation:
1. Extract pages/claims from both vaults via UoW repos
2. Apply epistemic filter (STRICT: concept/mechanism pages + SUPPORTED claims; EXPLORATORY: + candidates)
3. Get/compute embeddings via EmbeddingIndex
4. Cross-vault cosine similarity (numpy matrix multiplication)
5. Problem relevance boost (embed problem, weight by cosine to problem)
6. Diversified selection by type allocation + similarity bands
7. Build BridgeCandidates with left/right provenance

Tests: seeded vaults → candidates generated, diversity across types, epistemic filter respects STRICT mode, problem relevance boosts relevant candidates, empty vault → empty candidates.

- [ ] **Step 1-6: Write tests → implement → commit**

```bash
git commit -m "feat(forgebase): add Stage 1 bridge candidate generation with typed diversification"
```

---

### Task 6: FusionAnalyzer ABC + Mock

**Files:**
- Create: `src/hephaestus/forgebase/fusion/analyzer.py`
- Create: `src/hephaestus/forgebase/fusion/analyzers/__init__.py`
- Create: `src/hephaestus/forgebase/fusion/analyzers/mock_analyzer.py`
- Test: `tests/test_forgebase/test_fusion/conftest.py`
- Test: `tests/test_forgebase/test_fusion/test_mock_analyzer.py`

`FusionAnalyzer` ABC with `analyze_candidates()` returning `(list[AnalogicalMap], list[TransferOpportunity], BackendCallRecord)`.

`MockFusionAnalyzer`: candidates above similarity 0.5 → STRONG_ANALOGY with mock component mappings. Below 0.3 → NO_ANALOGY. Between → WEAK_ANALOGY. Generates one TransferOpportunity per STRONG map.

Tests: mock produces expected verdicts, handles empty input, generates transfers for strong analogies.

- [ ] **Step 1-4: Write tests → implement → commit**

```bash
git commit -m "feat(forgebase): add FusionAnalyzer ABC and MockFusionAnalyzer"
```

---

### Task 7: Anthropic FusionAnalyzer

**Files:**
- Create: `src/hephaestus/forgebase/fusion/analyzers/anthropic_analyzer.py`
- Test: `tests/test_forgebase/test_fusion/test_anthropic_analyzer.py`

Uses Claude with structured JSON output. Analogy-specific prompts: "Given these two concepts from different domains, determine if there is a structural analogy..." Low temperature. Validate/repair pattern.

Tests mock the Anthropic client. Verify: correct JSON parsing, analogy verdicts, transfer opportunity extraction, repair on parse failure.

- [ ] **Step 1-4: Write tests → implement → commit**

```bash
git commit -m "feat(forgebase): add Anthropic FusionAnalyzer with structural analogy prompts"
```

---

### Task 8: Stage 3 — Fusion Synthesis

**Files:**
- Create: `src/hephaestus/forgebase/fusion/synthesis.py`
- Test: `tests/test_forgebase/test_fusion/test_synthesis.py`

```python
async def synthesize_fusion_result(
    pair_results: list[PairFusionResult],
    vault_packs: dict[EntityId, tuple[PriorArtBaselinePack, DomainContextPack, ConstraintDossierPack]],
    policy: FusionPolicy,
    request: FusionRequest,
    manifest_metadata: dict,
) -> FusionResult:
```

Pack merging with provenance-aware dedup: same claim/page ID → merge, different ID + similar text → keep both (conservative). Rank analogical maps by confidence. Group overlapping transfers. Cap per policy.

Tests: merge two vault packs → deduped correctly, provenance preserved, caps respected, poisoning guard (CONTESTED not in fused baseline).

- [ ] **Step 1-6: Write tests → implement → commit**

```bash
git commit -m "feat(forgebase): add Stage 3 fusion synthesis with provenance-aware pack merging"
```

---

### Task 9: FusionOrchestrator

**Files:**
- Create: `src/hephaestus/forgebase/fusion/orchestrator.py`
- Test: `tests/test_forgebase/test_fusion/test_orchestrator.py`

```python
class FusionOrchestrator:
    def __init__(self, uow_factory, context_assembler, fusion_analyzer, 
                 embedding_index, policy=None, default_actor=ActorRef.system()): ...
    
    async def fuse(self, request: FusionRequest) -> FusionResult: ...
```

Full pipeline: validate → extract packs → pairwise candidates + analysis → aggregate synthesis → persist FusionRun → emit events.

Tests using MockFusionAnalyzer and seeded vaults:
- test_fuse_two_vaults — complete pipeline produces FusionResult
- test_fuse_persists_fusion_run — FusionRun queryable after completion
- test_fuse_emits_events — fusion.completed event in outbox
- test_fuse_with_problem — problem-aware fusion
- test_fuse_invalid_request — < 2 vaults raises error
- test_fuse_poisoning_guard — CONTESTED content excluded from fused baseline

- [ ] **Step 1-6: Write tests → implement → commit**

```bash
git commit -m "feat(forgebase): add FusionOrchestrator — full three-stage pipeline"
```

---

### Task 10: Factory Wiring + E2E Test

**Files:**
- Modify: `src/hephaestus/forgebase/factory.py`
- Modify: `tests/test_forgebase/test_e2e/test_factory.py`
- Create: `tests/test_forgebase/test_e2e/test_fusion_lifecycle.py`

Wire into ForgeBase:
- `EmbeddingIndex`
- `MockFusionAnalyzer` (or Anthropic if API key available)
- `FusionOrchestrator`

Add `fb.fusion` attribute to ForgeBase class.

E2E test exercises all 9 minimum flows:
1. Create vault A (battery materials content) + vault B (logistics content), compile both
2. Fuse A + B → bridge candidates generated
3. Analyzer validates → maps with STRONG/WEAK/NO verdicts
4. Transfer opportunities with problem relevance
5. Fused packs: baseline (strict), context (broad), dossier (governance)
6. FusionRun persisted and queryable
7. Manifest with pair-level detail
8. Poisoning guard: CONTESTED not in fused baseline
9. Problem-aware: fusion with problem vs without produces different rankings

- [ ] **Step 1-6: Wire factory → write e2e → commit**

```bash
git commit -m "feat(forgebase): wire fusion into factory, add e2e fusion lifecycle test"
```

---

## Implementation Notes

**Parallelization:**
- Task 1 (contracts + domain) must come first
- Task 2 (fusion models) depends on Task 1
- Task 3 (repos + schema) depends on Task 1
- Tasks 2, 3 can run in parallel
- Task 4 (embeddings) depends on Task 3
- Tasks 5, 6, 7 can run in parallel after Tasks 2 + 4
- Task 8 (synthesis) depends on Task 2
- Task 9 (orchestrator) depends on Tasks 5, 6, 8
- Task 10 (factory + e2e) depends on Task 9

**Embedding model:** Uses `all-MiniLM-L6-v2` from `sentence-transformers`, same as existing convergence detection in `deepforge/pressure.py`. Lazy-loaded to keep import times fast.

**Numpy for similarity:** Cross-vault cosine similarity computed via numpy matrix multiplication. Already a dependency in `pyproject.toml`.

**Test vault seeding:** E2E tests create two vaults with deliberately different domain content (e.g., battery chemistry vs supply chain logistics), compile both through Tier 1 + Tier 2, then fuse. MockFusionAnalyzer provides deterministic bridge detection.
