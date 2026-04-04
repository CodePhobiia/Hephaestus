# ForgeBase Invention Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the closed-loop knowledge feedback system between ForgeBase and Hephaestus's invention stack — deep structured ingestion of invention outputs (Flow B), vault knowledge extraction for invention runs (Flow A), and epistemic filtering to prevent loop poisoning.

**Architecture:** Flow B upgrades shallow artifact dumping into structured invention pages, claims, concept candidates, Pantheon artifacts, and research sources — all with explicit epistemic state. Flow A extracts three trust-filtered products (PriorArtBaselinePack, DomainContextPack, ConstraintDossierPack) for injection into DeepForge pressure, lens selection, and Pantheon dossier. A PromotionService gates claim promotion with explicit checks. Loop safety rules prevent contested/rejected content from entering strict channels.

**Tech Stack:** Python 3.11+, aiosqlite, pytest-asyncio, existing ForgeBase (803 tests) + Hephaestus Genesis/DeepForge/Pantheon

**Spec:** `docs/superpowers/specs/2026-04-04-forgebase-invention-loop-design.md`

---

## File Structure

```
# New files to create:

src/hephaestus/forgebase/
  domain/enums.py                                  # MODIFY — add InventionEpistemicState, ProvenanceKind, 6 LinkKind values
  domain/models.py                                 # MODIFY — add InventionPageMeta, PromotionResult
  domain/event_types.py                            # MODIFY — add invention lifecycle events

  repository/invention_meta_repo.py                # CREATE — ABC
  repository/uow.py                                # MODIFY — add invention_meta accessor

  store/sqlite/schema.py                           # MODIFY — add fb_invention_page_meta table
  store/sqlite/invention_meta_repo.py              # CREATE
  store/sqlite/uow.py                              # MODIFY — wire invention_meta

  integration/
    genesis_adapter.py                             # MODIFY — delegate to invention_ingester
    pantheon_adapter.py                            # MODIFY — delegate to pantheon_ingester
    research_adapter.py                            # MODIFY — durable follow-on
    invention_ingester.py                          # CREATE — structured invention → pages/claims/links
    pantheon_ingester.py                           # CREATE — structured Pantheon → artifacts
    promotion.py                                   # CREATE — PromotionService

  extraction/
    __init__.py                                    # CREATE
    models.py                                      # CREATE — PackEntry, pack dataclasses
    policy.py                                      # CREATE — ExtractionPolicy
    assembler.py                                   # CREATE — VaultContextAssembler
    baseline_pack.py                               # CREATE — PriorArtBaselinePack extraction
    context_pack.py                                # CREATE — DomainContextPack extraction
    dossier_pack.py                                # CREATE — ConstraintDossierPack extraction
    renderers.py                                   # CREATE — pack → API format renderers

  factory.py                                       # MODIFY — wire new components

tests/test_forgebase/
  test_integration/
    test_invention_ingester.py                     # CREATE
    test_pantheon_ingester.py                      # CREATE
    test_promotion.py                              # CREATE
  test_extraction/
    __init__.py                                    # CREATE
    test_models.py                                 # CREATE
    test_policy.py                                 # CREATE
    test_baseline_pack.py                          # CREATE
    test_context_pack.py                           # CREATE
    test_dossier_pack.py                           # CREATE
    test_assembler.py                              # CREATE
    test_renderers.py                              # CREATE
  test_e2e/
    test_invention_loop.py                         # CREATE
```

---

### Task 1: Domain Extensions — Enums, InventionPageMeta, Pack Models

**Files:**
- Modify: `src/hephaestus/forgebase/domain/enums.py`
- Modify: `src/hephaestus/forgebase/domain/models.py`
- Modify: `src/hephaestus/forgebase/domain/event_types.py`
- Create: `src/hephaestus/forgebase/extraction/__init__.py`
- Create: `src/hephaestus/forgebase/extraction/models.py`
- Modify: `tests/test_forgebase/test_domain/test_enums.py`
- Modify: `tests/test_forgebase/test_domain/test_models.py`
- Create: `tests/test_forgebase/test_extraction/__init__.py`
- Create: `tests/test_forgebase/test_extraction/test_models.py`

**domain/enums.py** — Append:
```python
class InventionEpistemicState(str, Enum):
    PROPOSED = "proposed"
    REVIEWED = "reviewed"
    VERIFIED = "verified"
    CONTESTED = "contested"
    REJECTED = "rejected"

class ProvenanceKind(str, Enum):
    GENERATED = "generated"
    DERIVED = "derived"
    EMPIRICAL = "empirical"
    INHERITED = "inherited"
```

