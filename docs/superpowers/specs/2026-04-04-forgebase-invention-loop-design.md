# ForgeBase Sub-project 4: Genesis/DeepForge/Pantheon Integration — Design Spec

## Overview

This spec covers the closed-loop knowledge feedback system between ForgeBase and Hephaestus's invention stack. It upgrades shallow artifact dumping into deep structured ingestion (Flow B), builds vault knowledge extraction for invention runs (Flow A), and enforces epistemic filtering to prevent loop poisoning.

### Goal

Make ForgeBase materially improve every invention run, and make every invention run materially enrich the vault — with governance that keeps the loop clean.

### Architectural Stance

Sub-project 4 is not "vault-aware invention" or "artifact ingestion." It is the **closed-loop knowledge feedback system**. The hard problem is epistemic filtering: what knowledge is allowed to influence future invention runs, under what trust tier, and into which injection channel.

---

## Locked Architectural Decisions

### 1. Closed Loop with B-First Sequencing

- **Flow B (invention → vault):** Deep structured ingestion — invention pages, claims, concept candidates, Pantheon artifacts, research sources, all with explicit epistemic state.
- **Flow A (vault → invention):** Vault knowledge extraction — three products with different trust levels per injection channel.
- **Loop governance:** Epistemic filtering policy preventing loop poisoning.
- Flow B is implemented first because Flow A is only as good as the vault content.

### 2. All Invention Outputs Get Pages

Every meaningful invention output produces a `PageType.INVENTION` page — not just verified ones. Pages carry an `InventionEpistemicState` lifecycle:
- `PROPOSED` → `REVIEWED` → `VERIFIED` / `CONTESTED` / `REJECTED`
- The governance layer decides what can influence future runs, not page existence.
- REJECTED inventions remain for anti-rediscovery awareness.

### 3. Novelty and Fidelity Are Not Epistemic Confidence

Novelty scores and fidelity scores are **artifact quality metrics** stored on the invention/run record. Epistemic confidence is derived separately from: evidence coverage, verifier strength, Pantheon consensus, objection resolution, source trust tier.

### 4. Pantheon Artifacts Stay First-Class

Canon, dossier, verdict, and objections remain as real Pantheon artifact records. Derived claims/views may be created for searchability, but the authoritative objects preserve their original lifecycle and semantics. Objections are not collapsed into plain claims.

### 5. Generated Provenance ≠ Empirical Support

Invention claims are explicitly `GENERATED` or `DERIVED`. The run trace is generation provenance, not external empirical evidence. When invention claims are structurally derived from vault claims or research sources, derivation links are attached separately. This distinction survives ingestion, promotion, and extraction.

### 6. Strict Channels Consume Structured Objects, Not Strings

Extraction packs have typed internal entries with origin_kind, claim_ids, page_ids, source_refs, epistemic_state, trust_tier, and salience. Rendering to strings happens at the injection boundary, not in the domain model.

### 7. Promotion Is an Explicit Step

Claims are not silently promoted to SUPPORTED. A `PromotionService` performs explicit checks: invention state eligible, no open contested objections, required support/derivation links exist, lint pass succeeded, trust thresholds met.

### 8. Research Outputs Require Pipeline Processing

Research adapter outputs become Flow A-eligible only after normal ingest + Tier 1/Tier 2 processing, not immediately on arrival.

### 9. Integration Syncs Are Durable and Decoupled

ForgeBase ingestion failures do not mark upstream runs as failed. Every sync gets its own record with retry state. The original invention/research run succeeds independently.

---

## Module Organization

