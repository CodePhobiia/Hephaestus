# ForgeBase Linting + Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the lint detection engine with 11 pluggable detectors, a finding-driven remediation state machine (triage → research → repair → verify), and knowledge debt scoring — making ForgeBase actively maintain vault health.

**Architecture:** Pluggable detector registry with VaultLintState query facade. Data-only detectors are pure queries; LLM-assisted detectors use prefilter → LintAnalyzer analysis. Findings enter a remediation lifecycle managed by durable jobs: LintJob → FindingResearchJob → RepairWorkbookJob → FindingVerificationJob. All remediation happens on workbook branches. Research augmentation uses the existing ResearchAugmentor interface. Findings close only after detector-specific verification.

**Tech Stack:** Python 3.11+, aiosqlite, pytest-asyncio, existing ForgeBase Foundation Platform + Compiler (562 tests)

**Spec:** `docs/superpowers/specs/2026-04-04-forgebase-linting-design.md`

---

## File Structure

```
# New files to create:

src/hephaestus/forgebase/
  domain/enums.py                               # MODIFY — add 5 new enums, rename 2 categories
  domain/models.py                              # MODIFY — extend LintFinding, add RepairBatch, ResearchPacket + children, LintReport
  domain/event_types.py                         # MODIFY — add 16 new events to taxonomy

  repository/finding_repo.py                    # MODIFY — add new query methods
  repository/research_packet_repo.py            # CREATE
  repository/repair_batch_repo.py               # CREATE
  repository/lint_report_repo.py                # CREATE
  repository/uow.py                             # MODIFY — add 3 new repo accessors

  store/sqlite/schema.py                        # MODIFY — add new tables, modify findings table
  store/sqlite/finding_repo.py                  # MODIFY — add new query methods
  store/sqlite/research_packet_repo.py          # CREATE
  store/sqlite/repair_batch_repo.py             # CREATE
  store/sqlite/lint_report_repo.py              # CREATE
  store/sqlite/uow.py                           # MODIFY — wire new repos

  service/lint_service.py                       # MODIFY — add remediation status/disposition methods

  linting/
    __init__.py                                 # CREATE
    engine.py                                   # CREATE — LintEngine orchestrator
    state.py                                    # CREATE — VaultLintState query facade
    fingerprint.py                              # CREATE — finding fingerprint + dedup
    scoring.py                                  # CREATE — knowledge debt scoring

    analyzer.py                                 # CREATE — LintAnalyzer ABC
    analyzers/
      __init__.py                               # CREATE
      anthropic_analyzer.py                     # CREATE
      mock_analyzer.py                          # CREATE — for testing

    detectors/
      __init__.py                               # CREATE
      base.py                                   # CREATE — LintDetector ABC + RawFinding
      stale_evidence.py                         # CREATE
      orphaned_page.py                          # CREATE
      duplicate_page.py                         # CREATE
      broken_reference.py                       # CREATE
      missing_canonical.py                      # CREATE
      unresolved_todo.py                        # CREATE
      unsupported_claim.py                      # CREATE
      contradictory_claim.py                    # CREATE
      source_gap.py                             # CREATE
      missing_figure.py                         # CREATE
      resolvable_by_search.py                   # CREATE

    remediation/
      __init__.py                               # CREATE
      policy.py                                 # CREATE — RemediationPolicy + rules
      triage.py                                 # CREATE — route assignment
      batcher.py                                # CREATE — finding batching
      research_job.py                           # CREATE — FindingResearchJob
      repair_job.py                             # CREATE — RepairWorkbookJob
      verification_job.py                       # CREATE — FindingVerificationJob

  factory.py                                    # MODIFY — wire linting components

tests/test_forgebase/
  test_linting/
    __init__.py                                 # CREATE
    conftest.py                                 # CREATE — mock analyzer + test vault fixtures
    test_state.py                               # CREATE
    test_fingerprint.py                         # CREATE
    test_scoring.py                             # CREATE
    test_engine.py                              # CREATE
    test_detectors/
      __init__.py                               # CREATE
      test_stale_evidence.py                    # CREATE
      test_orphaned_page.py                     # CREATE
      test_duplicate_page.py                    # CREATE
      test_broken_reference.py                  # CREATE
      test_missing_canonical.py                 # CREATE
      test_unresolved_todo.py                   # CREATE
      test_unsupported_claim.py                 # CREATE
      test_contradictory_claim.py               # CREATE
      test_source_gap.py                        # CREATE
    test_remediation/
      __init__.py                               # CREATE
      test_policy.py                            # CREATE
      test_triage.py                            # CREATE
      test_batcher.py                           # CREATE
      test_research_job.py                      # CREATE
      test_repair_job.py                        # CREATE
      test_verification_job.py                  # CREATE
  test_e2e/
    test_lint_lifecycle.py                      # CREATE
```