Add to existing `LinkKind`:
```python
    MOTIVATED_BY = "motivated_by"
    MAPS_TO = "maps_to"
    DERIVES_FROM = "derives_from"
    PRIOR_ART_OF = "prior_art_of"
    CONSTRAINED_BY = "constrained_by"
    CHALLENGED_BY = "challenged_by"
```

**domain/models.py** — Add `InventionPageMeta` and `PromotionResult` dataclasses with all fields from the spec.

**domain/event_types.py** — Add invention lifecycle events:
```
invention.page_created, invention.state_updated, invention.claims_extracted,
invention.promoted, pantheon.canon_ingested, pantheon.dossier_ingested,
pantheon.verdict_recorded, pantheon.objections_ingested
```

**extraction/models.py** — `PackEntry` dataclass + `PriorArtBaselinePack`, `DomainContextPack`, `ConstraintDossierPack` dataclasses with all fields from spec (entries as `list[PackEntry]`, vault_id, vault_revision_id, branch_id, policy_version, assembler_version, extracted_at).

Tests: verify enum values, model creation, pack construction.

- [ ] **Step 1-6: Write tests → implement → run full suite → commit**

```bash
git commit -m "feat(forgebase): add invention loop domain extensions — enums, InventionPageMeta, pack models"
```

---

### Task 2: InventionPageMeta Repository + Schema

**Files:**
- Create: `src/hephaestus/forgebase/repository/invention_meta_repo.py`
- Modify: `src/hephaestus/forgebase/repository/uow.py`
- Modify: `src/hephaestus/forgebase/store/sqlite/schema.py`
- Create: `src/hephaestus/forgebase/store/sqlite/invention_meta_repo.py`
- Modify: `src/hephaestus/forgebase/store/sqlite/uow.py`
- Create: `tests/test_forgebase/test_store/test_sqlite_invention_meta_repo.py`

**Repository ABC:**
```python
class InventionPageMetaRepository(ABC):
    async def create(self, meta: InventionPageMeta) -> None: ...
    async def get(self, page_id: EntityId) -> InventionPageMeta | None: ...
    async def update_state(self, page_id: EntityId, state: InventionEpistemicState) -> None: ...
    async def update_pantheon(self, page_id: EntityId, verdict: str, outcome_tier: str, 
                               consensus: bool, objection_count_open: int, 
                               objection_count_resolved: int) -> None: ...
    async def list_by_vault(self, vault_id: EntityId, state: InventionEpistemicState | None = None) -> list[InventionPageMeta]: ...
    async def list_by_state(self, vault_id: EntityId, state: InventionEpistemicState) -> list[InventionPageMeta]: ...
```

**Schema:** `fb_invention_page_meta` table with all fields, indexed on vault_id + invention_state.

**UoW:** Add `invention_meta: InventionPageMetaRepository` accessor.

Tests: CRUD, state updates, Pantheon metadata updates, list by state.

- [ ] **Step 1-6: Write tests → implement → wire UoW → commit**

```bash
git commit -m "feat(forgebase): add InventionPageMeta repo + SQLite schema"
```

---

### Task 3: InventionIngester (Flow B — Genesis Deep Ingestion)

**Files:**
- Create: `src/hephaestus/forgebase/integration/invention_ingester.py`
- Modify: `src/hephaestus/forgebase/integration/genesis_adapter.py`
- Create: `tests/test_forgebase/test_integration/test_invention_ingester.py`

The InventionIngester is the core of Flow B. It takes raw Genesis output and produces structured ForgeBase knowledge.

```python
class InventionIngester:
    """Structured ingestion of Genesis invention outputs into ForgeBase."""
    
    def __init__(
        self, uow_factory, page_service, claim_service, link_service, 
        ingest_service, run_integration_service, default_actor,
    ) -> None: ...

    async def ingest_invention_report(
        self, vault_id: EntityId, run_id: str, report: Any,
        workbook_id: EntityId | None = None,
    ) -> list[EntityId]:
        """Ingest all inventions from a Genesis report.
        
        For each invention:
        1. Create INVENTION page with rendered markdown
        2. Create InventionPageMeta (state=PROPOSED)
        3. Extract mechanism/mapping/architecture claims (HYPOTHESIS, GENERATED)
        4. Extract concept candidates
        5. Create semantic links (MOTIVATED_BY, MAPS_TO, DERIVES_FROM, PRIOR_ART_OF)
        6. Record run artifacts
        
        Returns list of created page IDs.
        """
```

