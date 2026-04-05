# Hephaestus Transliminality Engine
## Feature Handover / Developer Spec
### Version 0.1

## 1. Executive summary

The **Transliminality Engine** is the missing Layer 2 in Hephaestus.

Hephaestus already has a strong **negative creative force**: it blocks obvious paths, suppresses prior-art grooves, and pushes generation away from default solutions. That is necessary, but it is not enough. Without a second force, the system can still drift into:
- second-best conventional answers in unusual clothing
- novelty theater
- weird-but-empty ideas
- decorative analogy

The Transliminality Engine adds the **positive creative force**:

> retrieve structurally compatible mechanisms from remote domains, validate whether the analogy is real, and inject that bridge into invention-time reasoning.

The subsystem sits between:
- **ForgeBase / cross-vault fusion** for knowledge retrieval
- **Genesis / DeepForge** for generation
- **Pantheon** for verification and objection handling

It changes the invention loop from:

1. avoid the obvious

to:

1. avoid the obvious  
2. cross a real boundary with a valid structural bridge  
3. verify that the bridge survives constraints and is not ornamental

This is what turns Hephaestus from a novelty engine into a **directed cross-domain synthesis engine**.

---

## 2. Product thesis

### 2.1 Problem

Hephaestus can already push an LLM away from standard answers. That creates search space, but not direction.

What is missing is a subsystem that can say:

- not just “avoid the default”
- but “borrow the functional logic of this remote mechanism”
- and “do not borrow it literally”
- and “preserve these constraints while transferring it”

That is the role of Transliminality.

### 2.2 Thesis

The best non-obvious inventions are often not random. They are **structure-preserving transfers** from one domain to another.

Examples in principle:
- a gating mechanism in one field becomes a selective control mechanism in another
- a redundancy pattern in distributed systems becomes a resilience pattern in logistics
- a staged-activation pattern in biology becomes a safety or escalation mechanism elsewhere

Transliminality is the subsystem that lets Hephaestus find and use those bridges intentionally.

### 2.3 Outcome

The feature should produce:
- better cross-domain invention candidates
- better justification for why a bridge is valid
- better objections when a bridge is invalid
- a compounding library of validated and rejected analogies inside ForgeBase

---

## 3. Goals and non-goals

### 3.1 Goals

The subsystem must:

- build a structured, revision-pinned representation of the invention problem
- retrieve remote, policy-eligible knowledge from ForgeBase and other vaults
- distinguish **structural analogy** from generic semantic similarity
- assemble a provenance-rich `TransliminalityPack`
- inject that pack into existing Hephaestus invention points
- score integration, not just novelty
- write accepted and rejected analogical artifacts back into ForgeBase
- prevent speculative or contested artifacts from poisoning strict invention channels

### 3.2 Non-goals

The subsystem does **not**:

- replace DeepForge pressure
- replace the fusion subsystem
- replace Pantheon
- replace ForgeBase
- become a generic RAG layer
- auto-promote speculative invention output into strict baseline knowledge
- accept lexical similarity as proof of transferable structure

---

## 4. System boundary

The Transliminality Engine is a **top-level invention subsystem**.

It is not:
- a prompt template
- a ForgeBase page type
- a DeepForge variant
- a Pantheon plugin

It is a run-time orchestration layer that consumes existing systems and produces invention-time structured context.

### 4.1 Owns

The engine owns:
- problem-conditioned cross-domain retrieval
- role-signature construction
- bridge candidate generation
- structural analogy validation
- transfer-opportunity synthesis
- transliminality pack assembly
- integration scoring
- writeback of transliminality artifacts

### 4.2 Does not own

It does not own:
- raw prior-art blocking
- generic research discovery
- low-level vector storage
- final invention adjudication
- generic vault storage semantics
- deep candidate generation inside Genesis

---

## 5. Architecture overview

### 5.1 Position in the invention stack

The invention stack becomes:

- **Layer 1 — Pressure**
  - block obvious paths
  - suppress prior-art grooves
  - avoid default explored families

