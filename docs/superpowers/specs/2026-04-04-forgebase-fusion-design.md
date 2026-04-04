# ForgeBase Sub-project 5a: Cross-Vault Fusion — Design Spec

## Overview

This spec covers cross-vault fusion — the ability to detect structural analogies across multiple knowledge vaults and produce fused context for invention runs. It is the first of four sub-projects completing ForgeBase (5a fusion → 5b CLI → 5c agents → 5d web UI).

### Goal

Make ForgeBase truly cross-domain: fuse knowledge from multiple vaults, detect bridge concepts and analogical structures, surface transfer opportunities, and produce policy-filtered fused context packs that materially improve Genesis/DeepForge/Pantheon invention runs.

### Architectural Stance

Fusion is not similarity search. Fusion is similarity prefiltering followed by structural analogy analysis and policy-governed synthesis. The pipeline is problem-aware: the user's problem affects candidate diversification, analogy analysis, and transfer opportunity ranking.

---

## Locked Architectural Decisions

### 1. Three-Stage Fusion Pipeline

- **Stage 1 (Candidate Generation):** Embedding-based cross-vault bridge candidate selection. Typed, diversified across concept/mechanism/claim/theme categories and similarity bands.
- **Stage 2 (Structural Analysis):** `FusionAnalyzer` ABC validates analogies, maps mechanisms, detects transfer opportunities. Explicit negative capability — can reject candidates.
- **Stage 3 (Fusion Synthesis):** Rank, dedup, group validated analogies. Merge context packs with provenance-aware dedup. Produce `FusionResult` with policy filtering.

### 2. Public API Contract

`FusionOrchestrator.fuse(request: FusionRequest) -> FusionResult` is the canonical interface. Shared contracts live in `forgebase/contracts/`, not nested inside feature packages.

### 3. Problem-Aware Pipeline

The user's problem is central, not optional. It affects:
- Stage 1: candidate diversification (bias toward problem-relevant domains)
- Stage 2: analogy analysis (evaluate relevance to stated problem)
- Stage 3: ranking and transfer selection (prioritize problem-useful transfers)

### 4. Multi-Vault Semantics

Multi-vault fusion (3+ vaults) is explicitly pairwise analysis + aggregate synthesis:
- Pair-level candidate generation and analysis
- Pair-level sub-results with their own manifests
- Aggregate reducer merges all pair results into final FusionResult

### 5. Persistent Embedding Cache

Embeddings are not recomputed from scratch on every fusion run. A persistent, version-pinned embedding index (keyed to page/claim/entity version) is maintained. Reuses the existing `sentence-transformers` infrastructure.

### 6. Strict Default, Exploratory Optional

Default fusion mode: candidates drawn from canonical concept pages, mechanism pages, and promoted/policy-eligible claims only. Concept candidates and speculative entities require explicit `FusionMode.EXPLORATORY`.

### 7. Fusion as Durable Artifact

Fusion runs produce durable ForgeBase artifacts — not just transient API responses. Queryable by vault pair, problem, policy version, analyzer version, bridge concepts found.

### 8. Same Epistemic Policy

Fused packs follow the same trust filters as single-vault extraction:
- Baseline: strict (only SUPPORTED + VERIFIED, AUTHORITATIVE sources)
- Context: broad (includes hypotheses, open questions from both vaults)
- Dossier: governance-grade (evidence-backed constraints from both vaults)

---

## Shared Contracts (`forgebase/contracts/`)

Survive all sub-projects (5a-5d). Defined once, imported everywhere.

```
forgebase/contracts/
    __init__.py
    fusion.py              # FusionRequest, FusionResult
    query.py               # VaultQuery, QueryResult, QueryScope
    agent.py               # AgentTask, AgentRun, AgentRole, AgentTrace (stub for 5c)
    views.py               # VaultSummary, WorkbookDiffView, LintReportView
```

### FusionRequest

```
vault_ids            : list[EntityId]
problem              : str | None       # affects diversification, analysis, ranking
fusion_mode          : FusionMode       # STRICT (default) or EXPLORATORY
policy               : FusionPolicy | None
max_candidates       : int = 50
max_bridges          : int = 20
max_transfers        : int = 10
```

### FusionResult

```
fusion_id            : EntityId
request              : FusionRequest
bridge_concepts      : list[AnalogicalMap]
transfer_opportunities: list[TransferOpportunity]
fused_baseline       : PriorArtBaselinePack
fused_context        : DomainContextPack
fused_dossier        : ConstraintDossierPack
pair_results         : list[PairFusionResult]  # per-pair sub-results
fusion_manifest      : FusionManifest
created_at           : datetime
```