```
src/hephaestus/forgebase/
  integration/
    bridge.py                      # EXISTING — interface unchanged
    genesis_adapter.py             # MODIFY — delegates to invention_ingester
    pantheon_adapter.py            # MODIFY — delegates to pantheon_ingester
    research_adapter.py            # MODIFY — durable follow-on scheduling
    invention_ingester.py          # CREATE — structured invention → pages/claims/links
    pantheon_ingester.py           # CREATE — structured Pantheon → artifacts/claims
    promotion.py                   # CREATE — PromotionService for claim promotion

  extraction/
    __init__.py                    # CREATE
    assembler.py                   # CREATE — VaultContextAssembler
    baseline_pack.py               # CREATE — PriorArtBaselinePack extraction
    context_pack.py                # CREATE — DomainContextPack extraction
    dossier_pack.py                # CREATE — ConstraintDossierPack extraction
    policy.py                      # CREATE — ExtractionPolicy + filtering rules
    models.py                      # CREATE — PackEntry, typed pack dataclasses
```

---

## New Domain Model

### Enumerations

```
InventionEpistemicState  — PROPOSED, REVIEWED, VERIFIED, CONTESTED, REJECTED
ProvenanceKind           — GENERATED, DERIVED, EMPIRICAL, INHERITED
```

Add to existing `LinkKind`:
```
MOTIVATED_BY, MAPS_TO, DERIVES_FROM, PRIOR_ART_OF, CONSTRAINED_BY, CHALLENGED_BY
```

### Invention Page Extensions

Invention pages (`PageType.INVENTION`) get additional metadata stored in a new entity:

```
InventionPageMeta:
    page_id              : EntityId
    invention_state      : InventionEpistemicState
    run_id               : str
    run_type             : str          # genesis, pantheon
    models_used          : list[str]
    novelty_score        : float | None  # artifact quality metric, not confidence
    fidelity_score       : float | None  # artifact quality metric, not confidence
    domain_distance      : float | None
    source_domain        : str | None
    target_domain        : str | None
    pantheon_verdict     : str | None
    pantheon_outcome_tier: str | None
    pantheon_consensus   : bool | None
    objection_count_open : int
    objection_count_resolved: int
    total_cost_usd       : float
    created_at           : datetime
    updated_at           : datetime
```

### Pack Entry (typed internal structure)

```
PackEntry:
    text                 : str          # renderable description
    origin_kind          : str          # concept_page, mechanism_page, invention, objection, research, etc.
    claim_ids            : list[EntityId]
    page_ids             : list[EntityId]
    source_refs          : list[EntityId]
    epistemic_state      : str          # supported, hypothesis, contested, etc.
    trust_tier           : str          # authoritative, standard, low
    salience             : float        # 0.0-1.0 relevance ranking
    provenance_kind      : ProvenanceKind
```

### Extraction Pack Dataclasses

```
PriorArtBaselinePack:
    entries              : list[PackEntry]
    vault_id             : EntityId
    vault_revision_id    : VaultRevisionId
    branch_id            : EntityId | None
    extraction_policy_version: str
    assembler_version    : str
    extracted_at         : datetime

DomainContextPack:
    concepts             : list[PackEntry]
    mechanisms           : list[PackEntry]
    open_questions       : list[PackEntry]
    explored_directions  : list[PackEntry]  # summaries only for rejected
    vault_id             : EntityId
    vault_revision_id    : VaultRevisionId
    branch_id            : EntityId | None
    extraction_policy_version: str
    assembler_version    : str
    extracted_at         : datetime

ConstraintDossierPack:
    hard_constraints     : list[PackEntry]
    known_failure_modes  : list[PackEntry]
    validated_objections : list[PackEntry]
    unresolved_controversies: list[PackEntry]
    competitive_landscape: list[PackEntry]
    vault_id             : EntityId
    vault_revision_id    : VaultRevisionId
    branch_id            : EntityId | None
    extraction_policy_version: str
    assembler_version    : str
    extracted_at         : datetime
```

### ExtractionPolicy