- **Layer 2 — Transliminality**
  - retrieve remote, structurally compatible mechanisms
  - validate analogical maps
  - inject directed cross-domain context

- **Layer 3 — Verification**
  - Pantheon attacks the bridge
  - reject ornamental analogy
  - enforce constraint-respecting transfer

### 5.2 Core dependencies

The subsystem reuses existing product assets:

- `AntiTrainingPressure.apply(extra_blocked_paths=...)`
- `LensSelector.select_plan(reference_context=...)`
- `PantheonCoordinator.prepare_pipeline(baseline_dossier=...)`
- ForgeBase vaults, context packs, and writeback artifacts
- Fusion retrieval + structural analogy analysis stack
- existing run integration bridges

### 5.3 New top-level package

```text
src/hephaestus/transliminality/
  __init__.py

  domain/
    models.py
    enums.py
    policies.py
    scoring.py

  service/
    engine.py
    problem_signature_builder.py
    vault_router.py
    bridge_retriever.py
    pack_assembler.py
    integration_scorer.py
    writeback.py

  adapters/
    forgebase.py
    fusion.py
    genesis.py
    pantheon.py

  prompts/
    role_signature.py
    analogy_validation.py
    transfer_synthesis.py
    integration_grading.py

  factory.py
```

### 5.4 Layer rules

- `domain/` is pure
- `service/` owns orchestration
- `adapters/` bridge to existing Hephaestus subsystems
- `prompts/` are versioned policy artifacts, not ad hoc strings
- `factory.py` is the only composition root

---

## 6. Runtime pipeline

The Transliminality Engine runs as a **five-stage synchronous invention-time pipeline**, followed by **durable writeback**.

### Stage 0 — Problem conditioning

Build a structured representation of the invention problem:
- goals
- constraints
- dominant failure modes
- required mechanism shape
- control topology
- resource/time scale
- obvious blocked-path context

**Output:** `ProblemRoleSignature`

### Stage 1 — Vault routing

Choose the remote vaults that are worth traversing.

Input:
- home vault(s)
- optional explicitly requested remote vault(s)
- problem signature
- policy

Routing factors:
- domain complementarity
- prior successful bridge history
- role-signature affinity
- novelty potential
- policy exclusions

**Output:** selected remote vault set

### Stage 2 — Bridge retrieval

Use the fusion stack in problem-conditioned mode.

This stage should find:
- similar **roles**
- similar **mechanisms**
- homologous **control/failure patterns**
- transferable **constraint structures**

This is not generic similarity search.

**Output:** `BridgeCandidate[]`

### Stage 3 — Structural analogy analysis

Run the analyzer on shortlisted bridge candidates.

The analyzer must determine:
- what actually maps
- what partially maps
- what fails to map
- where the analogy breaks
- whether the transfer is valid, partial, weak, or invalid

**Output:**
- `AnalogicalMap[]`
- `TransferOpportunity[]`

### Stage 4 — Pack assembly

Assemble invention-time context:
- strict baseline additions
- soft transliminal context
- strict constraint additions
- analogy break warnings
- score preview

**Output:** `TransliminalityPack`

### Stage 5 — Injection

Inject the pack into:
- DeepForge pressure
- lens selection
- Genesis candidate generation
- Pantheon baseline dossier

### Stage 6 — Writeback

Persist:
- role signatures
- accepted analogical maps
- rejected analogical maps
- transfer opportunities
- run manifest

Writeback should be durable and decoupled from the upstream invention run success path.

---

## 7. Core data contracts

## 7.1 `TransliminalityConfig`

```python
@dataclass(frozen=True)
class TransliminalityConfig:
    enabled: bool = True
    mode: TransliminalityMode = TransliminalityMode.BALANCED

    home_vault_ids: list[EntityId] = field(default_factory=list)
    remote_vault_ids: list[EntityId] | None = None
    auto_select_remote_vaults: bool = True
    max_remote_vaults: int = 3

    require_problem_conditioning: bool = True

    prefilter_top_k: int = 40
    analyzed_candidate_limit: int = 12
    maps_to_keep: int = 6
    transfer_opportunities_to_keep: int = 4

    strict_channel_min_confidence: float = 0.80
    soft_channel_min_confidence: float = 0.50

    allow_hypothesis_in_soft_channel: bool = True
    allow_candidates_in_soft_channel: bool = False

    enforce_counterfactual_check: bool = True
    write_back_artifacts: bool = True
```

