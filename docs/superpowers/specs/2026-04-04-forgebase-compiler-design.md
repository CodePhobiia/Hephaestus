# ForgeBase Sub-project 2: Ingestion + Compiler + Provenance Realization — Design Spec

## Overview

This spec covers Sub-project 2 of ForgeBase: the source normalization pipeline, the two-tier compiler (per-source extraction + vault-wide synthesis), the CompilerBackend abstraction, research augmentation integration, and the compile manifest / dirty-tracking system. It builds on the Foundation Platform (Sub-project 1, 348 tests, fully operational).

### Goal

Turn a pile of ingested sources into a living, structured, evidence-grounded knowledge base — with claim-level provenance, candidate concept extraction, and vault-wide synthesis into canonical pages.

### Architectural Stance

The compiler is a **truth-seeking, structured, repeatable extraction system**. It is explicitly not DeepForge. DeepForge destabilizes model output for novelty; the compiler stabilizes it for accuracy. These are different jobs and must never share machinery.

---

## Locked Architectural Decisions

### 1. Two-Tier Compiler

- **Tier 1 (Source Compilation)**: Event-driven, per-source. Produces source cards, claims, concept candidates, source-local relations, dirty markers. Triggered by `source.normalized`.
- **Tier 2 (Vault Synthesis)**: Manifest-driven, vault-wide. Produces concept/mechanism/comparison/timeline/open-question pages, global graph updates. Triggered by coalescing (dirty threshold, debounce, or manual request).
- **"Compile vault"** = drain pending Tier 1 work, then run Tier 2 synthesis.
- Both tiers compile into the **target branch state**, not implicitly into canonical.

### 2. CompilerBackend Abstraction

- Abstract `CompilerBackend` interface injected at composition time.
- First concrete backend: structured extraction optimized for low variance, JSON schema enforcement, validate/repair, deterministic prompts.
- DeepForge adapters are never used for compilation.
- Perplexity is a separate `ResearchAugmentor`, not the compiler core.

### 3. ConceptCandidate as Immutable Extraction Artifact

- First-class queryable entity, not a claim or manifest blob.
- Branch-scoped, source-version-scoped, evidence-linked.
- Immutable: recompile produces new candidates, marks old as SUPERSEDED.
- Resolved by Tier 2 into canonical concept pages.
- Evidence tracked via `ConceptCandidateEvidence` relation, not generic Links.

### 4. Source Card as Compiled View

- Source card is generated AFTER claim and concept extraction, not in parallel.
- The source card is a compiled view over the extracted primitives plus the normalized source — not an independent competing interpretation.

### 5. Claim Status Semantics

- Claims directly supported by a source passage are `SUPPORTED` regardless of extraction confidence. Extraction confidence lives in evidence grade / ClaimSupport.strength, not in ClaimStatus.
- `HYPOTHESIS` is reserved for speculative or synthesized claims without direct source backing.
- `INFERRED` is for claims logically derived from multiple supported claims.

### 6. Evidence Segment Refs

- Evidence provenance uses stable segment references into the normalized artifact (offset, length, or section identifier), not raw text strings as the primary handle.
- Preview text is stored as a convenience field; the segment ref is the durable link.

### 7. Dirty Marker Dedup

- One active dirty marker per `(vault_id, workbook_id, target_kind, target_key)`.
- Upsert semantics: first_dirtied_at preserved, last_dirtied_at and times_dirtied updated, latest source/job refs overwritten.
- Tier 2 consumes the consolidated marker, not a pile of duplicates.

### 8. Policy-Driven Clustering

- Concept clustering thresholds and promotion rules live in versioned synthesis policy, not hardcoded in the compiler.
- The architecture provides the mechanism for policy-driven clustering; specific thresholds are tunable without code changes.

### 9. Research Augmentation as Follow-On Work

- Tier 2 detects evidence gaps and schedules follow-on durable `source_discovery` / `ingest_source` jobs.
- The current synthesis run closes cleanly. New sources enter Tier 1 later.
- Augmentor results never recursively expand a synthesis transaction.

### 10. No-Op Version Rule

- If synthesis output is semantically unchanged from the current page version, no new page version is created.
- Content hash comparison determines whether an update is needed.
- This prevents version churn from re-synthesis runs.

---

## Module Organization