Key implementation details:
- Extract invention data from `report` using `getattr(report, field, default)` for resilience (same as existing adapters)
- Render invention to markdown: mechanism, mapping table, architecture, roadmap, limitations
- Claims extracted with `support_type=SupportType.GENERATED` — generation provenance, not empirical
- Concept candidates from source domain + target domain concepts
- Links use the rich taxonomy: MOTIVATED_BY links to problem, MAPS_TO links source→target domains

Update `genesis_adapter.py` to delegate to `InventionIngester.ingest_invention_report()` instead of shallow artifact dumping.

Tests:
- test_ingest_creates_invention_page — verify PageType.INVENTION, content includes mechanism
- test_ingest_creates_meta_proposed — InventionPageMeta with state=PROPOSED
- test_ingest_creates_hypothesis_claims — claims with HYPOTHESIS status, GENERATED support_type
- test_ingest_creates_concept_candidates — concept candidates from invention
- test_ingest_creates_semantic_links — MOTIVATED_BY, MAPS_TO links
- test_ingest_records_run_artifacts — KnowledgeRunRef + artifacts
- test_ingest_handles_dict_report — report as dict (resilience)
- test_ingest_handles_missing_fields — report with missing attributes

- [ ] **Step 1-6: Write tests → implement → update adapter → commit**

```bash
git commit -m "feat(forgebase): add InventionIngester with deep structured ingestion"
```

---

### Task 4: PantheonIngester (Flow B — Pantheon Deep Ingestion)

**Files:**
- Create: `src/hephaestus/forgebase/integration/pantheon_ingester.py`
- Modify: `src/hephaestus/forgebase/integration/pantheon_adapter.py`
- Create: `tests/test_forgebase/test_integration/test_pantheon_ingester.py`

```python
class PantheonIngester:
    """Structured ingestion of Pantheon deliberation into ForgeBase."""
    
    def __init__(
        self, uow_factory, claim_service, link_service, 
        run_integration_service, default_actor,
    ) -> None: ...

    async def ingest_pantheon_state(
        self, vault_id: EntityId, run_id: str, state: Any,
        invention_page_id: EntityId | None = None,
        workbook_id: EntityId | None = None,
    ) -> None:
        """Ingest Pantheon deliberation state into vault.
        
        1. Create KnowledgeRunRef
        2. Ingest AthenaCanon: derive constraint claims + CONSTRAINED_BY links
        3. Ingest HermesDossier: store ecosystem knowledge
        4. Record verdict on InventionPageMeta (update state)
        5. Ingest objections: CHALLENGED_BY links, CONTESTED status on challenged claims
        6. Update sync status
        """
```

Key: 
- Verdict mapping: UNANIMOUS→REVIEWED, QUALIFIED→REVIEWED, FAIL_CLOSED→REJECTED
- Open objections → set challenged invention claims to CONTESTED
- Canon constraints → claims linked to invention page via CONSTRAINED_BY
- Dossier → ingested as structured source

Update `pantheon_adapter.py` to delegate to `PantheonIngester`.

Tests:
- test_ingest_updates_invention_state_reviewed
- test_ingest_fail_closed_rejects_invention
- test_ingest_creates_constraint_claims_from_canon
- test_ingest_marks_contested_claims_from_objections
- test_ingest_records_verdict_on_meta
- test_ingest_handles_no_invention_page (standalone Pantheon run)

- [ ] **Step 1-6: Write tests → implement → update adapter → commit**

```bash
git commit -m "feat(forgebase): add PantheonIngester with first-class artifact ingestion"
```

---

### Task 5: Research Adapter Upgrade + Durable Follow-On

**Files:**
- Modify: `src/hephaestus/forgebase/integration/research_adapter.py`
- Create: `tests/test_forgebase/test_integration/test_research_adapter_upgrade.py`

Upgrade the research adapter to schedule durable ingest + Tier 1 compilation jobs instead of inline processing. Research outputs become Flow A eligible only after normal pipeline processing.

Tests:
- test_schedules_ingest_jobs_not_inline
- test_records_follow_on_job_refs
- test_sync_failure_does_not_affect_upstream

- [ ] **Step 1-4: Write tests → implement → commit**