---

### Task 1: Domain Extensions — Enums, Extended Models, Events

**Files:**
- Modify: `src/hephaestus/forgebase/domain/enums.py`
- Modify: `src/hephaestus/forgebase/domain/models.py`
- Modify: `src/hephaestus/forgebase/domain/event_types.py`
- Modify: `tests/test_forgebase/test_domain/test_enums.py`
- Modify: `tests/test_forgebase/test_domain/test_models.py`

- [ ] **Step 1: Write failing tests for new enums**

```python
# Append to tests/test_forgebase/test_domain/test_enums.py
from hephaestus.forgebase.domain.enums import (
    RemediationStatus, RemediationRoute, RouteSource,
    FindingDisposition, ResearchOutcome,
)

def test_remediation_status_values():
    assert RemediationStatus.OPEN == "open"
    assert RemediationStatus.TRIAGED == "triaged"
    assert RemediationStatus.RESEARCH_PENDING == "research_pending"
    assert RemediationStatus.VERIFIED == "verified"

def test_remediation_route_values():
    assert RemediationRoute.REPORT_ONLY == "report_only"
    assert RemediationRoute.RESEARCH_THEN_REPAIR == "research_then_repair"

def test_finding_disposition_values():
    assert FindingDisposition.ACTIVE == "active"
    assert FindingDisposition.RESOLVED == "resolved"
    assert FindingDisposition.FALSE_POSITIVE == "false_positive"

def test_research_outcome_values():
    assert ResearchOutcome.SUFFICIENT_FOR_REPAIR == "sufficient_for_repair"
    assert ResearchOutcome.NEW_SOURCES_PENDING == "new_sources_pending"

def test_finding_category_renames():
    """Verify STALE_PAGE → STALE_EVIDENCE and WEAK_BACKLINK → BROKEN_REFERENCE."""
    assert FindingCategory.STALE_EVIDENCE == "stale_evidence"
    assert FindingCategory.BROKEN_REFERENCE == "broken_reference"
    # Old names should not exist
    assert not hasattr(FindingCategory, "STALE_PAGE")
    assert not hasattr(FindingCategory, "WEAK_BACKLINK")
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest tests/test_forgebase/test_domain/test_enums.py -v -k "remediation or disposition or research_outcome or renames"`
Expected: FAIL

- [ ] **Step 3: Add new enums + rename existing categories**

In `domain/enums.py`:
- Rename `STALE_PAGE = "stale_page"` → `STALE_EVIDENCE = "stale_evidence"`
- Rename `WEAK_BACKLINK = "weak_backlink"` → `BROKEN_REFERENCE = "broken_reference"`
- Append 5 new enum classes: `RemediationStatus`, `RemediationRoute`, `RouteSource`, `FindingDisposition`, `ResearchOutcome`

```python
class RemediationStatus(str, Enum):
    OPEN = "open"
    TRIAGED = "triaged"
    RESEARCH_PENDING = "research_pending"
    RESEARCH_COMPLETED = "research_completed"
    REPAIR_PENDING = "repair_pending"
    REPAIR_WORKBOOK_CREATED = "repair_workbook_created"
    AWAITING_REVIEW = "awaiting_review"
    MERGED_PENDING_VERIFY = "merged_pending_verify"
    VERIFIED = "verified"

class RemediationRoute(str, Enum):
    REPORT_ONLY = "report_only"
    RESEARCH_ONLY = "research_only"
    REPAIR_ONLY = "repair_only"
    RESEARCH_THEN_REPAIR = "research_then_repair"

class RouteSource(str, Enum):
    POLICY = "policy"
    USER = "user"
    AUTOMATION = "automation"
    RETRIAGE = "retriage"

class FindingDisposition(str, Enum):
    ACTIVE = "active"
    RESOLVED = "resolved"
    FALSE_POSITIVE = "false_positive"
    WONT_FIX = "wont_fix"
    ABANDONED = "abandoned"

class ResearchOutcome(str, Enum):
    SUFFICIENT_FOR_REPAIR = "sufficient_for_repair"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    NEW_SOURCES_PENDING = "new_sources_pending"
    NO_ACTIONABLE_RESULT = "no_actionable_result"
```