## 7.2 `TransliminalityRequest`

```python
@dataclass(frozen=True)
class TransliminalityRequest:
    run_id: EntityId
    problem: str
    home_vault_ids: list[EntityId]
    remote_vault_ids: list[EntityId] | None
    branch_id: EntityId | None
    vault_revision_ids: list[EntityId] | None
    config: TransliminalityConfig
```

## 7.3 `RoleSignature`

A role signature is the functional identity of a problem, mechanism, concept, page, claim cluster, or invention artifact.

```python
@dataclass(frozen=True)
class RoleSignature:
    signature_id: EntityId
    subject_ref: EntityRef
    subject_kind: SignatureSubjectKind

    vault_id: EntityId | None
    branch_id: EntityId | None
    vault_revision_id: EntityId | None

    functional_roles: list[RoleTag]
    inputs: list[SignalTag]
    outputs: list[SignalTag]
    constraints: list[ConstraintTag]
    failure_modes: list[FailureModeTag]
    control_patterns: list[ControlPatternTag]
    timescale: TimeScaleTag | None
    resource_profile: list[ResourceTag]
    topology: list[TopologyTag]

    confidence: float
    provenance_refs: list[EntityRef]

    policy_version: str
    created_at: datetime
```

### Initial taxonomy

#### Role tags
- `FILTER`
- `GATE`
- `BUFFER`
- `ROUTE`
- `DETECT`
- `ISOLATE`
- `AMPLIFY`
- `DAMP`
- `COORDINATE`
- `DISTRIBUTE`
- `CHECKPOINT`
- `REPAIR`
- `TRANSFORM`
- `SEQUENCE`
- `REDUNDANCY`
- `SELECT`

#### Constraint tags
- `CAPACITY_LIMIT`
- `LATENCY_BOUND`
- `ENERGY_BOUND`
- `SELECTIVITY_REQUIREMENT`
- `SAFETY_LIMIT`
- `COMPLIANCE_LIMIT`
- `COST_LIMIT`
- `PRECISION_REQUIREMENT`
- `ROBUSTNESS_REQUIREMENT`
- `SCALABILITY_LIMIT`

#### Failure mode tags
- `OVERLOAD`
- `LEAKAGE`
- `CONTAMINATION`
- `DRIFT`
- `OSCILLATION`
- `DEADLOCK`
- `STARVATION`
- `BRITTLENESS`
- `SPOOFING`
- `CASCADE_FAILURE`

#### Control pattern tags
- `FEEDBACK`
- `FEEDFORWARD`
- `THRESHOLDING`
- `STAGED_ACTIVATION`
- `REDUNDANCY`
- `VOTING`
- `BATCHING`
- `DIFFUSION`
- `PRIORITIZATION`
- `ADAPTIVE_ROUTING`

## 7.4 `BridgeCandidate`

Candidate bridge prior to deep analogy validation.

```python
@dataclass(frozen=True)
class BridgeCandidate:
    candidate_id: EntityId

    left_ref: EntityRef
    right_ref: EntityRef
    left_signature_ref: EntityRef
    right_signature_ref: EntityRef

    left_kind: BridgeEntityKind
    right_kind: BridgeEntityKind

    retrieval_reason: RetrievalReason
    similarity_score: float

    left_claim_refs: list[EntityRef]
    right_claim_refs: list[EntityRef]
    left_source_refs: list[EntityRef]
    right_source_refs: list[EntityRef]

    left_revision_ref: EntityId | None
    right_revision_ref: EntityId | None

    epistemic_filter_passed: bool
```

## 7.5 `ComponentMapping`

```python
@dataclass(frozen=True)
class ComponentMapping:
    left_component_ref: EntityRef | None
    right_component_ref: EntityRef | None
    shared_role: str
    mapping_rationale: str
```

