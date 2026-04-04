# ForgeBase Sub-project 3: Linting + Research + Workbook Intelligence — Design Spec

## Overview

This spec covers Sub-project 3 of ForgeBase: the lint detection engine, finding-driven remediation pipeline, research integration for evidence gathering, and repair workbook automation. It builds on the Foundation Platform (Sub-project 1) and the Compiler (Sub-project 2, 562 tests).

### Goal

Detect knowledge problems in a vault (contradictions, unsupported claims, stale evidence, structural issues), triage them with policy-driven remediation routes, optionally research missing evidence, create repair workbooks with proposed fixes, and verify resolutions after merge.

### Architectural Stance

Lint is a **finding-driven remediation state machine**, not just a report generator. Every finding enters a lifecycle: detect → triage → research (optional) → repair (optional) → verify. Each stage is an independent durable job. The system closes findings only after verification, never from workbook existence alone.

---

## Locked Architectural Decisions

### 1. Pluggable Detector Registry + Event-Reactive Fast Path

- Primary flow: scheduled lint pass with pluggable detectors (LintDetector ABC). Full-vault health reports, knowledge debt scores, on-demand "lint this vault."
- Optimization: high-value detectors (contradiction, stale evidence) can also subscribe to events for incremental early detection.
- The scheduled pass is the authoritative baseline; event-reactive detection is a fast path.

### 2. Data-Only + LLM-Assisted Detectors

- Data-only detectors: pure queries, no LLM (stale evidence, orphans, duplicates, broken refs, missing canonical, unresolved TODOs).
- LLM-assisted detectors: use a dedicated LintAnalyzer interface for lint-specific reasoning (contradictions, unsupported claims, source gaps, resolvable by search).
- LLM detectors use **prefilter → analysis**: cheap query filters produce candidate sets, then only reduced sets go to LintAnalyzer.
- CompilerBackend.grade_evidence() reused where it overlaps (unsupported claim assessment).

### 3. Dedicated LintAnalyzer Contract

- Own interface with lint-specific prompts and outputs, separate from CompilerBackend.
- May share underlying model client infrastructure (transport, retry, credentials).
- Never conceptually "the compiler backend doing extra things."
- Independently benchmarkable and tunable.

### 4. Finding-Driven Remediation State Machine

- Detect → Triage → Research (optional) → Repair Workbook (optional) → Verify.
- Each stage is an independent durable job.
- Research augmentation is follow-on work, not inline.
- Repair happens only in workbooks, never directly in canonical.
- Findings close only after verification, never from workbook existence alone.
- Remediation routes are policy-driven, overridable, and reversible.

### 5. Finding Fingerprint + Dedup

- Every finding has a stable fingerprint from (category, affected_entity_ids, normalized_subject, branch scope, detector_version).
- Rerun lint uses fingerprints to dedup against existing open findings.
- When a fingerprint reappears after resolution, the finding is reopened, not duplicated.

### 6. Detector-Specific Verification

- Verification is not just "fingerprint absent = resolved."
- Each detector exposes a verification contract: `is_resolved(original_finding, current_state, new_findings) -> bool`.
- Fingerprint is one signal, not the entire truth.
- Contradiction handling may convert the problem into an explicit representation, not erase it.

### 7. Contradiction Repair Preserves Uncertainty

- A contradiction finding may only be "resolved by status update" if research found strong enough evidence to settle it.
- Default repair: represent the contradiction explicitly (open-question page, preserve both views, mark epistemic state honestly).
- The system never launders uncertainty into fake cleanliness.

### 8. Research Result Classification

After research, the system classifies the result before auto-scheduling repair:
- `SUFFICIENT_FOR_REPAIR` → schedule repair workbook
- `INSUFFICIENT_EVIDENCE` → may stay open or move to report-only
- `NEW_SOURCES_PENDING` → wait for ingest + Tier 1/Tier 2
- `NO_ACTIONABLE_RESULT` → defer or require human review

Only `SUFFICIENT_FOR_REPAIR` automatically triggers repair.

### 9. Separate Lifecycle State from Disposition