- [ ] **Step 4: Extend LintFinding model + add new entities**

In `domain/models.py`, extend `LintFinding` with new fields and add `RepairBatch`, `ResearchPacket`, `ResearchPacketDiscoveredSource`, `ResearchPacketIngestJob`, `ResearchPacketContradictionResult`, `ResearchPacketFreshnessResult`, `LintReport` as new dataclasses matching the spec exactly.

- [ ] **Step 5: Add 16 new events to EVENT_TAXONOMY**

In `domain/event_types.py`, add to the `EVENT_TAXONOMY` frozenset:
```python
"finding.triaged",
"finding.route_assigned",
"finding.research_requested",
"finding.research_completed",
"finding.repair_requested",
"research.packet_created",
"repair.batch_created",
"repair.workbook_created",
"repair.workbook_merged",
"repair.workbook_abandoned",
"finding.verification_requested",
"finding.resolved",
"finding.reopened",
"finding.false_positive",
"finding.wont_fix",
"finding.abandoned",
```

- [ ] **Step 6: Write model tests, run all tests, commit**

Run: `python -m pytest tests/test_forgebase/test_domain/ -v`
Expected: All PASS

```bash
git commit -m "feat(forgebase): add linting domain extensions — enums, extended finding model, remediation entities, events"
```

---

### Task 2: Repository Extensions + Schema + SQLite Implementations

**Files:**
- Modify: `src/hephaestus/forgebase/repository/finding_repo.py` — add new abstract methods
- Create: `src/hephaestus/forgebase/repository/research_packet_repo.py`
- Create: `src/hephaestus/forgebase/repository/repair_batch_repo.py`
- Create: `src/hephaestus/forgebase/repository/lint_report_repo.py`
- Modify: `src/hephaestus/forgebase/repository/uow.py` — add 3 new accessors
- Modify: `src/hephaestus/forgebase/store/sqlite/schema.py` — add/modify tables
- Modify: `src/hephaestus/forgebase/store/sqlite/finding_repo.py` — implement new methods
- Create: `src/hephaestus/forgebase/store/sqlite/research_packet_repo.py`
- Create: `src/hephaestus/forgebase/store/sqlite/repair_batch_repo.py`
- Create: `src/hephaestus/forgebase/store/sqlite/lint_report_repo.py`
- Modify: `src/hephaestus/forgebase/store/sqlite/uow.py` — wire repos
- Test: `tests/test_forgebase/test_store/test_sqlite_finding_repo_ext.py`
- Test: `tests/test_forgebase/test_store/test_sqlite_research_packet_repo.py`
- Test: `tests/test_forgebase/test_store/test_sqlite_repair_batch_repo.py`

Schema additions:
- Alter `fb_lint_findings` table: add columns for fingerprint, remediation_status, disposition, route, route_source, detector_version, confidence, affected_entity_ids (JSON), research_job_id, repair_workbook_id, repair_batch_id, verification_job_id
- New tables: `fb_repair_batches`, `fb_research_packets`, `fb_research_packet_sources`, `fb_research_packet_ingest_jobs`, `fb_research_packet_contradiction_results`, `fb_research_packet_freshness_results`, `fb_lint_reports`

New finding repo methods: `update_remediation_status()`, `update_disposition()`, `find_by_fingerprint()`, `list_by_disposition()`, `list_by_remediation_status()`

Follow established repo patterns from SP1/SP2.

- [ ] **Step 1-6: Write tests → implement repos + schema → wire UoW → commit**

```bash
git commit -m "feat(forgebase): add linting repos, schema extensions, finding query methods"
```

---