```python
@dataclass
class ExtractionPolicy:
    policy_version: str = "1.0.0"
    assembler_version: str = "1.0.0"
    
    # Prior-art baseline channel (strictest)
    baseline_min_external_source_trust: SourceTrustTier = SourceTrustTier.AUTHORITATIVE
    baseline_min_internal_invention_state: InventionEpistemicState = InventionEpistemicState.VERIFIED
    baseline_min_claim_status: ClaimStatus = ClaimStatus.SUPPORTED
    baseline_include_hypothesis: bool = False
    baseline_include_contested: bool = False
    
    # Domain context channel (broadest)
    context_include_hypothesis: bool = True
    context_include_contested: bool = True
    context_include_open_questions: bool = True
    context_include_prior_directions: bool = True
    context_max_concepts: int = 50
    context_max_mechanisms: int = 30
    context_max_open_questions: int = 20
    context_max_explored_directions: int = 20
    
    # Constraint dossier channel (governance-grade)
    dossier_min_claim_status: ClaimStatus = ClaimStatus.SUPPORTED
    dossier_include_resolved_objections: bool = True
    dossier_include_unresolved_controversies: bool = True
    dossier_include_failure_modes: bool = True
    dossier_max_claim_age_days: int | None = None
```

---

## Flow B: Deep Output Ingestion

### InventionIngester

Replaces the shallow Genesis adapter logic. Called by `GenesisAdapter.handle_genesis_completed()`.

```
Input: vault_id, run_id, InventionReport (or dict)

1. Create KnowledgeRunRef (sync tracking record)
2. For EACH verified/unverified invention in the report:
   a. Create Page (PageType.INVENTION)
      - page_key: "inventions/{run_slug}/{invention_slug}"
      - Content: rendered markdown (mechanism, mapping, architecture, roadmap, limitations)
   b. Create InventionPageMeta
      - invention_state: PROPOSED (always starts here)
      - novelty/fidelity as quality metrics, NOT confidence
      - run provenance fields
   c. Extract claims (GENERATED provenance):
      - Mechanism claims → status=HYPOTHESIS, support_type=GENERATED
      - Mapping claims → status=HYPOTHESIS, support_type=GENERATED
      - Architecture claims → status=HYPOTHESIS, support_type=GENERATED
      - Each claim gets ClaimSupport linking to the run (generation provenance, not empirical)
   d. Extract concept candidates from the invention
   e. Create Links with rich taxonomy:
      - MOTIVATED_BY: invention page → problem concept page
      - MAPS_TO: source domain concept → target domain concept
      - DERIVES_FROM: invention claims → vault claims that informed the run
      - PRIOR_ART_OF: invention → related prior art pages
3. Record all artifacts via KnowledgeRunArtifact
4. Update sync status
```

### PantheonIngester

Replaces the shallow Pantheon adapter logic.

```
Input: vault_id, run_id, PantheonState (or dict), invention_page_id

1. Create KnowledgeRunRef for the Pantheon run
2. Ingest AthenaCanon as structured artifact:
   - Store as vault artifact (not just dumped source)
   - Derive constraint claims from mandatory_constraints
   - Derive anti-goal claims
   - Link to invention page via CONSTRAINED_BY
3. Ingest HermesDossier as structured artifact:
   - Store competitor_patterns, ecosystem_constraints
   - Link to relevant vault concept pages
4. Record verdict on InventionPageMeta:
   - Update invention_state based on outcome:
     UNANIMOUS_CONSENSUS → REVIEWED (pending verification)
     QUALIFIED_CONSENSUS → REVIEWED
     FAIL_CLOSED → REJECTED
   - Store pantheon_verdict, outcome_tier, consensus flag
5. Ingest objections:
   - Each PantheonObjection → claim with CHALLENGED_BY link to invention claim
   - Open objections → invention claim status=CONTESTED
   - Resolved objections → provenance record preserved
   - objection_count_open and objection_count_resolved updated on meta
6. Update sync status
```

### Research Adapter Upgrade

```
Input: vault_id, run_id, research artifacts

1. Register source artifacts with KnowledgeRunRef
2. Schedule durable ingest jobs (NOT inline processing):
   - Each research artifact → IngestService.ingest_source() job
   - After ingest → Tier 1 compilation job (normal pipeline)
   - Research outputs become Flow A eligible ONLY after Tier 1/Tier 2 processing
3. Track follow-on jobs in sync record
```