## 7.6 `AnalogyBreak`

```python
@dataclass(frozen=True)
class AnalogyBreak:
    category: AnalogyBreakCategory
    description: str
    affected_constraint: str | None
    severity: float
```

## 7.7 `AnalogicalMap`

```python
@dataclass(frozen=True)
class AnalogicalMap:
    map_id: EntityId
    candidate_ref: EntityRef

    shared_role: str
    mapped_components: list[ComponentMapping]

    preserved_constraints: list[str]
    broken_constraints: list[str]
    analogy_breaks: list[AnalogyBreak]

    structural_alignment_score: float
    constraint_carryover_score: float
    grounding_score: float
    confidence: float

    verdict: AnalogicalVerdict
    rationale: str

    provenance_refs: list[EntityRef]
```

### `AnalogicalVerdict`
- `VALID`
- `PARTIAL`
- `WEAK`
- `INVALID`

## 7.8 `TransferOpportunity`

```python
@dataclass(frozen=True)
class TransferOpportunity:
    opportunity_id: EntityId
    map_ref: EntityRef

    title: str
    transferred_mechanism: str
    target_problem_fit: str

    expected_benefit: str
    required_transformations: list[str]
    caveats: list[TransferCaveat]

    confidence: float
    epistemic_state: EpistemicState

    supporting_refs: list[EntityRef]
```

## 7.9 `KnowledgePackEntry`

```python
@dataclass(frozen=True)
class KnowledgePackEntry:
    entry_id: EntityId
    text: str

    origin_kind: PackOriginKind
    claim_ids: list[EntityId]
    page_ids: list[EntityId]
    source_refs: list[EntityRef]

    epistemic_state: EpistemicState
    trust_tier: TrustTier
    salience: float
```

## 7.10 `IntegrationScoreBreakdown`

```python
@dataclass(frozen=True)
class IntegrationScoreBreakdown:
    structural_alignment: float
    constraint_fidelity: float
    source_grounding: float
    counterfactual_dependence: float
    bidirectional_explainability: float
    non_ornamental_use: float
```

## 7.11 `TransliminalityPack`

```python
@dataclass(frozen=True)
class TransliminalityPack:
    pack_id: EntityId
    run_id: EntityId

    problem_signature_ref: EntityRef

    home_vault_ids: list[EntityId]
    remote_vault_ids: list[EntityId]

    bridge_candidates: list[EntityRef]
    validated_maps: list[EntityRef]
    transfer_opportunities: list[EntityRef]

    strict_baseline_entries: list[KnowledgePackEntry]
    soft_context_entries: list[KnowledgePackEntry]
    strict_constraint_entries: list[KnowledgePackEntry]

    integration_score_preview: IntegrationScoreBreakdown
    policy_version: str
    assembler_version: str

    extracted_at: datetime
```

## 7.12 `TransliminalityRunManifest`

```python
@dataclass(frozen=True)
class TransliminalityRunManifest:
    manifest_id: EntityId
    run_id: EntityId

    policy_version: str
    assembler_version: str
    scorer_version: str

    selected_vaults: list[EntityId]
    candidate_count: int
    analyzed_count: int
    valid_map_count: int
    rejected_map_count: int
    transfer_opportunity_count: int

    injected_pack_ref: EntityRef | None
    downstream_outcome_refs: list[EntityRef]

    created_at: datetime
```

---

## 8. Subsystem components

## 8.1 `ProblemRoleSignatureBuilder`

### Responsibility
Convert the invention problem into one or more role signatures.

### Inputs
- raw problem statement
- optional Genesis problem decomposition
- optional home-vault context
- blocked-path info from Layer 1

### Outputs
- one primary `RoleSignature`
- optional sub-signatures for subproblems or mechanisms

### Why it matters
Without role signatures, the system falls back to semantic similarity and loses the structural foundation that makes transliminality useful.

## 8.2 `VaultRouter`

### Responsibility
Pick remote vaults worth traversing.