### Task 3: Lint Service Extensions

**Files:**
- Modify: `src/hephaestus/forgebase/service/lint_service.py`
- Test: `tests/test_forgebase/test_service/test_lint_service_ext.py`

Extend `LintService` with new methods needed by the remediation pipeline:
- `update_finding_remediation(finding_id, remediation_status, route?, route_source?)`
- `update_finding_disposition(finding_id, disposition)`
- `set_finding_research_job(finding_id, research_job_id)`
- `set_finding_repair_workbook(finding_id, repair_workbook_id, repair_batch_id)`
- `set_finding_verification_job(finding_id, verification_job_id)`
- `reopen_finding(finding_id)` — sets disposition=ACTIVE, status=OPEN

Each method emits the appropriate event.

- [ ] **Step 1-4: Write tests → implement → commit**

```bash
git commit -m "feat(forgebase): extend LintService with remediation lifecycle methods"
```

---

### Task 4: LintDetector ABC + RawFinding + Finding Fingerprint

**Files:**
- Create: `src/hephaestus/forgebase/linting/__init__.py`
- Create: `src/hephaestus/forgebase/linting/detectors/__init__.py`
- Create: `src/hephaestus/forgebase/linting/detectors/base.py`
- Create: `src/hephaestus/forgebase/linting/fingerprint.py`
- Test: `tests/test_forgebase/test_linting/__init__.py`
- Test: `tests/test_forgebase/test_linting/test_fingerprint.py`

`RawFinding` dataclass with category, severity, description, affected_entity_ids, normalized_subject, suggested_action, confidence, page_id, claim_id.

`LintDetector` ABC with `name`, `categories`, `version`, `detect(state) -> list[RawFinding]`, `is_resolved(original, current_state, new_findings) -> bool`.

`compute_fingerprint(category, affected_entity_ids, normalized_subject, workbook_id, detector_version) -> str` using stable hash.

`dedup_findings(raw_findings, existing_findings) -> tuple[list[new], list[reopen]]` using fingerprint matching.

- [ ] **Step 1: Write fingerprint tests**

```python
# tests/test_forgebase/test_linting/test_fingerprint.py
from hephaestus.forgebase.linting.fingerprint import compute_fingerprint, dedup_findings

def test_fingerprint_stable():
    fp1 = compute_fingerprint("unsupported_claim", ["claim_001"], "claim about X", None, "1.0")
    fp2 = compute_fingerprint("unsupported_claim", ["claim_001"], "claim about X", None, "1.0")
    assert fp1 == fp2

def test_fingerprint_differs_on_category():
    fp1 = compute_fingerprint("unsupported_claim", ["claim_001"], "X", None, "1.0")
    fp2 = compute_fingerprint("stale_evidence", ["claim_001"], "X", None, "1.0")
    assert fp1 != fp2

def test_fingerprint_differs_on_entities():
    fp1 = compute_fingerprint("unsupported_claim", ["claim_001"], "X", None, "1.0")
    fp2 = compute_fingerprint("unsupported_claim", ["claim_002"], "X", None, "1.0")
    assert fp1 != fp2

def test_dedup_new_finding():
    # No existing findings → all raw findings are new
    ...

def test_dedup_reopen_resolved():
    # Existing resolved finding with same fingerprint → reopen list
    ...

def test_dedup_skip_existing_open():
    # Existing open finding with same fingerprint → neither new nor reopen
    ...
```

- [ ] **Step 2-5: Implement + commit**

```bash
git commit -m "feat(forgebase): add LintDetector ABC, RawFinding, finding fingerprint + dedup"
```

---

### Task 5: VaultLintState Query Facade

**Files:**
- Create: `src/hephaestus/forgebase/linting/state.py`
- Test: `tests/test_forgebase/test_linting/test_state.py`

VaultLintState: lazy-cached, branch-aware query facade. Constructed with UoW + vault_id + optional workbook_id. Provides: `pages()`, `claims()`, `links()`, `sources()`, `candidates()`, `existing_findings()`, plus helper selectors: `claims_without_support()`, `pages_with_zero_inbound_links()`, `claims_past_freshness(now)`, `candidates_promotion_worthy(policy)`, `page_content(page_id)`.