```
src/hephaestus/forgebase/
  ingestion/                        # Source normalization (format → clean markdown)
    __init__.py
    normalization.py                # NormalizationPipeline: dispatch by format
    pdf.py                          # PDF → markdown
    html.py                         # HTML → markdown (extends existing research/ingestion.py patterns)
    markdown_normalizer.py          # Markdown cleanup / section splitting
    images.py                       # Image description extraction (stub for now)

  compiler/                         # Application/orchestration layer (owns UoW scope)
    __init__.py
    backend.py                      # CompilerBackend ABC
    models.py                       # Extraction result schemas + backend call metadata
    prompts/
      __init__.py
      claim_extraction.py           # Versioned prompt templates with prompt_id + version metadata
      concept_extraction.py
      source_card.py
      evidence_grading.py
      synthesis.py                  # Tier 2 synthesis prompts
    backends/
      __init__.py
      anthropic_backend.py          # First concrete CompilerBackend (Claude, structured output)
    tier1.py                        # SourceCompiler — per-source extraction orchestrator
    tier2.py                        # VaultSynthesizer — vault-wide synthesis orchestrator
    manifest.py                     # Manifest models (already in domain, this is manifest logic)
    dirty.py                        # Dirty-tracking logic (upsert, consume, coalesce)
    policy.py                       # Versioned synthesis policies (clustering thresholds, promotion rules)

  research/                         # Research augmentation (separate from compiler core)
    __init__.py
    augmentor.py                    # ResearchAugmentor ABC
    perplexity_augmentor.py         # Perplexity-backed implementation
```

### New Domain Model Additions (`domain/`)

```
domain/enums.py           # + CandidateKind, CandidateStatus, DirtyTargetKind, CompilePhase
domain/models.py          # + ConceptCandidate, ConceptCandidateEvidence,
                          #   SourceCompileManifest, VaultSynthesisManifest,
                          #   SynthesisDirtyMarker, EvidenceSegmentRef,
                          #   BackendCallRecord
```

### New Repository Contracts + Store Implementations

```
repository/
  concept_candidate_repo.py
  candidate_evidence_repo.py
  compile_manifest_repo.py
  dirty_marker_repo.py

store/sqlite/
  concept_candidate_repo.py
  candidate_evidence_repo.py
  compile_manifest_repo.py
  dirty_marker_repo.py

  # Join tables for manifest associations:
  # fb_synthesis_source_manifests (synthesis_manifest_id, source_manifest_id)
  # fb_synthesis_pages_created (synthesis_manifest_id, page_id)
  # fb_synthesis_pages_updated (synthesis_manifest_id, page_id)
  # fb_synthesis_dirty_consumed (synthesis_manifest_id, marker_id)
```

### Layer Dependency Rules

| Layer | May Import | Notes |
|-------|-----------|-------|
| `ingestion/` | `domain/`, `repository/` | Normalization pipeline, owns its UoW scope |
| `compiler/` | `domain/`, `repository/` | Application/orchestration, owns UoW scope directly |
| `compiler/backend.py` | `compiler/models.py` only | ABC — no repo/service imports |
| `compiler/backends/` | `compiler/backend.py`, `compiler/models.py`, `compiler/prompts/` | Concrete implementations |
| `compiler/tier1.py` | `domain/`, `repository/`, `compiler/backend.py`, `compiler/models.py` | Orchestrates extraction |
| `compiler/tier2.py` | `domain/`, `repository/`, `compiler/backend.py`, `compiler/models.py`, `compiler/policy.py` | Orchestrates synthesis |
| `research/` | `domain/`, `repository/` | Research augmentor, independent of compiler |

---

## New Domain Model

### Enumerations

```
CandidateKind     — CONCEPT, ENTITY, MECHANISM, TERM
CandidateStatus   — ACTIVE, CLUSTERED, PROMOTED, REJECTED, SUPERSEDED
DirtyTargetKind   — CONCEPT, MECHANISM, COMPARISON, TIMELINE, OPEN_QUESTION, SOURCE_INDEX
CompilePhase      — TIER1_EXTRACTION, TIER1_PERSIST, TIER2_CLUSTER, TIER2_SYNTHESIZE, TIER2_GRAPH
```

### EvidenceSegmentRef (value object)

Stable reference into a normalized source artifact.