### PairFusionResult

```
left_vault_id        : EntityId
right_vault_id       : EntityId
candidates_generated : int
maps_produced        : list[AnalogicalMap]
transfers_produced   : list[TransferOpportunity]
pair_manifest        : PairFusionManifest
```

### VaultSummary (read model for CLI/web)

```
vault_id             : EntityId
name                 : str
description          : str
health_score         : float            # from last lint
page_count           : int
claim_count          : int
source_count         : int
finding_count        : int              # open findings
last_compiled_at     : datetime | None
last_linted_at       : datetime | None
```

---

## Module Organization

```
src/hephaestus/forgebase/
  contracts/
    __init__.py
    fusion.py                # FusionRequest, FusionResult, PairFusionResult
    query.py                 # VaultQuery, QueryResult, QueryScope (stub for 5b)
    agent.py                 # AgentTask, AgentRun, AgentRole (stub for 5c)
    views.py                 # VaultSummary, WorkbookDiffView, LintReportView

  fusion/
    __init__.py
    models.py                # BridgeCandidate, AnalogicalMap, TransferOpportunity, FusionManifest
    enums.py                 # FusionMode, BridgeCandidateKind, AnalogyVerdict
    candidates.py            # Stage 1: embedding candidate generation
    embeddings.py            # Persistent embedding cache/index
    analyzer.py              # FusionAnalyzer ABC
    analyzers/
      __init__.py
      anthropic_analyzer.py  # First implementation
      mock_analyzer.py       # For testing
    synthesis.py             # Stage 3: ranking, dedup, grouping, pack merging
    orchestrator.py          # FusionOrchestrator: full pipeline
    policy.py                # FusionPolicy
```

---

## Domain Model

### Enumerations

```
FusionMode           — STRICT, EXPLORATORY
BridgeCandidateKind  — CONCEPT, MECHANISM, CLAIM_CLUSTER, PAGE_THEME, EXPLORATORY
AnalogyVerdict       — STRONG_ANALOGY, WEAK_ANALOGY, NO_ANALOGY, INVALID
```

### BridgeCandidate (Stage 1 output)

```
candidate_id         : EntityId
left_vault_id        : EntityId
right_vault_id       : EntityId
left_entity_ref      : EntityId
right_entity_ref     : EntityId
left_kind            : BridgeCandidateKind
right_kind           : BridgeCandidateKind
similarity_score     : float
retrieval_reason     : str
left_text            : str
right_text           : str
left_claim_refs      : list[EntityId]
right_claim_refs     : list[EntityId]
left_source_refs     : list[EntityId]
right_source_refs    : list[EntityId]
left_revision_ref    : VaultRevisionId
right_revision_ref   : VaultRevisionId
epistemic_filter_passed: bool
problem_relevance    : float | None     # how relevant to the stated problem
```

### AnalogicalMap (Stage 2 output)

```
map_id               : EntityId
bridge_concept       : str
left_structure       : str
right_structure      : str
mapped_components    : list[ComponentMapping]
mapped_constraints   : list[ConstraintMapping]
analogy_breaks       : list[AnalogyBreak]
confidence           : float
verdict              : AnalogyVerdict
problem_relevance    : float | None
source_candidates    : list[EntityId]
left_page_refs       : list[EntityId]
right_page_refs      : list[EntityId]
left_claim_refs      : list[EntityId]
right_claim_refs     : list[EntityId]
```

**ComponentMapping:** `left_component: str, right_component: str, left_ref: EntityId | None, right_ref: EntityId | None, mapping_confidence: float`

**ConstraintMapping:** `left_constraint: str, right_constraint: str, preserved: bool`

**AnalogyBreak:** `description: str, severity: str, category: str` (categories: structural_mismatch, scale_difference, domain_assumption, temporal_mismatch)

### TransferOpportunity (Stage 2 output)

```
opportunity_id       : EntityId
from_vault_id        : EntityId
to_vault_id          : EntityId
mechanism            : str
rationale            : str
caveats              : list[str]
caveat_categories    : list[str]         # feasibility, scale, domain_assumption, etc.
analogical_map_id    : EntityId
confidence           : float
problem_relevance    : float | None
from_page_refs       : list[EntityId]
to_page_refs         : list[EntityId]
from_claim_refs      : list[EntityId]
```

### FusionManifest

