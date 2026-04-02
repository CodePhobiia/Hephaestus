# BranchGenome DAG — Trimmed V1 Build Spec

Date: 2026-04-01
Status: approved-for-implementation (trimmed V1 only)

## Decision

We are **not** implementing the full BranchGenome DAG system yet.
We are implementing a **trimmed V1** that preserves the core useful idea:

> Hephaestus should branch over **partial structural commitments** and promote the branches most likely to remain novel and valid under later pressure.

The following parts are **in scope** for V1:
- in-memory `BranchGenome` representation
- lightweight `BranchArena`
- partial commitment branching before full translation
- descendant spread / perturbation assay
- rejection ledger for anti-repetition and collapse memory
- promotion / pruning logic with hard resource caps
- observability hooks and tests

The following parts are **explicitly out of scope** for V1:
- full persistent DAG storage
- branch merging
- dormant branch reactivation
- learned survival forecasting model
- causal ancestor/backfill machinery
- global rollout replacement of the linear pipeline

---

## Why this version

The deep Hephaestus architecture run converged on a coherent direction, but also showed clear over-design risk.

The usable kernel is:
1. represent early invention state as partial commitments instead of near-finished inventions
2. fork a few meaningful variants before translation hardens them
3. test which variants survive perturbation and verification pressure
4. remember which structures collapsed before so the system stops repeating them

This should be implemented as a **layer around** the existing pipeline, not a replacement of the entire pipeline.

---

## V1 Design Goals

1. Improve output quality under fixed or near-fixed budget
2. Reduce late-stage collapse into generic baselines
3. Preserve genuinely strange but viable lines longer
4. Keep runtime and token overhead bounded and observable
5. Require minimal disruption to the current 5-stage Genesis pipeline

---

## Core Ontology

### BranchGenome
A `BranchGenome` is a partial invention state, not a finished invention.
It carries only the currently selected structural commitments.

A branch is defined by:
- which mechanism claims have been accepted so far
- which structural mappings have been accepted so far
- which target-side design commitments have been accepted so far
- which open questions remain unresolved
- what collapse / repetition evidence already counts against it

### Commitment
A commitment is a unit of structural choice.

V1 commitment kinds:
- `mechanism_claim`
- `mapping_claim`
- `target_binding`
- `resource_policy`
- `verification_assertion`

Each commitment has:
- `id`
- `kind`
- `statement`
- `confidence`
- `reversible`
- `provenance`

### Reversible vs irreversible
For V1:
- **reversible** = any commitment before full translation finalization
- **irreversible** = a commitment promoted into the translated candidate sent to verification

We are **not** implementing complex partial rollback semantics beyond this in V1.

---

## V1 Files / Modules

Add a new package:

```text
src/hephaestus/branchgenome/
  __init__.py
  models.py
  arena.py
  ledger.py
  assay.py
  strategy.py
```

### `models.py`
Contains:
- `CommitmentKind`
- `BranchStatus`
- `Commitment`
- `BranchGenome`
- `BranchMetrics`

### `arena.py`
Contains:
- `BranchArena`
- `seed_branches_from_translation_inputs(...)`
- `add_branch(...)`
- `promote_top_k(...)`
- `prune_over_budget(...)`

### `ledger.py`
Contains:
- `RejectionLedger`
- normalized structural fingerprint extraction
- overlap / similarity scoring against prior rejected and accepted outputs

### `assay.py`
Contains:
- descendant spread / perturbation evaluation
- quick survival scoring

### `strategy.py`
Contains:
- branching policy per mode
- score weighting
- token/runtime budgets

---

## Data Structures

## `Commitment`
```python
@dataclass(frozen=True)
class Commitment:
    id: str
    kind: CommitmentKind
    statement: str
    confidence: float
    reversible: bool
    provenance: tuple[str, ...] = ()
```

## `BranchMetrics`
```python
@dataclass
class BranchMetrics:
    novelty_hint: float = 0.0
    spread_score: float = 0.0
    rejection_overlap: float = 0.0
    collapse_risk: float = 0.0
    verification_hint: float = 0.0
    score_survival: float = 0.0
    token_cost_estimate: int = 0
    runtime_ms_estimate: int = 0
```

## `BranchGenome`
```python
@dataclass
class BranchGenome:
    branch_id: str
    parent_id: str | None
    source_candidate_index: int
    stage_cursor: str
    commitments: tuple[Commitment, ...]
    open_questions: tuple[str, ...]
    rejected_patterns: tuple[str, ...] = ()
    metrics: BranchMetrics = field(default_factory=BranchMetrics)
    status: BranchStatus = BranchStatus.ACTIVE
```

## `BranchArena`
```python
@dataclass
class BranchArena:
    branches: dict[str, BranchGenome]
    children: dict[str, list[str]]
    promoted_ids: list[str]
    pruned_ids: list[str]
```

V1 is **in-memory only**.
No DB. No full persistence.

---

## Genesis Integration Plan

We are not replacing the current stages.
We are inserting branching between scoring and translation.

Current flow:
- decompose
- search
- score
- translate
- verify

V1 flow:
- decompose
- search
- score
- **branchgenome: seed partial branches from top scored candidates**
- **branchgenome: assay + promote/prune**
- translate promoted branches
- verify

### Why here
This is the safest insertion point:
- we already have scored candidates
- we have not yet committed to full translation text
- we can compare multiple partial directions cheaply

---

## How seeding works

For each top scored candidate selected for translation:
- create 2–4 partial branches

Initial branch variants:
1. **mechanism-pure**
   - emphasize source mechanism fidelity
2. **target-feasible**
   - emphasize implementability / lower burden
3. **novelty-max**
   - emphasize target surprise / anti-baseline distance