| Field | Type | Notes |
|-------|------|-------|
| `source_id` | `EntityId` | |
| `source_version` | `Version` | |
| `segment_start` | `int` | Character offset into normalized content |
| `segment_end` | `int` | Character offset end |
| `section_key` | `str \| None` | Optional section identifier (e.g., "3.2") |
| `preview_text` | `str` | Convenience — first ~200 chars of segment |

### BackendCallRecord (value object)

Metadata for every CompilerBackend invocation, persisted in manifests.

| Field | Type | Notes |
|-------|------|-------|
| `model_name` | `str` | e.g., "claude-sonnet-4-5" |
| `backend_kind` | `str` | e.g., "anthropic" |
| `prompt_id` | `str` | e.g., "claim_extraction" |
| `prompt_version` | `str` | e.g., "1.0.0" |
| `schema_version` | `int` | |
| `repair_invoked` | `bool` | Whether validate/repair pass was needed |
| `input_tokens` | `int` | |
| `output_tokens` | `int` | |
| `duration_ms` | `int` | |
| `raw_output_ref` | `BlobRef \| None` | Optional ref to raw model output for audit |

### ConceptCandidate

| Field | Type | Notes |
|-------|------|-------|
| `candidate_id` | `EntityId` | |
| `vault_id` | `EntityId` | |
| `workbook_id` | `EntityId \| None` | Branch scope |
| `source_id` | `EntityId` | |
| `source_version` | `Version` | |
| `source_compile_job_id` | `EntityId` | |
| `name` | `str` | |
| `normalized_name` | `str` | Lowercase, stripped canonical form |
| `aliases` | `list[str]` | |
| `candidate_kind` | `CandidateKind` | |
| `confidence` | `float` | |
| `salience` | `float` | How central to the source |
| `status` | `CandidateStatus` | |
| `resolved_page_id` | `EntityId \| None` | Set when promoted to concept page |
| `compiler_policy_version` | `str` | |
| `created_at` | `datetime` | |

### ConceptCandidateEvidence

| Field | Type | Notes |
|-------|------|-------|
| `evidence_id` | `EntityId` | |
| `candidate_id` | `EntityId` | |
| `segment_ref` | `EvidenceSegmentRef` | Stable ref into normalized source |
| `role` | `str` | DEFINITION, USAGE, EXAMPLE, RELATIONSHIP |
| `created_at` | `datetime` | |

### SynthesisDirtyMarker

One active marker per `(vault_id, workbook_id, target_kind, target_key)`. Upsert semantics.

| Field | Type | Notes |
|-------|------|-------|
| `marker_id` | `EntityId` | |
| `vault_id` | `EntityId` | |
| `workbook_id` | `EntityId \| None` | |
| `target_kind` | `DirtyTargetKind` | |
| `target_key` | `str` | Normalized concept name or page family key |
| `first_dirtied_at` | `datetime` | Preserved on upsert |
| `last_dirtied_at` | `datetime` | Updated on upsert |
| `times_dirtied` | `int` | Incremented on upsert |
| `last_dirtied_by_source` | `EntityId` | |
| `last_dirtied_by_job` | `EntityId` | |
| `consumed_by_job` | `EntityId \| None` | Set when Tier 2 consumes |
| `consumed_at` | `datetime \| None` | |

### SourceCompileManifest

| Field | Type | Notes |
|-------|------|-------|
| `manifest_id` | `EntityId` | |
| `vault_id` | `EntityId` | |
| `workbook_id` | `EntityId \| None` | |
| `source_id` | `EntityId` | |
| `source_version` | `Version` | |
| `job_id` | `EntityId` | |
| `compiler_policy_version` | `str` | |
| `prompt_versions` | `dict[str, str]` | prompt_id → version |
| `backend_calls` | `list[BackendCallRecord]` | All LLM calls made |
| `claim_count` | `int` | |
| `concept_count` | `int` | |
| `relationship_count` | `int` | |
| `source_content_hash` | `ContentHash` | Hash of normalized source input |
| `created_at` | `datetime` | |

### VaultSynthesisManifest

| Field | Type | Notes |
|-------|------|-------|
| `manifest_id` | `EntityId` | |
| `vault_id` | `EntityId` | |
| `workbook_id` | `EntityId \| None` | |
| `job_id` | `EntityId` | |
| `base_revision` | `VaultRevisionId` | |
| `synthesis_policy_version` | `str` | |
| `prompt_versions` | `dict[str, str]` | |
| `backend_calls` | `list[BackendCallRecord]` | |
| `candidates_resolved` | `int` | |
| `augmentor_calls` | `int` | |
| `created_at` | `datetime` | |