```bash
git commit -m "feat(forgebase): upgrade research adapter with durable follow-on scheduling"
```

---

### Task 6: PromotionService

**Files:**
- Create: `src/hephaestus/forgebase/integration/promotion.py`
- Create: `tests/test_forgebase/test_integration/test_promotion.py`

```python
class PromotionService:
    def __init__(self, uow_factory, default_actor) -> None: ...
    
    async def evaluate_promotion(self, page_id, vault_id) -> PromotionResult:
        """Check eligibility: VERIFIED state, no CONTESTED objections, 
        required support links exist, trust thresholds met."""
    
    async def promote_claims(self, page_id, vault_id, claim_ids=None) -> list[EntityId]:
        """Promote eligible claims: HYPOTHESIS → SUPPORTED. Returns promoted IDs."""
```

Tests:
- test_evaluate_verified_page_eligible
- test_evaluate_proposed_page_not_eligible
- test_evaluate_contested_claims_block_promotion
- test_evaluate_missing_support_blocks
- test_promote_updates_claim_status
- test_promote_emits_event
- test_promote_skips_already_supported

- [ ] **Step 1-6: Write tests → implement → commit**

```bash
git commit -m "feat(forgebase): add PromotionService with explicit eligibility checks"
```

---

### Task 7: ExtractionPolicy + Pack Entry Models

**Files:**
- Create: `src/hephaestus/forgebase/extraction/policy.py`
- Create: `tests/test_forgebase/test_extraction/test_policy.py`

`ExtractionPolicy` dataclass with all per-channel trust filters from the spec. `DEFAULT_EXTRACTION_POLICY` constant.

Tests:
- test_default_policy_values
- test_baseline_strictest_settings
- test_context_broadest_settings
- test_dossier_governance_settings
- test_custom_policy_overrides

- [ ] **Step 1-4: Write tests → implement → commit**

```bash
git commit -m "feat(forgebase): add ExtractionPolicy with per-channel trust filters"
```

---

### Task 8: PriorArtBaselinePack Extraction

**Files:**
- Create: `src/hephaestus/forgebase/extraction/baseline_pack.py`
- Create: `tests/test_forgebase/test_extraction/test_baseline_pack.py`

```python
async def extract_baseline_pack(
    uow: AbstractUnitOfWork,
    vault_id: EntityId,
    policy: ExtractionPolicy,
    workbook_id: EntityId | None = None,
) -> PriorArtBaselinePack:
    """Extract prior-art baselines for DeepForge extra_blocked_paths.
    
    Includes:
    - SUPPORTED claims from concept/mechanism pages
    - VERIFIED invention mechanisms
    - External prior-art from AUTHORITATIVE sources
    
    Excludes:
    - HYPOTHESIS claims
    - CONTESTED claims
    - REJECTED inventions
    - Low-trust sources
    """
```

Tests using a seeded vault with mixed content (supported claims, hypothesis claims, verified inventions, rejected inventions):
- test_includes_supported_claims
- test_excludes_hypothesis_claims
- test_excludes_contested_claims
- test_includes_verified_inventions
- test_excludes_rejected_inventions
- test_pack_is_revision_pinned
- test_entries_have_typed_structure (PackEntry fields populated)

- [ ] **Step 1-6: Write tests → implement → commit**

```bash
git commit -m "feat(forgebase): add PriorArtBaselinePack extraction (strictest channel)"
```

---

### Task 9: DomainContextPack Extraction

**Files:**
- Create: `src/hephaestus/forgebase/extraction/context_pack.py`
- Create: `tests/test_forgebase/test_extraction/test_context_pack.py`

```python
async def extract_domain_context_pack(
    uow: AbstractUnitOfWork,
    vault_id: EntityId,
    policy: ExtractionPolicy,
    workbook_id: EntityId | None = None,
) -> DomainContextPack:
    """Extract domain context for LensSelector reference_context.
    
    Broadest channel — includes hypotheses, open questions, explored directions.
    Capped per category with salience ranking.
    Rejected inventions as explored-direction summaries only.
    """
```

Tests:
- test_includes_concept_pages
- test_includes_mechanism_pages
- test_includes_open_questions
- test_includes_hypothesis_claims
- test_rejected_inventions_as_summaries_only
- test_caps_entries_per_category
- test_salience_ranked

- [ ] **Step 1-6: Write tests → implement → commit**

```bash
git commit -m "feat(forgebase): add DomainContextPack extraction (broadest channel)"
```