- `remediation_status` tracks workflow stage (OPEN, TRIAGED, RESEARCH_PENDING, etc.)
- `disposition` tracks terminal outcome (ACTIVE, RESOLVED, FALSE_POSITIVE, WONT_FIX, ABANDONED)
- Clean separation for analytics, UI, and policy.

### 10. Policy-Versioned Debt Scoring

- Raw finding counts stored by category and severity.
- Debt score is a derived metric from a versioned debt policy.
- Weights are tunable without corrupting historical data.
- Score + category breakdown trendable over time.

---

## Module Organization

```
src/hephaestus/forgebase/
  linting/
    __init__.py
    engine.py                   # LintEngine orchestrator
    state.py                    # VaultLintState query facade
    fingerprint.py              # Finding fingerprint computation + dedup
    scoring.py                  # Knowledge debt score computation

    analyzer.py                 # LintAnalyzer ABC
    analyzers/
      __init__.py
      anthropic_analyzer.py     # First LintAnalyzer implementation

    detectors/
      __init__.py
      base.py                   # LintDetector ABC + RawFinding model
      stale_evidence.py
      orphaned_page.py
      duplicate_page.py
      broken_reference.py
      missing_canonical.py
      unresolved_todo.py
      unsupported_claim.py
      contradictory_claim.py
      source_gap.py
      missing_figure.py
      resolvable_by_search.py

    remediation/
      __init__.py
      policy.py                 # RemediationPolicy + route assignment
      triage.py                 # Route assignment + override logic
      batcher.py                # Finding batching into repair groups
      research_job.py           # FindingResearchJob orchestrator
      repair_job.py             # RepairWorkbookJob orchestrator
      verification_job.py       # FindingVerificationJob orchestrator
```

---

## New Domain Model

### Enumerations

```
RemediationStatus   — OPEN, TRIAGED, RESEARCH_PENDING, RESEARCH_COMPLETED,
                      REPAIR_PENDING, REPAIR_WORKBOOK_CREATED, AWAITING_REVIEW,
                      MERGED_PENDING_VERIFY, VERIFIED
RemediationRoute    — REPORT_ONLY, RESEARCH_ONLY, REPAIR_ONLY, RESEARCH_THEN_REPAIR
RouteSource         — POLICY, USER, AUTOMATION, RETRIAGE
FindingDisposition  — ACTIVE, RESOLVED, FALSE_POSITIVE, WONT_FIX, ABANDONED
ResearchOutcome     — SUFFICIENT_FOR_REPAIR, INSUFFICIENT_EVIDENCE,
                      NEW_SOURCES_PENDING, NO_ACTIONABLE_RESULT
```

Update existing `FindingCategory`:
- Rename `STALE_PAGE` → `STALE_EVIDENCE`
- Rename `WEAK_BACKLINK` → `BROKEN_REFERENCE`

### Extended LintFinding

Add fields to existing `LintFinding` model:

| Field | Type | Notes |
|-------|------|-------|
| `finding_fingerprint` | `str` | Stable dedup key |
| `remediation_status` | `RemediationStatus` | Workflow stage |
| `disposition` | `FindingDisposition` | Terminal outcome |
| `remediation_route` | `RemediationRoute \| None` | Current route |
| `route_source` | `RouteSource \| None` | Who assigned the route |
| `detector_version` | `str` | Which detector version |
| `confidence` | `float` | Detector confidence |
| `affected_entity_ids` | `list[EntityId]` | Pages, claims, sources |
| `research_job_id` | `EntityId \| None` | If research triggered |
| `repair_workbook_id` | `EntityId \| None` | If repair workbook created |
| `repair_batch_id` | `EntityId \| None` | Grouping key |
| `verification_job_id` | `EntityId \| None` | If verification triggered |

### RepairBatch

| Field | Type | Notes |
|-------|------|-------|
| `batch_id` | `EntityId` | |
| `vault_id` | `EntityId` | |
| `batch_fingerprint` | `str` | Stable idempotency key |
| `batch_strategy` | `str` | BY_PAGE, BY_CONCEPT, BY_CATEGORY |
| `batch_reason` | `str` | Human-readable explanation |
| `finding_ids` | `list[EntityId]` | Findings in this batch |
| `policy_version` | `str` | |
| `workbook_id` | `EntityId \| None` | Created workbook |
| `created_by_job_id` | `EntityId` | |
| `created_at` | `datetime` | |