Association fields (`source_manifests`, `pages_created`, `pages_updated`, `dirty_markers_consumed`) are stored as join tables in the database, not inline lists.

---

## CompilerBackend Contract

```python
class CompilerBackend(ABC):
    """Structured extraction backend for the ForgeBase compiler.
    
    Optimized for: low variance, schema validity, repeatability,
    evidence sensitivity, provenance-friendly outputs.
    
    validate_and_repair is internal to concrete backends, not part of this ABC.
    """

    # --- Tier 1: Per-source extraction ---

    @abstractmethod
    async def extract_claims(
        self, source_text: str, source_metadata: dict
    ) -> tuple[list[ExtractedClaim], BackendCallRecord]: ...

    @abstractmethod
    async def extract_concepts(
        self, source_text: str, source_metadata: dict
    ) -> tuple[list[ExtractedConcept], BackendCallRecord]: ...

    @abstractmethod
    async def generate_source_card(
        self, source_text: str, source_metadata: dict,
        extracted_claims: list[ExtractedClaim],
        extracted_concepts: list[ExtractedConcept],
    ) -> tuple[SourceCardContent, BackendCallRecord]: ...

    @abstractmethod
    async def grade_evidence(
        self, claim: str, segment_ref: EvidenceSegmentRef, source_text: str
    ) -> tuple[EvidenceGrade, BackendCallRecord]: ...

    # --- Tier 2: Vault-wide synthesis ---

    @abstractmethod
    async def synthesize_concept_page(
        self, concept_name: str, evidence: list[ConceptEvidence],
        existing_claims: list[str], related_concepts: list[str],
        policy: SynthesisPolicy,
    ) -> tuple[SynthesizedPage, BackendCallRecord]: ...

    @abstractmethod
    async def synthesize_mechanism_page(
        self, mechanism_name: str, causal_claims: list[str],
        source_evidence: list[ConceptEvidence], policy: SynthesisPolicy,
    ) -> tuple[SynthesizedPage, BackendCallRecord]: ...

    @abstractmethod
    async def synthesize_comparison_page(
        self, entities: list[str], comparison_data: list[dict],
        policy: SynthesisPolicy,
    ) -> tuple[SynthesizedPage, BackendCallRecord]: ...

    @abstractmethod
    async def synthesize_timeline_page(
        self, topic: str, temporal_claims: list[str],
        policy: SynthesisPolicy,
    ) -> tuple[SynthesizedPage, BackendCallRecord]: ...

    @abstractmethod
    async def identify_open_questions(
        self, contested_claims: list[str], evidence_gaps: list[str],
        policy: SynthesisPolicy,
    ) -> tuple[list[OpenQuestion], BackendCallRecord]: ...
```

Every method returns a `BackendCallRecord` alongside its result. The backend internally handles JSON schema enforcement, low temperature, retry on parse failure, and validate/repair. The `validate_and_repair` logic is an internal backend concern, not exposed in the ABC.

---

## Extraction Result Schemas (`compiler/models.py`)

### ExtractedClaim

| Field | Type | Notes |
|-------|------|-------|
| `statement` | `str` | The assertion |
| `segment_ref` | `EvidenceSegmentRef` | Stable ref to source passage |
| `confidence` | `float` | Extraction confidence (not epistemic status) |
| `claim_type` | `str` | factual, methodological, comparative, limitation |

### ExtractedConcept

| Field | Type | Notes |
|-------|------|-------|
| `name` | `str` | |
| `aliases` | `list[str]` | |
| `kind` | `CandidateKind` | CONCEPT, ENTITY, MECHANISM, TERM |
| `evidence_segments` | `list[EvidenceSegmentRef]` | Stable refs |
| `salience` | `float` | How central to the source |

### SourceCardContent

| Field | Type | Notes |
|-------|------|-------|
| `summary` | `str` | |
| `key_claims` | `list[str]` | Derived from extracted claims |
| `methods` | `list[str]` | |
| `limitations` | `list[str]` | |
| `evidence_quality` | `str` | |
| `concepts_mentioned` | `list[str]` | Derived from extracted concepts |

### EvidenceGrade