### Inputs
- home vaults
- problem signature
- explicit remote vaults, if provided
- prior successful fusion history
- policy

### Outputs
- selected remote vault IDs
- routing rationale

### Rules
- never route to forbidden or low-trust vaults
- prefer complementarity over topic overlap
- cap the number of remote vaults for cost and precision

## 8.3 `BridgeRetriever`

### Responsibility
Retrieve plausible cross-vault bridge candidates.

### Internal design
The retriever should reuse the fusion subsystem but operate in problem-conditioned mode.

#### Stage 1 — candidate generation
Use embedding-based and metadata-based retrieval to generate a **diversified candidate set**:
- concept-to-concept
- mechanism-to-mechanism
- claim-cluster-to-claim-cluster
- page-family-to-page-family

#### Stage 2 — policy filter
Exclude:
- rejected or contested strict artifacts
- low-trust sources in strict mode
- ineligible hypotheses for strict channels
- direct duplicates and near-duplicates

#### Stage 3 — shortlist
Return top candidates with diversity constraints.

### Output
- `BridgeCandidate[]`

### Important note
This is not allowed to collapse to “top cosine similar pairs.” Diversity and role coverage are required.

## 8.4 `FusionAnalyzer` adapter

### Responsibility
Validate whether a candidate bridge represents a real structural analogy.

### Behavior
For each candidate:
- determine the shared role
- identify mapped components
- identify preserved and broken constraints
- identify where the analogy breaks
- produce `AnalogicalVerdict`
- optionally synthesize transfer opportunities

### Negative capability
The analyzer must be able to say:
- no valid analogy
- weak analogy
- tempting but invalid analogy

This is essential. If the analyzer cannot reject bridges, the loop will poison itself.

## 8.5 `PackAssembler`

### Responsibility
Assemble strict and soft invention-time context.

### Inputs
- valid maps
- partial maps
- transfer opportunities
- policy
- confidence thresholds

### Outputs
- `strict_baseline_entries`
- `soft_context_entries`
- `strict_constraint_entries`

### Rules
Strict and soft channels must remain separate.

## 8.6 `IntegrationScorer`

### Responsibility
Score how real the cross-domain synthesis is.

### Inputs
- analogical maps
- transfer opportunities
- generated invention candidates
- supporting vault refs
- optional Pantheon signals later in the pipeline

### Outputs
- `IntegrationScoreBreakdown`
- aggregate integration score

## 8.7 `WritebackService`

### Responsibility
Persist accepted and rejected transliminality artifacts into ForgeBase.

### Outputs
- role signature artifacts
- valid map artifacts
- rejected map artifacts
- transfer opportunities
- run manifest

Writeback must be durable and idempotent.

---

## 9. Injection points into existing Hephaestus systems

## 9.1 DeepForge pressure (`extra_blocked_paths`)

Pressure stays Layer 1 and keeps doing negative novelty control.

Transliminality can contribute:
- strict prior-art baselines from validated cross-vault knowledge
- validated explored-path families that should be blocked from literal reuse

It must **not** dump soft hypotheses into blocked paths.

## 9.2 Lens selection (`reference_context`)

This is the main positive injection point.

The engine should inject:
- bridge concepts
- validated analogical maps
- soft transfer opportunities
- role-relevant remote mechanisms

This lets lens planning intentionally choose cross-domain routes.

## 9.3 Genesis candidate generation

Genesis should receive:
- validated analogical maps
- transfer opportunities
- preserved constraints
- broken constraints
- caveat lists

The prompt or structured generation context should tell the model:
- transform, do not transplant literally
- preserve required constraints
- do not use ornamental cross-domain language

## 9.4 Pantheon baseline dossier

Pantheon should receive:
- strict constraint entries
- analogy breaks
- known mismatch warnings
- support/grounding gaps

### New objection taxonomy
Pantheon should add:
- `ORNAMENTAL_ANALOGY`
- `ROLE_MISMATCH`
- `DROPPED_CONSTRAINT`
- `UNGROUNDED_BRIDGE`
- `LITERAL_TRANSPLANT`
- `IGNORED_COST_OF_TRANSFER`
- `UNSUPPORTED_MECHANISM_CARRYOVER`