```
manifest_id          : EntityId
vault_ids            : list[EntityId]
problem              : str | None
fusion_mode          : FusionMode
candidate_count      : int
analyzed_count       : int
bridge_count         : int
transfer_count       : int
policy_version       : str
analyzer_version     : str
analyzer_calls       : list[BackendCallRecord]
pair_manifests       : list[PairFusionManifest]
created_at           : datetime
```

**PairFusionManifest:** `left_vault_id, right_vault_id, left_revision, right_revision, candidate_count, map_count, transfer_count, analyzer_calls`

### FusionRun (durable artifact)

```
fusion_run_id        : EntityId
vault_ids            : list[EntityId]
problem              : str | None
fusion_mode          : FusionMode
status               : str              # PENDING, RUNNING, COMPLETED, FAILED
bridge_count         : int
transfer_count       : int
manifest_id          : EntityId
policy_version       : str
created_at           : datetime
completed_at         : datetime | None
```

Queryable by vault pair, problem, policy version. Persisted as a first-class entity.

---

## Stage 1: Candidate Generation

### `fusion/candidates.py`

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

**Flow:**
1. Load extractable entities from both vaults (pages, claims, concept candidates)
2. Apply epistemic filter: STRICT mode uses only canonical pages + promoted claims; EXPLORATORY includes speculative
3. Retrieve or compute embeddings via `EmbeddingIndex`
4. Cross-vault cosine similarity matrix
5. If problem provided: also embed the problem, boost candidates closer to problem embedding
6. Diversified selection:
   - Budget allocation by type (concept 40%, mechanism 30%, claim 20%, exploratory 10%)
   - Within each type: spread across similarity bands (top-25%, 25-50%, 50-75%), not just highest
7. Build BridgeCandidate with left/right provenance, revision refs

### `fusion/embeddings.py`

```python
class EmbeddingIndex:
    """Persistent, version-pinned embedding cache."""
    
    async def get_or_compute(
        self, entity_id: EntityId, version: Version, text: str,
    ) -> NDArray[np.float32]: ...
    
    async def batch_get_or_compute(
        self, items: list[tuple[EntityId, Version, str]],
    ) -> list[NDArray[np.float32]]: ...
    
    async def invalidate(self, entity_id: EntityId) -> None: ...
```

Backed by a simple SQLite table: `fb_embedding_cache(entity_id, version, embedding_blob, computed_at)`. Embeddings recomputed only when entity version changes.

---

## Stage 2: FusionAnalyzer

### `fusion/analyzer.py`

```python
class FusionAnalyzer(ABC):
    """Structural analogy analysis — dedicated contract for cross-domain fusion."""

    @abstractmethod
    async def analyze_candidates(
        self,
        candidates: list[BridgeCandidate],
        left_context: DomainContextPack,
        right_context: DomainContextPack,
        problem: str | None = None,
    ) -> tuple[list[AnalogicalMap], list[TransferOpportunity], BackendCallRecord]:
        """Analyze bridge candidates for structural analogies.
        
        Must produce:
        - AnalogicalMaps with STRONG/WEAK/NO/INVALID verdicts
        - TransferOpportunities for validated analogies
        - Explicit negative results (NO_ANALOGY, INVALID)
        
        Problem affects: relevance ranking, transfer direction preference.
        """
```

`AnthropicFusionAnalyzer`: uses Claude with structured JSON output. Analogy-specific prompts. Low temperature. Validate/repair pattern.

`MockFusionAnalyzer`: deterministic — marks first N candidates as STRONG_ANALOGY based on similarity threshold.

---

## Stage 3: Fusion Synthesis

### `fusion/synthesis.py`

```python
async def synthesize_fusion_result(
    pair_results: list[PairFusionResult],
    vault_packs: dict[EntityId, tuple[PriorArtBaselinePack, DomainContextPack, ConstraintDossierPack]],
    policy: FusionPolicy,
    request: FusionRequest,
    manifest_metadata: dict,
) -> FusionResult:
```

**Pack merging rules:**
- **Baseline merge:** union of entries from all vaults. Dedup by provenance-aware fingerprint (canonical claim/page ID, not text). Policy-filtered per ExtractionPolicy baseline rules.
- **Context merge:** union, dedup by provenance fingerprint, cap per category from policy.
- **Dossier merge:** union, dedup by fingerprint, governance-grade filter.

Provenance-aware dedup: entries with the same canonical claim ID or page ID across vaults are merged (not duplicated). Entries with different IDs but similar text are flagged as potential overlaps but kept (conservative).

---

## FusionOrchestrator

### `fusion/orchestrator.py`