### ResearchPacket

| Field | Type | Notes |
|-------|------|-------|
| `packet_id` | `EntityId` | |
| `finding_id` | `EntityId` | |
| `vault_id` | `EntityId` | |
| `augmentor_kind` | `str` | "perplexity", "noop" |
| `outcome` | `ResearchOutcome` | Classification of results |
| `created_at` | `datetime` | |

### ResearchPacketDiscoveredSource

| Field | Type | Notes |
|-------|------|-------|
| `id` | `EntityId` | |
| `packet_id` | `EntityId` | FK to ResearchPacket |
| `url` | `str` | |
| `title` | `str` | |
| `summary` | `str` | |
| `relevance` | `float` | |
| `trust_tier` | `str` | |

### ResearchPacketIngestJob

| Field | Type | Notes |
|-------|------|-------|
| `packet_id` | `EntityId` | FK to ResearchPacket |
| `ingest_job_id` | `EntityId` | Follow-on source ingest job |

### ResearchPacketContradictionResult

| Field | Type | Notes |
|-------|------|-------|
| `packet_id` | `EntityId` | FK to ResearchPacket |
| `summary` | `str` | |
| `resolution` | `str` | claim_a_stronger / claim_b_stronger / both_valid / insufficient_evidence |
| `confidence` | `float` | |
| `supporting_evidence` | `list[str]` | |

### ResearchPacketFreshnessResult

| Field | Type | Notes |
|-------|------|-------|
| `packet_id` | `EntityId` | FK to ResearchPacket |
| `is_stale` | `bool` | |
| `reason` | `str` | |
| `newer_evidence` | `list[str]` | |

### LintReport

| Field | Type | Notes |
|-------|------|-------|
| `report_id` | `EntityId` | |
| `vault_id` | `EntityId` | |
| `workbook_id` | `EntityId \| None` | |
| `job_id` | `EntityId` | |
| `finding_count` | `int` | |
| `findings_by_category` | `dict[str, int]` | |
| `findings_by_severity` | `dict[str, int]` | |
| `debt_score` | `float` | 0-100 |
| `debt_policy_version` | `str` | |
| `raw_counts` | `dict` | Full breakdown for trending |
| `created_at` | `datetime` | |

---

## Lint Engine

### VaultLintState (Query Facade)

Branch-aware query facade constructed once per lint run. Not an eager materialization — cached lazy views with helper selectors.

```python
class VaultLintState:
    """Read-only, branch-aware query facade over vault state."""

    def __init__(self, uow: AbstractUnitOfWork, vault_id: EntityId,
                 workbook_id: EntityId | None = None): ...

    # Cached lazy accessors
    async def pages(self) -> list[tuple[Page, PageVersion]]: ...
    async def claims(self) -> dict[EntityId, tuple[ClaimVersion, list[ClaimSupport], list[ClaimDerivation]]]: ...
    async def links(self) -> list[tuple[Link, LinkVersion]]: ...
    async def sources(self) -> list[tuple[Source, SourceVersion]]: ...
    async def candidates(self) -> list[ConceptCandidate]: ...
    async def existing_findings(self) -> list[LintFinding]: ...

    # Helper selectors (avoid full scans in detectors)
    async def claims_without_support(self) -> list[tuple[Claim, ClaimVersion]]: ...
    async def pages_with_zero_inbound_links(self) -> list[Page]: ...
    async def claims_past_freshness(self, now: datetime) -> list[tuple[Claim, ClaimVersion]]: ...
    async def candidates_promotion_worthy(self, policy: SynthesisPolicy) -> list[ConceptCandidate]: ...
    async def page_content(self, page_id: EntityId) -> bytes: ...
```

### LintDetector ABC

```python
class LintDetector(ABC):
    name: str
    categories: list[FindingCategory]
    version: str  # detector version for fingerprinting

    @abstractmethod
    async def detect(self, state: VaultLintState) -> list[RawFinding]: ...

    @abstractmethod
    async def is_resolved(
        self, original_finding: LintFinding,
        current_state: VaultLintState,
        new_findings: list[RawFinding],
    ) -> bool:
        """Detector-specific verification contract."""
```