4. **constraint-tight**
   - emphasize satisfying hard constraints explicitly

These are not full translated architectures.
They are partial commitment sets.

---

## Branch Mutation Policy

V1 mutation operators:
- tighten mechanism claim
- tighten target binding
- add resource policy
- add explicit failure guard
- remove weak / generic commitment
- rephrase in target-domain-only language

No merge.
No ancestor reconstruction.
No dormant reactivation.

Mutation count by mode:
- `STANDARD`: at most 2 variants per scored candidate
- `AGGRESSIVE`: at most 3
- `MAXIMUM`: at most 4

---

## Descendant Spread / Perturbation Assay

This is the key V1 evaluation mechanism.

For each active branch:
- render a minimal partial prompt from commitments
- apply a small perturbation set
- run cheap structural checks on the results

Perturbations:
1. target-domain-only rewrite
2. constraint order shuffled
3. one hard constraint emphasized
4. source-domain vocabulary suppressed

Checks:
- parseable structured output
- still distinct from banned baseline language
- still load-bearing in concept
- still coherent under target-domain phrasing

### Output metrics
- `spread_score`
- `collapse_risk`
- `verification_hint`

### Survival score
V1 should use a simple heuristic, not a learned model:

```python
score_survival = (
    0.35 * novelty_hint
    + 0.30 * spread_score
    + 0.20 * verification_hint
    - 0.15 * collapse_risk
    - 0.20 * rejection_overlap
)
```

Weights should live in `strategy.py`.

---

## Rejection Ledger

Purpose:
- remember patterns that collapsed before
- penalize repeated decorative/derivative structures
- distinguish accepted novelty from recycled novelty theater

### Inputs
Use normalized fingerprints from:
- `translation.key_insight`
- `translation.architecture`
- `phase1_abstract_mechanism`
- branch commitment statements

### Outcomes to store
- `accepted`
- `invalid`
- `decorative`
- `derivative`
- `baseline_overlap`

### V1 implementation
Do **not** build Count-Min Sketch + FAISS yet.
Use a simple JSONL or in-memory + existing failure/anti-memory surface.

Suggested file:
- `~/.hephaestus/branchgenome-rejections.jsonl`

Suggested API:
```python
class RejectionLedger:
    def overlap(self, fingerprint: str) -> float: ...
    def record(self, fingerprint: str, outcome: str, summary: str) -> None: ...
```

V1 can use simple lexical/embedding similarity via current local tools already in repo if convenient.

---

## Resource Controls

Hard caps are mandatory.

### STANDARD
- max seeded branches: 6
- max promoted branches: 3
- assay perturbations per branch: 3
- extra token budget target: <= 20% above current path

### AGGRESSIVE
- max seeded branches: 9
- max promoted branches: 4
- assay perturbations per branch: 4
- extra token budget target: <= 40%

### MAXIMUM
- max seeded branches: 12
- max promoted branches: 5
- assay perturbations per branch: 4
- extra token budget target: <= 70%

### Pruning rules
Prune immediately if:
- branch becomes obviously baseline-equivalent
- branch is structurally duplicate of stronger sibling
- branch exceeds per-branch token cost estimate
- branch fails 3/4 perturbation checks

---

## Observability

Add lightweight metrics only.

Track:
- `branches_seeded`
- `branches_promoted`
- `branches_pruned`
- `avg_spread_score`
- `avg_rejection_overlap`
- `avg_collapse_risk`
- `tokens_spent_branching`
- `tokens_saved_by_pruning`
- `promoted_branch_outcomes`

V1 logging can be JSONL or standard logger lines.
No dashboard required yet.

---

## Failure Modes and Mitigations

### 1. Branch explosion
Mitigation:
- hard caps
- no merge/reactivation in V1
- prune duplicates early

### 2. Generic branches score well because they survive perturbation
Mitigation:
- novelty hint and rejection overlap must actively suppress genericity
- add explicit anti-baseline lexical checks

### 3. Assay becomes too expensive
Mitigation:
- only assay branched candidates, not every search result
- use cheap partial renders
- small perturbation set

### 4. Branching adds complexity but no quality gain
Mitigation:
- make feature flaggable
- benchmark against baseline
- remove if win is not clear

### 5. Wrong things become “irreversible” too early
Mitigation:
- V1 only hardens at translation output boundary

---

## Rollout Plan

## V1
Build now.
- models
- arena
- rejection ledger
- perturbation assay
- scoring + pruning
- wire into Genesis between score and translate
- feature flag off by default or guarded by explicit config

## V2
Only if V1 wins.
- checkpointed branch state
- dormant branch reactivation
- better duplicate clustering
- richer metrics

## V3
Only if V2 still wins.
- persistent DAG storage
- more sophisticated forecasting
- optional merge logic

---

## Tests Required

### Unit tests
- commitment creation / hashing stability
- branch arena add/promote/prune correctness
- rejection ledger record + overlap behavior
- perturbation assay stability scoring
- duplicate suppression

### Integration tests
- Genesis with BranchGenome off vs on
- promoted branches feed translator correctly
- token overhead stays within configured caps
- quality-path does not break output formatting / export

### Benchmark tests
Use fixed internal problem set and compare:
- verifier pass rate
- load-bearing pass rate
- decorative rate
- novelty score distribution
- cost overhead

Target threshold for keeping V1:
- at least **+10%** improvement in accepted/high-quality outputs
- with no more than **+20–30%** cost increase in STANDARD mode

---

## Final recommendation

Implement **trimmed V1 now**.
Do **not** implement the full DAG.

The right first build is:
- partial commitment branching
- survival-style perturbation assay
- rejection memory
- bounded promote/prune loop

If V1 proves itself, grow it.
If not, kill it without having built a monster.