| Field | Type | Notes |
|-------|------|-------|
| `strength` | `float` | 0.0 - 1.0 |
| `methodology_quality` | `str` | strong, moderate, weak, unknown |
| `reasoning` | `str` | Brief justification |

### SynthesizedPage

| Field | Type | Notes |
|-------|------|-------|
| `title` | `str` | |
| `content_markdown` | `str` | Full page content |
| `claims` | `list[SynthesizedClaim]` | Claims to create/update |
| `related_concepts` | `list[str]` | Normalized names of related concepts |

### SynthesizedClaim

| Field | Type | Notes |
|-------|------|-------|
| `statement` | `str` | |
| `support_type` | `SupportType` | Usually SYNTHESIZED |
| `confidence` | `float` | |
| `derived_from_claims` | `list[str]` | Statement texts of parent claims |

### OpenQuestion

| Field | Type | Notes |
|-------|------|-------|
| `question` | `str` | |
| `context` | `str` | Why this is unresolved |
| `conflicting_claims` | `list[str]` | If contradiction-driven |
| `evidence_gap` | `str` | What's missing |

### ConceptEvidence

Aggregated evidence passed to Tier 2 synthesis methods.

| Field | Type | Notes |
|-------|------|-------|
| `source_id` | `EntityId` | |
| `source_title` | `str` | |
| `claims` | `list[str]` | Claim statements from this source about the concept |
| `segments` | `list[EvidenceSegmentRef]` | |

---

## Tier 1 Data Flow — Source Compilation

**Trigger chain:**
```
source.ingested → NormalizationJob → ingestion/normalization.py
  → IngestService.normalize_source()
    → source.normalized → SourceCompileJob
      → compiler/tier1.py (SourceCompiler)
```

**SourceCompiler flow:**

```
Input: source_id, source_version, vault_id, workbook_id

1. ACQUIRE UoW
2. READ normalized source content from ContentStore via source version's normalized_ref
3. EXTRACT (sequential, not parallel):
   a. claims = backend.extract_claims(source_text, metadata)
   b. concepts = backend.extract_concepts(source_text, metadata)
   c. source_card = backend.generate_source_card(source_text, metadata,
                                                  claims, concepts)
      Source card is compiled view over extracted primitives.

4. VALIDATE each extraction result
   - Schema validation on structured outputs
   - Backends handle repair internally
   - Drop irrecoverable extractions, log warning

5. PERSIST source card page:
   - page_key = "source-cards/{source_slug}"
   - page_type = SOURCE_CARD
   - compiled_from = [source_id]
   - Content = rendered markdown from SourceCardContent
   - NO-OP CHECK: if content hash matches existing version, skip version creation

6. PERSIST claims:
   For each ExtractedClaim:
   - Create Claim + ClaimVersion
     status = SUPPORTED (direct source evidence — always, per locked rule)
     support_type = DIRECT
     confidence = evidence grade strength (not extraction confidence)
   - Create ClaimSupport linking claim → source
     source_segment stored as EvidenceSegmentRef preview text
     strength = evidence grade strength
   - Set branch or canonical heads

7. PERSIST concept candidates:
   For each ExtractedConcept:
   - Create ConceptCandidate (status=ACTIVE)
     normalized_name = lowercase, stripped canonical form
     compiler_policy_version recorded
   - Create ConceptCandidateEvidence records with segment refs

8. PERSIST source-local links:
   - source_card page ← source (BACKLINK)
   - Claim-to-claim co-reference links where detected

9. MARK DIRTY for Tier 2 (upsert semantics):
   For each concept candidate:
   - Upsert SynthesisDirtyMarker (target_kind=CONCEPT, target_key=normalized_name)
   For the source's domain coverage:
   - Upsert dirty markers for affected MECHANISM, COMPARISON families

10. WRITE SourceCompileManifest with all backend call records

11. EMIT events + COMMIT UoW
```

### Three Job Types

| Job | Idempotency Key Pattern | Trigger |
|-----|------------------------|---------|
| `SourceCompileJob` | `"source:{source_id}:v{version}:tier1:{policy_version}"` | `source.normalized` event |
| `VaultSynthesisJob` | `"vault:{vault_id}:wb:{workbook_id_or_canonical}:tier2:{manifest_hash}:{policy_version}"` | Dirty threshold / manual / debounce |
| `FullRebuildJob` | `"vault:{vault_id}:rebuild:{policy_version}:{timestamp}"` | Manual/admin only |