These are first-class objections, not comments.

---

## 10. Strict vs soft channel policy

This is the most important governance boundary in the subsystem.

## 10.1 Strict baseline channel

Use for:
- `extra_blocked_paths`
- high-confidence prior-art steering
- only policy-eligible context

Allowed sources:
- verified internal inventions
- authoritative external prior art
- canonical mechanism pages
- promoted or explicitly eligible claims

Not allowed:
- raw concept candidates
- unverified invention hypotheses
- contested or rejected invention artifacts
- unresolved objections
- exploratory analogies

## 10.2 Soft context channel

Use for:
- lens selection
- candidate generation scaffolding
- exploratory context

Allowed sources:
- hypotheses
- open questions
- partial analogies
- exploratory bridge concepts
- validated but soft transfer opportunities

Still not allowed:
- content explicitly marked rejected or policy-excluded

## 10.3 Strict constraint channel

Use for Pantheon and other skeptical checks.

Allowed:
- evidence-backed constraints
- validated caveats
- known failure modes
- unresolved issues clearly marked as unresolved

This channel must stay conservative.

## 10.4 Promotion rules

Generated invention output may only move into strict channels if:
- it is verified or policy-eligible
- no unresolved critical objections remain
- derivation chain exists
- lint / consistency pass is green
- trust thresholds pass

No automatic self-promotion.

---

## 11. Evaluation framework

The Transliminality Engine only works if it can distinguish genuine integration from word salad.

## 11.1 Integration dimensions

### Structural alignment
Do mapped components actually play comparable systems roles?

### Constraint fidelity
Did the transfer preserve critical limits and conditions?

### Source grounding
Can the system point to actual vault knowledge supporting the bridge?

### Counterfactual dependence
If the bridge is removed, does the invention collapse back into a weaker or generic answer?

### Bidirectional explainability
Can the system explain why the mapping works and why nearby alternatives fail?

### Non-ornamental use
Is the bridge doing functional work, rather than decorating the narrative?

## 11.2 Integration score

Use geometric mean:

```text
IntegrationScore =
  GM(
    structural_alignment,
    constraint_fidelity,
    source_grounding,
    counterfactual_dependence,
    bidirectional_explainability,
    non_ornamental_use
  )
```

### Why geometric mean
A near-zero failure in one dimension should not be hidden by strong performance in another.

## 11.3 Final invention ranking

The invention stack should eventually combine:
- novelty
- integration
- feasibility
- verifiability

Suggested shape:

```text
FinalScore =
  GM(
    NoveltyScore,
    IntegrationScore,
    FeasibilityScore,
    VerifiabilityScore
  )
```

This prevents:
- highly novel nonsense
- highly grounded conventionality
- flashy but unverifiable analogies

---

## 12. Why the subsystem should work

The subsystem should work for four reasons.

### 12.1 It changes the search target
Instead of “anything non-obvious,” the model is steered toward:
- remote but structurally similar mechanisms
- homologous control patterns
- tested solutions from other domains

That is higher-quality exploration.

### 12.2 It turns analogy into an explicit object
Instead of hoping the model spontaneously discovers a good bridge, we retrieve, validate, and inject one deliberately.

### 12.3 It makes synthesis testable
Role signatures, analogical maps, and integration scoring make it possible to evaluate whether the synthesis is real.

### 12.4 It compounds
Validated maps and rejected bridges are written back into ForgeBase, so future runs get better.

---

## 13. Writeback and artifact model

The subsystem must write back at least four artifact families.

### 13.1 Role signature artifacts
For problem replay, routing, and later analysis.

### 13.2 Analogical map artifacts
Both valid and invalid maps should be persisted.

### 13.3 Transfer opportunity artifacts
These become future retrieval targets and may seed invention runs.

### 13.4 Run manifests
For audit, benchmarking, and reproducibility.

### Storage posture
Writeback should go through the existing ForgeBase integration bridge and artifact layers, not through side-channel file writes.