Tests create a seeded vault (pages, claims, links, sources) and verify each selector returns correct results.

- [ ] **Step 1-4: Write tests → implement → commit**

```bash
git commit -m "feat(forgebase): add VaultLintState query facade with cached selectors"
```

---

### Task 6: Data-Only Detectors (6 detectors)

**Files:**
- Create: `src/hephaestus/forgebase/linting/detectors/stale_evidence.py`
- Create: `src/hephaestus/forgebase/linting/detectors/orphaned_page.py`
- Create: `src/hephaestus/forgebase/linting/detectors/duplicate_page.py`
- Create: `src/hephaestus/forgebase/linting/detectors/broken_reference.py`
- Create: `src/hephaestus/forgebase/linting/detectors/missing_canonical.py`
- Create: `src/hephaestus/forgebase/linting/detectors/unresolved_todo.py`
- Test: `tests/test_forgebase/test_linting/test_detectors/` (one file per detector)

Each detector implements `LintDetector` ABC. Each test creates specific vault state that triggers the detector and verifies correct findings are produced.

**StaleEvidenceDetector:** Claims where `fresh_until < now`. Aggregates per page. `is_resolved`: claim's fresh_until updated or claim removed.

**OrphanedPageDetector:** Pages with no incoming links, excluding SOURCE_CARD and SOURCE_INDEX types. `is_resolved`: page has incoming links.

**DuplicatePageDetector:** Pages with normalized titles that match (case-insensitive, stripped). `is_resolved`: one page removed or renamed.

**BrokenReferenceDetector:** Links where target entity doesn't exist. `is_resolved`: link removed or target exists.

**MissingCanonicalDetector:** Active concept candidates crossing promotion thresholds (uses SynthesisPolicy) with no resolved_page_id. `is_resolved`: candidate promoted or rejected.

**UnresolvedTodoDetector:** Regex scan for TODO/FIXME/TBD/PLACEHOLDER in page content bytes. `is_resolved`: text patterns removed.

- [ ] **Step 1-6: Write detectors + tests, commit**

```bash
git commit -m "feat(forgebase): add 6 data-only lint detectors"
```

---

### Task 7: LintAnalyzer ABC + Mock Analyzer

**Files:**
- Create: `src/hephaestus/forgebase/linting/analyzer.py`
- Create: `src/hephaestus/forgebase/linting/analyzers/__init__.py`
- Create: `src/hephaestus/forgebase/linting/analyzers/mock_analyzer.py`
- Create: `tests/test_forgebase/test_linting/conftest.py`

LintAnalyzer ABC with: `detect_contradictions(claim_pairs)`, `assess_source_gaps(concept, evidence_count, claims)`, `check_resolvable_by_search(claim, existing_support)`.

Result types: `ContradictionResult(is_contradictory: bool, explanation: str, confidence: float)`, `SourceGapAssessment(is_gap: bool, severity: str, explanation: str)`, `ResolvabilityAssessment(is_resolvable: bool, search_query: str, confidence: float)`.

MockLintAnalyzer returns deterministic results. Exposed as `mock_analyzer` fixture.

- [ ] **Step 1-4: Write + commit**

```bash
git commit -m "feat(forgebase): add LintAnalyzer ABC, result types, and mock implementation"
```

---

### Task 8: LLM-Assisted Detectors (5 detectors)

**Files:**
- Create: `src/hephaestus/forgebase/linting/detectors/unsupported_claim.py`
- Create: `src/hephaestus/forgebase/linting/detectors/contradictory_claim.py`
- Create: `src/hephaestus/forgebase/linting/detectors/source_gap.py`
- Create: `src/hephaestus/forgebase/linting/detectors/missing_figure.py`
- Create: `src/hephaestus/forgebase/linting/detectors/resolvable_by_search.py`
- Test: `tests/test_forgebase/test_linting/test_detectors/` (per detector)

Each LLM detector follows prefilter → analysis pattern:

**UnsupportedClaimDetector:** Prefilter: `claims_without_support()`. Analysis: LintAnalyzer not needed for claims with zero support — those are automatically findings. For claims with weak support, could optionally use grade_evidence.