---

## Tier 2 Data Flow — Vault Synthesis

**Trigger:**
```
Manual: "compile vault" → drain pending Tier 1 → VaultSynthesisJob
Auto: dirty markers accumulate → threshold/debounce → VaultSynthesisJob
```

**VaultSynthesizer flow:**

```
Input: vault_id, workbook_id, synthesis_config

1. ACQUIRE UoW
2. READ state:
   a. All ACTIVE ConceptCandidates in this branch/vault
   b. All unconsumed SynthesisDirtyMarkers
   c. Prior VaultSynthesisManifest (for incremental)
   d. All existing concept/mechanism/comparison/timeline/open-question pages

3. CLUSTER concept candidates (policy-driven):
   - Group by normalized_name similarity (threshold from policy)
   - Merge aliases across sources
   - Assign cluster confidence = aggregated from members
   - Determine which clusters deserve canonical pages (thresholds from policy)

4. For each cluster that deserves a page:

   4a. SYNTHESIZE concept page:
   - Gather ConceptEvidence across all source-grounded claims for this concept
   - If page exists: read current version, compare content hash after synthesis
   - Call backend.synthesize_concept_page(...)
   - NO-OP CHECK: if content hash unchanged, skip version creation
   - If changed: create/update Page + PageVersion
   - Create synthesized Claims (support_type=SYNTHESIZED, status=INFERRED)
   - Create ClaimDerivations linking synthesized → source claims
   - Create Links: concept ↔ related concepts (RELATED_CONCEPT), concept ← sources (BACKLINK)
   - Update ConceptCandidates: status → PROMOTED, resolved_page_id set

5. For dirty MECHANISM families:
   - backend.synthesize_mechanism_page(...)
   - Same no-op check and persist pattern

6. For dirty COMPARISON targets:
   - backend.synthesize_comparison_page(...)

7. For TIMELINE targets:
   - backend.synthesize_timeline_page(...)

8. For OPEN_QUESTION / contradiction detection:
   - Cross-reference claims with conflicting evidence
   - backend.identify_open_questions(...)
   - Create open question pages

9. RESEARCH AUGMENTATION (follow-on, not inline):
   - If evidence gaps detected during synthesis:
     Schedule durable source_discovery jobs for later execution
   - Current synthesis run completes cleanly without recursive ingest
   - New sources will enter Tier 1 pipeline later

10. UPDATE global graph:
    - Refresh backlinks for all modified pages
    - Create/update source index page
    - Refresh cross-page relationship Links

11. WRITE VaultSynthesisManifest
    - Association refs stored in join tables (source_manifests, pages_created, pages_updated, dirty_markers_consumed)
    - Prompt versions as JSON metadata
    - All backend call records

12. MARK consumed dirty markers (set consumed_by_job, consumed_at)
13. EMIT events + COMMIT UoW
```

### Scheduling Policy

| Trigger | Behavior |
|---------|----------|
| `source.normalized` | Schedule Tier 1 immediately |
| `source_compile.completed` | Upsert dirty markers |
| Dirty markers accumulate | Coalesce: debounce window OR dirty threshold → schedule Tier 2 |
| User says "compile vault" | Drain Tier 1 first, then run Tier 2 |
| Claim invalidated / major provenance change | Upsert dirty markers |

Tier 2 auto-run policy (configurable via vault config):
- Run after N dirty markers accumulated (default: 5)
- Or after T minutes of quiet after last Tier 1 completion (default: 10)
- Or immediately if user explicitly requests
- Or immediately for small vaults in local mode if policy allows

---

## ResearchAugmentor Contract

```python
class ResearchAugmentor(ABC):
    """External evidence augmentation — separate from compiler core."""

    @abstractmethod
    async def find_supporting_evidence(
        self, concept: str, evidence_gaps: list[str]
    ) -> list[DiscoveredSource]: ...

    @abstractmethod
    async def resolve_contradiction(
        self, claim_a: str, claim_b: str, context: str
    ) -> ContradictionResolution: ...

    @abstractmethod
    async def check_freshness(
        self, claim: str, last_validated: datetime
    ) -> FreshnessCheck: ...
```

`PerplexityAugmentor` wraps the existing `PerplexityClient` from `hephaestus.research.perplexity`. Used only in Tier 2, and only when evidence is incomplete. Results become follow-on durable ingest jobs, not inline ingestion.