---

## 14. Internal interfaces

## 14.1 `TransliminalityEngine`

```python
class TransliminalityEngine(Protocol):
    async def build_pack(
        self,
        request: TransliminalityRequest,
    ) -> TransliminalityPack: ...

    async def write_back(
        self,
        pack: TransliminalityPack,
        downstream_outcome_refs: list[EntityRef],
    ) -> TransliminalityRunManifest: ...
```

## 14.2 `ProblemRoleSignatureBuilder`

```python
class ProblemRoleSignatureBuilder(Protocol):
    async def build(
        self,
        problem: str,
        home_vault_ids: list[EntityId],
        branch_id: EntityId | None,
        config: TransliminalityConfig,
    ) -> RoleSignature: ...
```

## 14.3 `BridgeRetriever`

```python
class BridgeRetriever(Protocol):
    async def retrieve(
        self,
        problem_signature: RoleSignature,
        home_vault_ids: list[EntityId],
        remote_vault_ids: list[EntityId],
        config: TransliminalityConfig,
    ) -> list[BridgeCandidate]: ...
```

## 14.4 `FusionAnalyzer` (adapter contract)

```python
class FusionAnalyzer(Protocol):
    async def analyze_candidates(
        self,
        candidates: list[BridgeCandidate],
        problem_signature: RoleSignature,
        config: TransliminalityConfig,
    ) -> tuple[list[AnalogicalMap], list[TransferOpportunity]]: ...
```

## 14.5 `PackAssembler`

```python
class PackAssembler(Protocol):
    async def assemble(
        self,
        run_id: EntityId,
        problem_signature: RoleSignature,
        home_vault_ids: list[EntityId],
        remote_vault_ids: list[EntityId],
        maps: list[AnalogicalMap],
        opportunities: list[TransferOpportunity],
        config: TransliminalityConfig,
    ) -> TransliminalityPack: ...
```

## 14.6 `IntegrationScorer`

```python
class IntegrationScorer(Protocol):
    async def score_pack(
        self,
        pack: TransliminalityPack,
        maps: list[AnalogicalMap],
        opportunities: list[TransferOpportunity],
    ) -> IntegrationScoreBreakdown: ...
```

---

## 15. Events and observability

## 15.1 Domain events

Add at least:
- `transliminality.requested`
- `transliminality.problem_signature_built`
- `transliminality.vaults_selected`
- `transliminality.bridge_retrieval_completed`
- `transliminality.analysis_completed`
- `transliminality.pack_assembled`
- `transliminality.injected`
- `transliminality.writeback_completed`
- `transliminality.failed`
- `transliminality.partial_completed`

## 15.2 Metrics

Track:
- selected remote vault count
- bridge candidates retrieved
- candidates analyzed
- valid vs invalid maps
- transfer opportunities created
- pack size by strict/soft channel
- integration score distribution
- downstream invention score delta with vs without transliminality
- rejection reasons by analogy verdict
- writeback latency and failure rate

## 15.3 Logging / tracing

Every run should log:
- request config
- selected vaults
- candidate retrieval reasons
- rejected bridge reasons
- pack assembly stats
- policy version
- prompt/policy versions used in role signature and analogy analysis

---

## 16. Testing strategy

## 16.1 Unit tests
Cover:
- role signature construction
- routing policy
- pack assembly strict/soft filtering
- score calculation
- promotion policy guards
- objection taxonomy mapping

## 16.2 Integration tests
Cover:
- ForgeBase retrieval → transliminality pack
- pack → lens selection / Genesis
- pack → Pantheon dossier
- writeback into ForgeBase

## 16.3 Poisoning guard tests
Required cases:
- contested invention does not enter strict baseline
- rejected analogy is persisted but not injected as positive context
- weak bridge remains soft only
- unsupported bridge triggers `UNGROUNDED_BRIDGE`

## 16.4 Benchmark tests
Need an internal benchmark set where:
- removing transliminality reduces meaningful cross-domain synthesis
- adding transliminality increases integration score without collapsing verifiability