### RawFinding

```python
@dataclass
class RawFinding:
    category: FindingCategory
    severity: FindingSeverity
    description: str
    affected_entity_ids: list[EntityId]
    normalized_subject: str  # for fingerprinting
    suggested_action: str | None = None
    confidence: float = 1.0
    page_id: EntityId | None = None
    claim_id: EntityId | None = None
```

### LintEngine

```python
class LintEngine:
    def __init__(
        self,
        uow_factory: Callable[[], AbstractUnitOfWork],
        detectors: list[LintDetector],
        lint_analyzer: LintAnalyzer | None,
        lint_service: LintService,
        default_actor: ActorRef,
        remediation_policy: RemediationPolicy | None = None,
        debt_policy: DebtScoringPolicy | None = None,
    ): ...

    async def run_lint(
        self,
        vault_id: EntityId,
        workbook_id: EntityId | None = None,
        config: dict | None = None,
    ) -> LintReport:
        """Full vault lint pass.

        1. Schedule LintJob
        2. Build VaultLintState (query facade)
        3. Run each detector → collect RawFindings
        4. Fingerprint + dedup against existing findings
        5. Open new findings via LintService
        6. Reopen findings whose fingerprint reappears after resolution
        7. Triage: assign remediation route per policy
        8. Compute knowledge debt score
        9. Complete lint job
        10. Return LintReport
        """
```

### 11 Detectors

| Detector | Category | Type | Prefilter | Logic |
|----------|----------|------|-----------|-------|
| `StaleEvidenceDetector` | STALE_EVIDENCE | Data | `claims_past_freshness(now)` | Claims where `fresh_until < now`, aggregate per page |
| `OrphanedPageDetector` | ORPHANED_PAGE | Data | `pages_with_zero_inbound_links()` | Pages with no incoming links (excluding source cards and index pages) |
| `DuplicatePageDetector` | DUPLICATE_PAGE | Data | Full page list | Pages with matching normalized titles or overlapping page_keys |
| `BrokenReferenceDetector` | BROKEN_REFERENCE | Data | Full link list | Links where target entity doesn't exist in current state |
| `MissingCanonicalDetector` | MISSING_CANONICAL | Data | `candidates_promotion_worthy(policy)` | Promotion-worthy candidates with no resolved_page_id |
| `UnresolvedTodoDetector` | UNRESOLVED_TODO | Data | Full page content scan | TODO/FIXME/TBD patterns in page content |
| `UnsupportedClaimDetector` | UNSUPPORTED_CLAIM | LLM | `claims_without_support()` | Claims with SUPPORTED status but no ClaimSupport, then LintAnalyzer grades remaining |
| `ContradictoryClaimDetector` | CONTRADICTORY_CLAIM | LLM | Same-concept claim pairs | Prefilter by concept page, then LintAnalyzer checks contradiction on reduced pairs |
| `SourceGapDetector` | SOURCE_GAP | LLM | Concepts with < N sources | LintAnalyzer assesses whether thin evidence is a real gap |
| `MissingFigureDetector` | MISSING_FIGURE_EXPLANATION | Data | Pages with image refs | Pages referencing images without descriptions |
| `ResolvableBySearchDetector` | RESOLVABLE_BY_SEARCH | LLM | Claims with weak support | LintAnalyzer checks if external search could strengthen |

### LintAnalyzer ABC

```python
class LintAnalyzer(ABC):
    """Lint-specific LLM reasoning — dedicated contract, separate from CompilerBackend."""

    @abstractmethod
    async def detect_contradictions(
        self, claim_pairs: list[tuple[str, str]],
    ) -> list[ContradictionResult]: ...

    @abstractmethod
    async def assess_source_gaps(
        self, concept: str, evidence_count: int, claims: list[str],
    ) -> SourceGapAssessment: ...

    @abstractmethod
    async def check_resolvable_by_search(
        self, claim: str, existing_support: list[str],
    ) -> ResolvabilityAssessment: ...
```