---

## Normalization Pipeline

`forgebase/ingestion/normalization.py` dispatches by `SourceFormat`:

| Format | Handler | Output |
|--------|---------|--------|
| `MARKDOWN` | `markdown_normalizer.py` | Cleaned markdown, section splitting |
| `URL` / `HTML` | `html.py` | HTML → clean markdown (extends existing `research/ingestion.py` patterns) |
| `PDF` | `pdf.py` | PDF → markdown (using pdf extraction library) |
| `IMAGE` | `images.py` | Stub — returns image metadata, description placeholder |
| `CSV` / `JSON` | Inline | Structured summary as markdown |
| `HEPH_OUTPUT` | Inline | Already markdown — normalize formatting |
| Others | Passthrough | Store raw, mark as INGESTED (not NORMALIZED) |

Each handler produces `bytes` (normalized markdown) that gets passed to `IngestService.normalize_source()`. The normalization pipeline owns UoW scope for the normalization job. The compiler (Tier 1) receives the normalized content as input.

---

## Versioned Prompts

Each prompt module in `compiler/prompts/` exports:

```python
PROMPT_ID = "claim_extraction"
PROMPT_VERSION = "1.0.0"
SCHEMA_VERSION = 1

SYSTEM_PROMPT = "..."
USER_PROMPT_TEMPLATE = "..."
OUTPUT_SCHEMA = { ... }  # JSON schema for expected output
```

These are referenced by the backend and recorded in `BackendCallRecord` and manifests. Policy changes that affect extraction (schema changes, rubric changes, prompt rewrites) require version bumps and trigger `FullRebuildJob` eligibility.

---

## Synthesis Policy (`compiler/policy.py`)

```python
@dataclass
class SynthesisPolicy:
    policy_version: str
    # Clustering
    name_similarity_threshold: float = 0.85
    min_sources_for_promotion: int = 2
    min_salience_single_source: float = 0.8
    # Page generation
    max_claims_per_page: int = 50
    max_related_concepts: int = 20
    # Scheduling
    dirty_threshold_for_auto_synthesis: int = 5
    debounce_minutes: float = 10.0
    # Evidence
    min_evidence_strength_for_supported: float = 0.3
```

Policy is loaded from vault config or defaults. All thresholds are tunable without code changes.

---

## What Gets Implemented in Sub-project 2

### Backend
- Normalization pipeline (markdown, HTML, PDF handlers)
- CompilerBackend ABC + AnthropicCompilerBackend
- SourceCompiler (Tier 1 orchestrator)
- VaultSynthesizer (Tier 2 orchestrator)
- Versioned prompt templates (claim extraction, concept extraction, source card, evidence grading, synthesis)
- Synthesis policy system
- Dirty marker upsert/consume logic
- Compile manifest persistence
- ConceptCandidate + evidence persistence
- ResearchAugmentor ABC + PerplexityAugmentor
- Factory updates to wire new components
- Event consumers for Tier 1 / Tier 2 scheduling

### New domain entities
- ConceptCandidate, ConceptCandidateEvidence
- SourceCompileManifest, VaultSynthesisManifest
- SynthesisDirtyMarker
- EvidenceSegmentRef, BackendCallRecord (value objects)

### New repos + SQLite implementations
- ConceptCandidateRepository
- CandidateEvidenceRepository
- CompileManifestRepository
- DirtyMarkerRepository
- New join tables for manifest associations
- Schema migration for new tables

### Minimum Real Flows
1. Ingest a markdown source → normalize → Tier 1 produces source card + claims + candidates + dirty markers
2. Ingest a second source → Tier 1 runs → shared concepts detected via candidates
3. Run Tier 2 → concept pages synthesized from candidates across both sources
4. Verify claim provenance: synthesized claim → derivation → source claims → source evidence segments
5. Verify dirty markers consumed after synthesis
6. Verify no-op: re-run Tier 2 with no new sources → no new page versions created
7. Compile on workbook branch → all output branch-scoped → merge to canonical

### What Is NOT In Sub-project 2
- Lint detection intelligence (Sub-project 3)
- Genesis/DeepForge vault-aware invention (Sub-project 4)
- Multi-agent knowledge teams (Sub-project 5)
- Web UI (Sub-project 5)
- Postgres implementation (follow-up to Sub-project 1)
- Local FS content store (follow-up to Sub-project 1)