---

### Task 10: ConstraintDossierPack Extraction

**Files:**
- Create: `src/hephaestus/forgebase/extraction/dossier_pack.py`
- Create: `tests/test_forgebase/test_extraction/test_dossier_pack.py`

```python
async def extract_constraint_dossier_pack(
    uow: AbstractUnitOfWork,
    vault_id: EntityId,
    policy: ExtractionPolicy,
    workbook_id: EntityId | None = None,
) -> ConstraintDossierPack:
    """Extract constraints for Pantheon baseline_dossier.
    
    Governance-grade: evidence-backed constraints, known failures, 
    validated objections, unresolved controversies (labeled).
    """
```

Tests:
- test_includes_hard_constraints
- test_includes_failure_modes
- test_includes_validated_objections
- test_includes_unresolved_controversies_labeled
- test_excludes_hypothesis
- test_excludes_rejected_inventions
- test_pack_revision_pinned

- [ ] **Step 1-6: Write tests → implement → commit**

```bash
git commit -m "feat(forgebase): add ConstraintDossierPack extraction (governance-grade)"
```

---

### Task 11: VaultContextAssembler + Renderers

**Files:**
- Create: `src/hephaestus/forgebase/extraction/assembler.py`
- Create: `src/hephaestus/forgebase/extraction/renderers.py`
- Create: `tests/test_forgebase/test_extraction/test_assembler.py`
- Create: `tests/test_forgebase/test_extraction/test_renderers.py`

```python
class VaultContextAssembler:
    def __init__(self, uow_factory, policy=None) -> None: ...
    async def assemble_prior_art_pack(self, vault_id, workbook_id=None) -> PriorArtBaselinePack: ...
    async def assemble_domain_context_pack(self, vault_id, workbook_id=None) -> DomainContextPack: ...
    async def assemble_constraint_dossier_pack(self, vault_id, workbook_id=None) -> ConstraintDossierPack: ...
    async def assemble_all(self, vault_id, workbook_id=None) -> tuple[...]: ...
```

Renderers:
```python
def render_baseline_pack_to_blocked_paths(pack: PriorArtBaselinePack) -> list[str]: ...
def render_context_pack_to_reference_context(pack: DomainContextPack) -> dict[str, Any]: ...
def render_dossier_pack_to_baseline_dossier(pack: ConstraintDossierPack) -> Any: ...
```

Tests:
- test_assembler_produces_all_three_packs
- test_assembler_uses_policy
- test_renderer_baseline_to_strings
- test_renderer_context_to_dict
- test_renderer_dossier_to_baseline_compatible

- [ ] **Step 1-6: Write tests → implement → commit**

```bash
git commit -m "feat(forgebase): add VaultContextAssembler and injection boundary renderers"
```

---

### Task 12: Factory Wiring

**Files:**
- Modify: `src/hephaestus/forgebase/factory.py`
- Modify: `tests/test_forgebase/test_e2e/test_factory.py`

Wire into ForgeBase:
- `InventionIngester`
- `PantheonIngester`
- `PromotionService`
- `VaultContextAssembler`

Update `GenesisAdapter` and `PantheonAdapter` constructors to accept the new ingesters.

Add to ForgeBase class: `fb.invention_ingester`, `fb.pantheon_ingester`, `fb.promotion`, `fb.context_assembler`

- [ ] **Step 1-4: Update factory → update tests → commit**

```bash
git commit -m "feat(forgebase): wire invention loop components into factory"
```

---

### Task 13: End-to-End Closed-Loop Test

**Files:**
- Create: `tests/test_forgebase/test_e2e/test_invention_loop.py`

The definitive test proving the full feedback loop works:

```python
@pytest.mark.asyncio
async def test_full_invention_loop():
    """Exercise all 9 minimum flows from the spec."""
    
    fb = await create_forgebase(clock=..., id_generator=...)
    vault = await fb.vaults.create_vault(name="loop-test")
    
    # Setup: ingest + compile some background sources first
    # (gives the vault content for extraction)
    ...
    
    # Flow 1: Genesis run → invention page (PROPOSED) + claims + concepts
    pages = await fb.invention_ingester.ingest_invention_report(
        vault_id=vault.vault_id, run_id="genesis-001", report=mock_report,
    )
    assert len(pages) > 0
    # Verify INVENTION page, PROPOSED state, HYPOTHESIS claims
    
    # Flow 2: Pantheon → REVIEWED + artifacts
    await fb.pantheon_ingester.ingest_pantheon_state(
        vault_id=vault.vault_id, run_id="pantheon-001", 
        state=mock_pantheon_state, invention_page_id=pages[0],
    )
    # Verify state updated, canon/dossier artifacts, objection links
    
    # Flow 3: Verification → VERIFIED
    # (simulate by directly updating state)
    uow = fb.uow_factory()
    async with uow:
        await uow.invention_meta.update_state(pages[0], InventionEpistemicState.VERIFIED)
        await uow.commit()
    
    # Flow 4: PromotionService → claims promoted
    result = await fb.promotion.evaluate_promotion(pages[0], vault.vault_id)
    promoted = await fb.promotion.promote_claims(pages[0], vault.vault_id)
    assert len(promoted) > 0
    
    # Flow 5: Extract PriorArtBaselinePack
    baseline = await fb.context_assembler.assemble_prior_art_pack(vault.vault_id)
    # Promoted claims should appear
    assert len(baseline.entries) > 0
    
    # Flow 6: Extract DomainContextPack
    context = await fb.context_assembler.assemble_domain_context_pack(vault.vault_id)
    assert len(context.concepts) > 0 or len(context.mechanisms) > 0
    
    # Flow 7: Extract ConstraintDossierPack
    dossier = await fb.context_assembler.assemble_constraint_dossier_pack(vault.vault_id)
    # Should include any constraint claims
    
    # Flow 8: Render packs for injection
    from hephaestus.forgebase.extraction.renderers import (
        render_baseline_pack_to_blocked_paths,
        render_context_pack_to_reference_context,
    )
    blocked_paths = render_baseline_pack_to_blocked_paths(baseline)
    ref_context = render_context_pack_to_reference_context(context)
    assert isinstance(blocked_paths, list)
    assert isinstance(ref_context, dict)
    
    # Flow 9: POISONING GUARD — contested/rejected NOT in baseline
    # Create a CONTESTED invention
    contested_pages = await fb.invention_ingester.ingest_invention_report(
        vault_id=vault.vault_id, run_id="genesis-bad",
        report=mock_rejected_report,
    )
    uow2 = fb.uow_factory()
    async with uow2:
        await uow2.invention_meta.update_state(contested_pages[0], InventionEpistemicState.CONTESTED)
        await uow2.commit()
    
    # Re-extract baseline — contested should NOT appear
    baseline2 = await fb.context_assembler.assemble_prior_art_pack(vault.vault_id)
    contested_meta = ...  # read the contested invention's claims
    # Verify none of the contested claims are in baseline entries
    
    await fb.close()
```

The test needs mock Genesis report and mock Pantheon state objects. Create them as simple dicts/objects with the fields the ingesters extract.

- [ ] **Step 1-6: Write e2e test → run → commit**

```bash
git commit -m "feat(forgebase): add end-to-end closed-loop invention test with poisoning guard"
```

---

## Implementation Notes

**Parallelization opportunities:**
- Task 1 (domain) must come first
- Task 2 (repo + schema) depends on Task 1
- Tasks 3, 4, 5 (ingesters + research upgrade) can run in parallel after Task 2
- Task 6 (PromotionService) depends on Task 2
- Task 7 (ExtractionPolicy) depends on Task 1 only
- Tasks 8, 9, 10 (three extraction packs) can run in parallel after Tasks 2 + 7
- Task 11 (assembler + renderers) depends on Tasks 8-10
- Task 12 (factory) depends on everything
- Task 13 (e2e) depends on Task 12

**Best dispatch order:**
1. Task 1 (domain)
2. Task 2 (repo + schema) + Task 7 (policy) in parallel
3. Tasks 3, 4, 5, 6 (Flow B) in parallel with Tasks 8, 9, 10 (Flow A packs)
4. Task 11 (assembler)
5. Tasks 12 + 13 (factory + e2e)

**Link taxonomy:** The 6 new LinkKind values (MOTIVATED_BY, MAPS_TO, DERIVES_FROM, PRIOR_ART_OF, CONSTRAINED_BY, CHALLENGED_BY) are added to the existing enum in Task 1. No schema changes needed — links already store kind as a string value.

**Mock data for tests:** Ingesters accept `Any` typed report/state parameters. Tests should create simple dataclass instances or dicts mimicking Genesis/Pantheon output structure, using `getattr()` resilient extraction.