### Knowledge Debt Scoring

```python
@dataclass
class DebtScoringPolicy:
    policy_version: str = "1.0.0"
    weights: dict[FindingSeverity, float] = field(default_factory=lambda: {
        FindingSeverity.CRITICAL: 10.0,
        FindingSeverity.WARNING: 3.0,
        FindingSeverity.INFO: 1.0,
    })
    normalization_base: str = "pages_plus_claims"

def compute_debt_score(
    findings_by_severity: dict[FindingSeverity, int],
    vault_size: int,  # pages + claims count
    policy: DebtScoringPolicy,
) -> float:
    """Returns 0-100 score. Lower is healthier."""
```

Raw counts by category and severity are stored in `LintReport` for trending. The score is always a derived metric.

---

## Remediation Pipeline

### Remediation Policy

```python
@dataclass
class RemediationPolicy:
    policy_version: str = "1.0.0"
    default_route: RemediationRoute = RemediationRoute.REPORT_ONLY
    rules: list[RemediationRule] = field(default_factory=list)

@dataclass
class RemediationRule:
    category: FindingCategory | None      # None = any category
    severity: FindingSeverity | None      # None = any severity
    route: RemediationRoute
    priority: int = 0                     # higher priority wins on conflict
```

Policy engine resolution order: exact match (category + severity) → category-only → severity-only → default.

### Triage

```python
async def triage_findings(
    findings: list[LintFinding],
    policy: RemediationPolicy,
) -> list[LintFinding]:
    """Assign remediation route to each finding based on policy.
    Updates remediation_status → TRIAGED, sets route + route_source=POLICY.
    """
```

Routes are overridable (user can change route, route_source becomes USER) and reversible (abandoned repair can be retriaged under RETRIAGE).

### Finding Batching

```python
def batch_findings(
    findings: list[LintFinding],
    strategy: str = "auto",
) -> list[RepairBatch]:
    """Group findings into workbook-appropriate batches.

    Strategies:
    - BY_PAGE: group findings affecting the same page
    - BY_CONCEPT: group findings in the same concept cluster
    - BY_CATEGORY: group findings of the same type
    - auto: smart grouping (same page first, then concept, then category)
    """
```

### Durable Job Types

**1. LintJob** (exists) — produces findings via LintEngine.

**2. FindingResearchJob**

```
Input: finding_id or finding_batch, vault_id
Flow:
  1. Read finding + affected entities
  2. Dispatch to ResearchAugmentor based on category:
     - CONTRADICTORY_CLAIM → augmentor.resolve_contradiction()
     - SOURCE_GAP → augmentor.find_supporting_evidence()
     - STALE_EVIDENCE → augmentor.check_freshness()
     - RESOLVABLE_BY_SEARCH → augmentor.find_supporting_evidence()
     - UNSUPPORTED_CLAIM → augmentor.find_supporting_evidence()
  3. Create ResearchPacket + normalized child records
  4. Classify outcome: SUFFICIENT / INSUFFICIENT / NEW_SOURCES / NO_RESULT
  5. If new sources discovered: schedule ingest jobs (follow-on)
  6. Update finding: status → RESEARCH_COMPLETED, research_job_id set
  7. If outcome == SUFFICIENT and route includes repair: schedule RepairWorkbookJob
  8. If outcome == NEW_SOURCES_PENDING: finding stays in RESEARCH_COMPLETED, awaits pipeline
  9. Emit finding.research_completed + research.packet_created
```

**3. RepairWorkbookJob**

```
Input: repair_batch_id, vault_id, research_packet_ids?
Flow:
  1. Create workbook: purpose=LINT_REPAIR, name from batch
  2. For each finding in batch, based on category:
     - DUPLICATE_PAGE → merge pages on branch (keep best, redirect links)
     - ORPHANED_PAGE → create backlinks or tombstone
     - BROKEN_REFERENCE → remove broken links or update targets
     - CONTRADICTORY_CLAIM →
       IF research resolved it: update claim statuses on branch
       ELSE: create/update open-question page representing the contradiction
     - UNSUPPORTED_CLAIM → strengthen support if research found evidence,
       or downgrade claim status on branch
     - STALE_EVIDENCE → update validated_at/fresh_until, re-validate claims
  3. All mutations on workbook branch
  4. Update findings: status → REPAIR_WORKBOOK_CREATED
  5. Emit repair.workbook_created
```