**ContradictoryClaimDetector:** Prefilter: group claims by page, generate same-concept pairs. Analysis: `analyzer.detect_contradictions(pairs)`. Only pairs within the same concept scope to avoid combinatorial explosion.

**SourceGapDetector:** Prefilter: concepts with < N source evidence (threshold from policy). Analysis: `analyzer.assess_source_gaps()`.

**MissingFigureDetector (data-only despite being in this task):** Regex scan for image references `![...]` or `<img` without corresponding description text. No LLM needed.

**ResolvableBySearchDetector:** Prefilter: claims with low support strength. Analysis: `analyzer.check_resolvable_by_search()`.

- [ ] **Step 1-6: Write detectors + tests, commit**

```bash
git commit -m "feat(forgebase): add 5 LLM-assisted lint detectors with prefilter pattern"
```

---

### Task 9: Knowledge Debt Scoring

**Files:**
- Create: `src/hephaestus/forgebase/linting/scoring.py`
- Test: `tests/test_forgebase/test_linting/test_scoring.py`

`DebtScoringPolicy` dataclass with `policy_version`, `weights` dict (severity → float), `normalization_base`.

`compute_debt_score(findings_by_severity, vault_size, policy) -> float` returns 0-100.

Tests verify: empty vault = 0, critical findings increase score, normalization by vault size works, custom weights apply.

- [ ] **Step 1-4: Write + commit**

```bash
git commit -m "feat(forgebase): add policy-versioned knowledge debt scoring"
```

---

### Task 10: LintEngine Orchestrator

**Files:**
- Create: `src/hephaestus/forgebase/linting/engine.py`
- Test: `tests/test_forgebase/test_linting/test_engine.py`

LintEngine ties everything together: schedules job, builds VaultLintState, runs detectors, fingerprints + dedup, opens findings, triages, scores, completes job, returns LintReport.

Tests use MockLintAnalyzer + a seeded vault with known issues. Verify: correct findings opened, duplicates skipped, resolved findings reopened, debt score computed, report persisted.

- [ ] **Step 1-6: Write engine + tests, commit**

```bash
git commit -m "feat(forgebase): add LintEngine orchestrator with detector registry and dedup"
```

---

### Task 11: Remediation Policy + Triage

**Files:**
- Create: `src/hephaestus/forgebase/linting/remediation/__init__.py`
- Create: `src/hephaestus/forgebase/linting/remediation/policy.py`
- Create: `src/hephaestus/forgebase/linting/remediation/triage.py`
- Test: `tests/test_forgebase/test_linting/test_remediation/__init__.py`
- Test: `tests/test_forgebase/test_linting/test_remediation/test_policy.py`
- Test: `tests/test_forgebase/test_linting/test_remediation/test_triage.py`

`RemediationPolicy` with rules list + priority-based resolution (exact match → category-only → severity-only → default).

`triage_findings()` assigns route + route_source=POLICY to each finding.

Tests verify: policy matching precedence, default route applied, override changes route_source to USER.

- [ ] **Step 1-4: Write + commit**

```bash
git commit -m "feat(forgebase): add remediation policy engine and triage logic"
```

---

### Task 12: Finding Batching

**Files:**
- Create: `src/hephaestus/forgebase/linting/remediation/batcher.py`
- Test: `tests/test_forgebase/test_linting/test_remediation/test_batcher.py`

`batch_findings(findings, strategy)` groups findings into `RepairBatch` objects. Strategies: BY_PAGE (same page_id), BY_CONCEPT (same concept cluster), BY_CATEGORY (same category), auto (page first, then concept, then category fallback). Each batch gets a stable fingerprint for idempotency.

- [ ] **Step 1-4: Write + commit**

```bash
git commit -m "feat(forgebase): add finding batching for repair workbook grouping"
```

---

### Task 13: FindingResearchJob

**Files:**
- Create: `src/hephaestus/forgebase/linting/remediation/research_job.py`
- Test: `tests/test_forgebase/test_linting/test_remediation/test_research_job.py`

Orchestrates research for a finding: reads finding, dispatches to ResearchAugmentor by category, creates ResearchPacket + child records, classifies outcome, schedules follow-on ingest/repair if appropriate, updates finding status.