### Epistemic State Mapping (Flow B)

| Event | InventionPageMeta.invention_state | Claim Status |
|---|---|---|
| Genesis completes | PROPOSED | HYPOTHESIS (all claims) |
| Pantheon UNANIMOUS | REVIEWED | HYPOTHESIS (high confidence) |
| Pantheon QUALIFIED | REVIEWED | HYPOTHESIS |
| Pantheon FAIL_CLOSED | REJECTED | CONTESTED |
| Pantheon objection (open) | stays current | CONTESTED on challenged claims |
| Pantheon objection (resolved) | stays current | Objection claim → provenance preserved |
| Verifier passes | VERIFIED | Still HYPOTHESIS until promotion |
| PromotionService runs | stays VERIFIED | Eligible claims → SUPPORTED |

---

## Flow A: Vault Knowledge Extraction

### VaultContextAssembler

```python
class VaultContextAssembler:
    """Extracts structured knowledge from a vault for invention runs."""

    def __init__(
        self,
        uow_factory: Callable[[], AbstractUnitOfWork],
        policy: ExtractionPolicy | None = None,
    ) -> None: ...

    async def assemble_prior_art_pack(
        self, vault_id: EntityId, workbook_id: EntityId | None = None,
    ) -> PriorArtBaselinePack: ...

    async def assemble_domain_context_pack(
        self, vault_id: EntityId, workbook_id: EntityId | None = None,
    ) -> DomainContextPack: ...

    async def assemble_constraint_dossier_pack(
        self, vault_id: EntityId, workbook_id: EntityId | None = None,
    ) -> ConstraintDossierPack: ...

    async def assemble_all(
        self, vault_id: EntityId, workbook_id: EntityId | None = None,
    ) -> tuple[PriorArtBaselinePack, DomainContextPack, ConstraintDossierPack]: ...
```

### Injection Boundary Renderers

At the boundary where packs meet the existing Hephaestus injection points, render structured entries to the formats those APIs expect:

```python
def render_baseline_pack_to_blocked_paths(pack: PriorArtBaselinePack) -> list[str]:
    """Render typed PackEntry objects to plain strings for extra_blocked_paths."""

def render_context_pack_to_reference_context(pack: DomainContextPack) -> dict[str, Any]:
    """Render to reference_context dict for LensSelector."""

def render_dossier_pack_to_baseline_dossier(pack: ConstraintDossierPack) -> Any:
    """Render to BaselineDossier-compatible object for Pantheon."""
```

### DomainContextPack Caps

Rejected inventions enter `explored_directions` as **summaries only** (title + source domain + one-line mechanism), not full mechanism text. All categories have policy-driven max counts with salience-based ranking.

---

## PromotionService

Explicit promotion step — claims are never silently promoted.

```python
class PromotionService:
    """Promotes invention claims from HYPOTHESIS to SUPPORTED after verification."""

    def __init__(
        self,
        uow_factory: Callable[[], AbstractUnitOfWork],
        default_actor: ActorRef,
    ) -> None: ...

    async def evaluate_promotion(
        self, page_id: EntityId, vault_id: EntityId,
    ) -> PromotionResult:
        """Check if an invention page's claims are eligible for promotion.
        
        Checks:
        1. InventionPageMeta.invention_state == VERIFIED
        2. No open CONTESTED objections on the page's claims
        3. Required ClaimSupport/ClaimDerivation links exist
        4. Source trust tier meets threshold
        5. Optionally: lint pass succeeded for this page
        
        Returns PromotionResult with eligible_claims and blocked_reasons.
        """

    async def promote_claims(
        self, page_id: EntityId, vault_id: EntityId,
        claim_ids: list[EntityId] | None = None,
    ) -> list[EntityId]:
        """Promote eligible claims from HYPOTHESIS to SUPPORTED.
        Returns list of promoted claim IDs.
        """
```