**4. FindingVerificationJob**

```
Input: finding_ids, vault_id, merged_revision_id
Flow:
  1. Build VaultLintState for current canonical state
  2. For each finding:
     a. Get the original detector
     b. Call detector.is_resolved(original_finding, current_state, new_findings)
     c. If resolved: disposition → RESOLVED, status → VERIFIED
     d. If not resolved: disposition stays ACTIVE, status → OPEN (reopened)
  3. Emit finding.resolved or finding.reopened per finding
```

---

## Event Taxonomy Extensions

Add to `EVENT_TAXONOMY`:

```
finding.triaged
finding.route_assigned
finding.research_requested
finding.research_completed
finding.repair_requested
research.packet_created
repair.batch_created
repair.workbook_created
repair.workbook_merged
repair.workbook_abandoned
finding.verification_requested
finding.resolved
finding.reopened
finding.false_positive
finding.wont_fix
finding.abandoned
```

---

## Repository Extensions

New repositories needed:

```
repository/
  research_packet_repo.py       # ResearchPacket + child records
  repair_batch_repo.py          # RepairBatch
  lint_report_repo.py           # LintReport

store/sqlite/
  research_packet_repo.py
  repair_batch_repo.py
  lint_report_repo.py
```

Existing `FindingRepository` needs extension:
- `update_remediation_status(finding_id, status, route?, route_source?)`
- `update_disposition(finding_id, disposition)`
- `find_by_fingerprint(vault_id, fingerprint) -> LintFinding | None`
- `list_by_disposition(vault_id, disposition) -> list[LintFinding]`
- `list_by_remediation_status(vault_id, status) -> list[LintFinding]`

UoW needs: `research_packets`, `repair_batches`, `lint_reports` accessors.

---

## What Gets Implemented

### Components
- LintEngine orchestrator + VaultLintState query facade
- 11 detectors (6 data-only with prefilters, 5 LLM-assisted with prefilter → analysis)
- LintAnalyzer ABC + Anthropic implementation
- Finding fingerprint + dedup + reopen logic
- Remediation policy engine (exact match → category fallback → severity fallback → default)
- Triage + route assignment + override
- Finding batching (BY_PAGE, BY_CONCEPT, BY_CATEGORY, auto)
- FindingResearchJob + ResearchPacket (structured, not dict bags)
- Research outcome classification (SUFFICIENT / INSUFFICIENT / NEW_SOURCES / NO_RESULT)
- RepairWorkbookJob (structural repairs + contradiction representation)
- FindingVerificationJob with detector-specific is_resolved()
- Knowledge debt scoring (policy-versioned, trendable)
- Extended domain model (RemediationStatus, RemediationRoute, RouteSource, FindingDisposition, ResearchOutcome + all entities)
- New repos + SQLite implementations + schema extensions
- Event taxonomy extensions (16 new events)
- Factory wiring

### Minimum Real Flows
1. Lint a vault with ingested + compiled sources → findings produced for multiple categories
2. Triage findings → remediation routes assigned by policy
3. Research job for a SOURCE_GAP finding → ResearchPacket created with discovered sources
4. Research outcome classified as SUFFICIENT → repair workbook auto-scheduled
5. Repair workbook created with proposed fixes for a batch of findings
6. Merge repair workbook → verification job runs → findings marked RESOLVED
7. Re-lint vault → previously resolved findings stay resolved, new issues detected
8. Contradiction handling: research cannot settle it → open-question page created, finding marked RESOLVED with honest representation

### What Is NOT In Sub-project 3
- Genesis/DeepForge vault-aware invention (Sub-project 4)
- Pantheon knowledge governance (Sub-project 4)
- Multi-agent knowledge teams (Sub-project 5)
- Cross-vault fusion (Sub-project 5)
- Web UI (Sub-project 5)
- Full CLI surface (Sub-project 5)