Tests use MockResearchAugmentor (NoOpAugmentor or mock) and verify: packet created, outcome classified, finding status updated, auto-repair triggered only on SUFFICIENT.

- [ ] **Step 1-4: Write + commit**

```bash
git commit -m "feat(forgebase): add FindingResearchJob orchestrator"
```

---

### Task 14: RepairWorkbookJob

**Files:**
- Create: `src/hephaestus/forgebase/linting/remediation/repair_job.py`
- Test: `tests/test_forgebase/test_linting/test_remediation/test_repair_job.py`

Creates a workbook (purpose=LINT_REPAIR) and applies category-specific repairs on the branch. Tests verify: workbook created, branch-scoped mutations, contradiction repair creates open-question page (not silent status flip), finding status updated.

- [ ] **Step 1-4: Write + commit**

```bash
git commit -m "feat(forgebase): add RepairWorkbookJob orchestrator"
```

---

### Task 15: FindingVerificationJob

**Files:**
- Create: `src/hephaestus/forgebase/linting/remediation/verification_job.py`
- Test: `tests/test_forgebase/test_linting/test_remediation/test_verification_job.py`

After repair merge, re-runs relevant detectors using `detector.is_resolved()`. Tests verify: resolved finding gets disposition=RESOLVED, unresolved finding gets reopened.

- [ ] **Step 1-4: Write + commit**

```bash
git commit -m "feat(forgebase): add FindingVerificationJob with detector-specific resolution checks"
```

---

### Task 16: Anthropic LintAnalyzer

**Files:**
- Create: `src/hephaestus/forgebase/linting/analyzers/anthropic_analyzer.py`
- Test: `tests/test_forgebase/test_linting/test_analyzers/test_anthropic_analyzer.py` (mock Anthropic client)

Real LLM implementation: sends lint-specific prompts, parses JSON responses, handles repair pass. Tests mock the Anthropic client.

- [ ] **Step 1-4: Write + commit**

```bash
git commit -m "feat(forgebase): add Anthropic LintAnalyzer implementation"
```

---

### Task 17: Factory Updates + E2E Lifecycle Test

**Files:**
- Modify: `src/hephaestus/forgebase/factory.py`
- Create: `tests/test_forgebase/test_e2e/test_lint_lifecycle.py`

Wire LintEngine, all detectors, LintAnalyzer, remediation policy, scoring into factory. Add `fb.lint_engine` to ForgeBase.

E2E test exercises all 8 minimum flows from the spec:
1. Lint vault → findings produced
2. Triage → routes assigned
3. Research job for SOURCE_GAP → ResearchPacket
4. Research SUFFICIENT → repair workbook auto-scheduled
5. Repair workbook with proposed fixes
6. Merge → verification → RESOLVED
7. Re-lint → resolved stay resolved, new detected
8. Contradiction → open-question page created

- [ ] **Step 1-6: Wire factory + write e2e test + commit**

```bash
git commit -m "feat(forgebase): wire linting into factory, add e2e lint lifecycle test"
```

---

## Implementation Notes

**Parallelization opportunities:**
- Tasks 1-3 (domain + repos + service) are sequential foundation
- Task 4 (detector ABC + fingerprint) can start after Task 1
- Tasks 5, 6, 7 can run in parallel after Task 4 (state, data detectors, analyzer)
- Task 8 (LLM detectors) depends on Tasks 5 + 7
- Tasks 9, 10 depend on Tasks 6 + 8
- Tasks 11, 12 can run in parallel (policy, batching)
- Tasks 13, 14, 15 are sequential (research → repair → verify)
- Task 16 is independent (Anthropic analyzer)
- Task 17 must come last

**FindingCategory renames:** The renames (STALE_PAGE → STALE_EVIDENCE, WEAK_BACKLINK → BROKEN_REFERENCE) will need to update any existing references in the codebase. Run `grep -r "STALE_PAGE\|WEAK_BACKLINK" src/` after the rename to catch all references.

**LintFinding schema migration:** The existing `fb_lint_findings` table needs new columns. Since this is a development-phase system (not yet production-deployed), the cleanest approach is to modify the CREATE TABLE statement in schema.py and drop/recreate during testing. If production migration is needed later, proper ALTER TABLE statements should be added to the migrations framework.