## 16.5 Counterfactual tests
At least a small benchmark should explicitly compare:
- baseline Hephaestus
- Hephaestus + pressure only
- Hephaestus + pressure + transliminality

---

## 17. Risks and mitigations

## Risk 1 — ornamental analogy
Mitigation:
- integration scoring
- Pantheon objections
- counterfactual dependence test
- negative capability in analyzer

## Risk 2 — self-poisoning loop
Mitigation:
- strict vs soft channels
- promotion gates
- no automatic promotion of generated artifacts

## Risk 3 — cost explosion
Mitigation:
- remote vault routing cap
- retrieval prefilter
- analyzed candidate cap
- cached role signatures and retrieval artifacts

## Risk 4 — overfitting to lexical overlap
Mitigation:
- role signatures
- diversified retrieval
- structural analogy analysis

## Risk 5 — literal transplant from remote domain
Mitigation:
- explicit “transform, do not transplant” instruction
- `LITERAL_TRANSPLANT` Pantheon objection
- strict constraint carryover check

---

## 18. Implementation plan

## Phase 1 — Subsystem skeleton
Build:
- package layout
- `TransliminalityConfig`
- `TransliminalityRequest`
- domain models
- factory wiring
- stub engine

## Phase 2 — Problem and retrieval path
Build:
- `ProblemRoleSignatureBuilder`
- `VaultRouter`
- `BridgeRetriever`
- bridge candidate persistence / tracing
- initial pack assembly skeleton

## Phase 3 — Analogy validation and injection
Build:
- analyzer integration
- `PackAssembler`
- injection into lens selection and Genesis
- strict/soft channel policy

## Phase 4 — Scoring and Pantheon
Build:
- `IntegrationScorer`
- Pantheon objection taxonomy additions
- pack → dossier injection
- counterfactual and non-ornamental checks

## Phase 5 — Writeback and benchmarks
Build:
- artifact persistence
- run manifest
- poisoning guard tests
- benchmark harness
- score impact tracking

---

## 19. Definition of done

The feature is done only when:

- a problem and one or more vaults can produce a revision-pinned `TransliminalityPack`
- the pack injects through existing invention-time interfaces
- Pantheon can explicitly object to invalid or ornamental bridges
- valid and invalid maps are written back into ForgeBase
- strict channels remain policy-clean
- integration score exists and influences ranking
- benchmark runs show improved cross-domain synthesis quality relative to pressure-only mode

---

## 20. Immediate developer handoff

The first implementation target should be:

1. create `src/hephaestus/transliminality/`
2. add domain models and enums
3. build `ProblemRoleSignatureBuilder`
4. add `BridgeRetriever` using existing fusion stack
5. create `PackAssembler` with strict vs soft channels
6. wire pack injection into:
   - `LensSelector.select_plan(reference_context=...)`
   - `PantheonCoordinator.prepare_pipeline(baseline_dossier=...)`
7. leave writeback and scoring behind feature flags until core pack flow is proven

### First code changes expected outside the new package
- `src/hephaestus/core/genesis.py`
- `src/hephaestus/deepforge/pressure.py` or harness/config surface
- `src/hephaestus/pantheon/coordinator.py`
- `src/hephaestus/forgebase/` integration bridge and artifact registration
- tests under:
  - `tests/test_transliminality/`
  - selected Genesis/Pantheon/ForgeBase integration suites

---

## 21. Final summary

The Transliminality Engine is the subsystem that gives Hephaestus **directional creativity**.

Layer 1 says:
> do not do the obvious.

Layer 2 says:
> use a mechanism from another domain, but only if the structural mapping is real.

Layer 3 says:
> prove the bridge survives constraints and is not ornamental.

That is the feature.

It is valuable because it turns “novelty” into **guided cross-domain synthesis**, and it is viable because it reuses the parts Hephaestus already has:
- ForgeBase
- fusion
- Genesis
- DeepForge
- Pantheon

The subsystem’s success criterion is simple:

> it must make Hephaestus produce more real cross-domain inventions, not just more unusual language.