```
PromotionResult:
    page_id              : EntityId
    eligible_claims      : list[EntityId]
    blocked_claims       : list[tuple[EntityId, str]]  # (claim_id, reason)
    overall_eligible     : bool
```

---

## Loop Safety Rules (frozen)

1. **GENERATED claims never auto-become SUPPORTED.** Requires explicit PromotionService.
2. **CONTESTED claims never enter extra_blocked_paths.** Would wrongly prohibit disputed directions.
3. **REJECTED inventions stay in vault** — only in domain context pack as explored-direction summaries.
4. **Novelty/fidelity are quality metrics**, never epistemic confidence.
5. **Epistemic confidence** derived from: evidence coverage, verifier strength, Pantheon consensus, objection resolution, source trust.
6. **Unresolved controversies** enter constraint dossier explicitly labeled — never silently promoted.
7. **Research outputs** become Flow A eligible only after ingest + Tier 1/Tier 2 processing.
8. **Every extraction pack** is revision-pinned and policy-versioned for reproducibility.

---

## Integration Sync Records

Every integration write-back persists:
- `upstream_system` (genesis, pantheon, research)
- `upstream_run_id`
- `artifact_ids` created
- `sync_status` (PENDING, SYNCED, FAILED, RETRYING)
- `retry_count`
- `last_error`
- `synced_at`

Already supported by the existing `KnowledgeRunRef` + `KnowledgeRunArtifact` model from Sub-project 1.

---

## Repository Extensions

```
repository/
    invention_meta_repo.py          # CREATE — InventionPageMeta CRUD
store/sqlite/
    invention_meta_repo.py          # CREATE
```

Existing repos used: pages, claims, claim_supports, claim_derivations, links, concept_candidates, run_refs, run_artifacts.

UoW needs: `invention_meta` accessor.

---

## What Gets Implemented

### Flow B (Deep Ingestion)
- InventionIngester — structured page/claim/concept/link creation
- PantheonIngester — first-class canon/dossier/verdict/objection artifacts
- Research adapter upgrade — durable follow-on scheduling
- InventionPageMeta entity + repo + SQLite implementation
- Extended LinkKind (6 new semantic edge types)
- Epistemic state mapping per outcome type

### Flow A (Knowledge Extraction)
- VaultContextAssembler with three extraction methods
- PriorArtBaselinePack extraction (strictest channel)
- DomainContextPack extraction (broadest, capped, salience-ranked)
- ConstraintDossierPack extraction (governance-grade)
- PackEntry typed internal structure
- ExtractionPolicy with per-channel trust filters
- Injection boundary renderers (pack → API format)

### Loop Governance
- PromotionService with explicit eligibility checks
- InventionEpistemicState lifecycle
- Loop safety rules enforced in extraction policy
- Poisoning guard: contested/rejected never in strict channels

### Infrastructure
- Schema extensions for InventionPageMeta + new link kinds
- Factory wiring
- E2E closed-loop test

### Minimum Real Flows
1. Genesis run with vault_id → invention page (PROPOSED) + claims + concepts + links
2. Pantheon deliberation → page updated (REVIEWED) + canon/dossier/objection artifacts
3. Verification → page updated (VERIFIED)
4. PromotionService → eligible claims promoted to SUPPORTED
5. Extract PriorArtBaselinePack → only SUPPORTED + VERIFIED inventions
6. Extract DomainContextPack → includes hypotheses, open questions, explored directions
7. Extract ConstraintDossierPack → constraints + failures + validated objections
8. Genesis run WITH vault context → enriched pressure + lens selection + dossier
9. **Poisoning guard:** CONTESTED invention claims NOT in baseline pack, REJECTED not in dossier

### What Is NOT In Sub-project 4
- Multi-agent knowledge teams (Sub-project 5)
- Cross-vault fusion (Sub-project 5)
- Web UI (Sub-project 5)
- Full CLI surface (Sub-project 5)