```python
class FusionOrchestrator:
    """Orchestrates the three-stage fusion pipeline."""
    
    def __init__(
        self,
        uow_factory: Callable[[], AbstractUnitOfWork],
        context_assembler: VaultContextAssembler,
        fusion_analyzer: FusionAnalyzer,
        embedding_index: EmbeddingIndex,
        policy: FusionPolicy | None = None,
        default_actor: ActorRef = ActorRef.system(),
    ) -> None: ...

    async def fuse(self, request: FusionRequest) -> FusionResult:
        """Execute full fusion pipeline.
        
        1. Validate request (vault_ids exist, >= 2 vaults)
        2. Assemble context packs from each vault
        3. For each vault pair:
           a. Stage 1: generate bridge candidates
           b. Stage 2: analyze via FusionAnalyzer
           c. Build PairFusionResult
        4. Stage 3: synthesize aggregate FusionResult
        5. Persist FusionRun + FusionManifest
        6. Emit events
        7. Return FusionResult
        """
```

---

## FusionPolicy

```python
@dataclass
class FusionPolicy:
    policy_version: str = "1.0.0"
    max_candidates_per_pair: int = 50
    candidate_type_allocation: dict[str, float] = field(default_factory=lambda: {
        "concept": 0.4, "mechanism": 0.3, "claim_cluster": 0.2, "exploratory": 0.1,
    })
    similarity_bands: list[tuple[float, float]] = field(default_factory=lambda: [
        (0.7, 1.0), (0.5, 0.7), (0.3, 0.5),
    ])
    min_similarity_threshold: float = 0.3
    max_analogical_maps: int = 20
    max_transfer_opportunities: int = 10
    # Epistemic (inherit ExtractionPolicy patterns)
    baseline_min_claim_status: ClaimStatus = ClaimStatus.SUPPORTED
    context_include_hypothesis: bool = True
    dossier_include_unresolved: bool = True
    # Problem relevance boost
    problem_relevance_weight: float = 0.3
```

---

## Events

Add to `EVENT_TAXONOMY`:
```
fusion.requested
fusion.candidates_generated
fusion.analysis_completed
fusion.synthesis_completed
fusion.completed
fusion.failed
fusion.partial_completed
fusion.persisted
```

---

## Repository Extensions

```
repository/
    fusion_run_repo.py          # FusionRun CRUD + query by vault pair
    embedding_cache_repo.py     # Embedding cache persistence
store/sqlite/
    fusion_run_repo.py
    embedding_cache_repo.py
    schema.py                   # + fb_fusion_runs, fb_embedding_cache tables
```

UoW needs: `fusion_runs`, `embedding_cache` accessors.

---

## What Gets Implemented

1. Shared contracts (`contracts/`): FusionRequest, FusionResult, PairFusionResult, VaultSummary, QueryResult stubs, AgentTask stubs
2. Fusion domain model: BridgeCandidate, AnalogicalMap, TransferOpportunity, FusionManifest, FusionRun
3. Fusion enums: FusionMode, BridgeCandidateKind, AnalogyVerdict
4. FusionPolicy dataclass
5. EmbeddingIndex with persistent cache
6. Stage 1: `generate_bridge_candidates()` with typed diversified selection
7. FusionAnalyzer ABC + AnthropicFusionAnalyzer + MockFusionAnalyzer
8. Stage 3: `synthesize_fusion_result()` with provenance-aware pack merging
9. FusionOrchestrator: full pipeline
10. FusionRun persistence (durable artifact)
11. Repository extensions + schema
12. Event taxonomy extensions
13. Factory wiring
14. E2E test: two-vault fusion with bridge detection, pack merging, poisoning guard

### Minimum Real Flows

1. Create vault A (battery materials) + vault B (logistics), compile both
2. Fuse A + B → bridge candidates across concept/mechanism types
3. FusionAnalyzer validates → AnalogicalMaps with STRONG/WEAK/NO verdicts
4. Transfer opportunities identified (with problem relevance if problem provided)
5. Fused packs: baseline (strict merge), context (broad merge), dossier (governance)
6. FusionRun persisted as durable queryable artifact
7. FusionManifest with pair-level sub-manifests + analyzer call records
8. Poisoning guard: CONTESTED content from vault A NOT in fused baseline
9. Problem-aware: fusion with problem produces different ranking than without

### What Is NOT In Sub-project 5a

- CLI/REPL surface (5b)
- Multi-agent knowledge teams (5c)
- Web UI (5d)
- Pantheon review of fusion outputs (future enhancement)
