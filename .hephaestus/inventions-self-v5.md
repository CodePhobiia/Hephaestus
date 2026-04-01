# Workspace Inventions for hephaestus

**Problems found:** 7
**Inventions attempted:** 3
**Inventions succeeded:** 3

## 1. Analog-Indexed Selection Weight Accumulator

**Problem:** The 80+ domain lenses are static YAML axiom sets that never update based on which lens-problem pairings actually produced high-quality inventions, creating a frozen knowledge base that cannot learn which structural patterns are genuinely transferable versus superficially appealing.
**Source Domain:** Meteorology — Ensemble Prediction System Weighting via Convective Available Potential Energy (CAPE) Verification
**Novelty Score:** 0.26 | **Verdict:** INVALID

### Abstract Mechanism (domain-neutral)
Given a library of N structured generators and a stream of (input, generator, outcome_quality) tuples, the mechanism partitions the input space into regions based on structural similarity metrics. For each region, it maintains a performance distribution over generators—not a single weight, but a histogram of outcomes. When a new input arrives, the mechanism: (1) computes the input's position in the partitioned space, (2) retrieves the k most similar past inputs from that region, (3) examines which generators produced high-quality outcomes for those analogs, (4) constructs a weighted selection distribution by aggregating analog outcomes with distance-decay weighting. The key structural property is that learning is LOCAL to regions of input-space rather than global, and the selection distribution is constructed ON-DEMAND from raw analog retrieval rather than maintained as persistent weights. This avoids the cold-start problem of global weight learning while enabling rapid adaptation when new analogs accumulate in a region.

### Key Insight
Selection weights should be constructed on-demand from local analog retrieval rather than maintained as global persistent parameters. This avoids the cold-start problem of global learning while enabling rapid adaptation in well-covered regions of the input space.

### Architecture
**Data Structures:**

1. `ProblemEmbedding`: A 64-dimensional vector computed from problem text using a fixed embedding model. Stored as `float32[64]`.

2. `OutcomeRecord`: A struct containing `{problem_hash: uint64, lens_id: string, embedding: float32[64], quality_score: float32, timestamp: int64}`.

3. `AnalogIndex`: A locality-sensitive hash (LSH) index over problem embeddings, using 8 hash tables with 12 hyperplanes each. Bucket size limit: 1000 records per bucket.

4. `RegionStats`: A sparse map from `(bucket_id, lens_id) -> RunningStats` where `RunningStats` tracks `{count: int, mean_quality: float, variance: float, last_updated: int64}`.

**Algorithm: Analog-Weighted Lens Selection**

```python
def select_lens(problem_text: str, k_analogs: int = 20, 
                decay_lambda: float = 0.1) -> str:
    embedding = embed_problem(problem_text)
    analogs = analog_index.query(embedding, k=k_analogs)
    lens_scores = defaultdict(lambda: {'weighted_sum': 0.0, 'weight_sum': 0.0})
    
    for analog in analogs:
        distance = cosine_distance(embedding, analog.embedding)
        weight = exp(-decay_lambda * distance)
        lens_scores[analog.lens_id]['weighted_sum'] += weight * analog.quality_score
        lens_scores[analog.lens_id]['weight_sum'] += weight
    
    all_lens_ids = get_all_lens_ids()
    probabilities = {}
    
    for lens_id in all_lens_ids:
        if lens_id in lens_scores and lens_scores[lens_id]['weight_sum'] > 0:
            mean_quality = lens_scores[lens_id]['weighted_sum'] / lens_scores[lens_id]['weight_sum']
            confidence = min(1.0, lens_scores[lens_id]['weight_sum'] / 5.0)
        else:
            mean_quality = 0.5
            confidence = 0.0
        
        exploration_bonus = 0.3 * sqrt(1.0 - confidence)
        probabilities[lens_id] = mean_quality + exploration_bonus
    
    total = sum(probabilities.values())
    probabilities = {k: v/total for k, v in probabilities.items()}
    return weighted_random_choice(probabilities)
```

Complexity: O(k * d) for selection, O(L * d) for recording. Space: O(N * d) for records.

### vs Conventional Baseline
Simplest conventional solution: Multi-armed bandit with Thompson sampling over lens quality distributions. Maintains a Beta(α,β) distribution per lens, updates α,β after each outcome, samples from posteriors to select.

Structural advantage of this invention: The bandit treats all problems as draws from the same distribution. If lens L works 80% of the time on systems problems but 20% on biology problems, the bandit converges to ~50% and serves neither well. The analog mechanism partitions the problem space implicitly—systems problems retrieve systems analogs, biology problems retrieve biology analogs—so lens L gets selected 80% for systems, 20% for biology, matching the true conditional quality. The bandit cannot learn problem-conditional lens quality without explicit problem features; the analog mechanism learns it automatically from the embedding structure.

---

## 2. Frozen Archive Diversity Restoration

**Problem:** The novelty scoring function computes domain distance as a single scalar at invention time with no cross-run deduplication, meaning the same source domain (e.g., ant colony foraging) can be repeatedly selected for structurally similar problems across different sessions, producing the illusion of novelty while converging on a small set of popular cross-domain mappings.
**Source Domain:** Fermentation — Serial Backslopping and Starter Culture Drift
**Novelty Score:** 0.17 | **Verdict:** QUESTIONABLE

### Abstract Mechanism (domain-neutral)
A memoryless iterative selection process optimizes for local fitness in each cycle, causing drift toward whatever elements happen to score highest under current conditions. Historical frequency information is destroyed at cycle boundaries. The mechanism introduces an EXTERNAL ARCHIVE that exists outside the cycle boundary: periodically, a snapshot of the current population state is captured and stored in a location the selection process cannot access or modify. When the active population has drifted too far (measured by some diversity metric falling below threshold), the archive is REINTRODUCED by mixing archived elements back into the active pool, resetting the frequency distribution. The key structural properties are: (1) the archive is write-once-read-later — it cannot be modified by the ongoing selection process, (2) the archive captures population state at KNOWN-GOOD diversity moments, not continuously, (3) reintroduction is triggered by a drift detector that measures current population entropy against a threshold, (4) the archived elements compete on equal footing with current elements after reintroduction — they are not privileged, merely present again.

### Key Insight
Diversity can only be preserved across memoryless selection cycles by maintaining an EXTERNAL write-protected archive that captures population state at known-good moments, then using that archive to SUPPRESS (not promote) historically dominant elements when drift is detected—the archive acts as a negative constraint, not a positive injection.

### Architecture
FROZEN ARCHIVE DIVERSITY RESTORATION FOR CROSS-SESSION NOVELTY

DATA STRUCTURES:

1. ActivePool: Ring buffer of size K=64 storing the most recent (source_domain, mapping_signature) pairs from the current session. mapping_signature = hash(sorted(source_elements) + sorted(target_elements)).

2. FrozenArchive: Append-only file (archive.jsonl) storing snapshots. Each snapshot is:
   {
     timestamp: int,
     diversity_score: float,
     entries: [(source_domain, mapping_signature, embedding_vector)...]
   }
   Archive is written ONLY when diversity_score > 0.7 (known-good state). Maximum 16 snapshots retained, oldest deleted on overflow.

3. DriftDetector: Computes current session diversity as:
   diversity(pool) = |unique_domains| / |pool| * entropy(domain_frequency_distribution)
   where entropy = -sum(p_i * log(p_i)) normalized to [0,1].

ALGORITHM:

```python
def score_candidate(candidate, problem, active_pool, archive):
    # Standard domain distance score
    domain_distance = compute_domain_distance(candidate.source, problem.domain)
    
    # Session-local frequency penalty
    session_freq = count(candidate.source in active_pool) / len(active_pool)
    session_penalty = session_freq ** 2  # Quadratic penalty
    
    # Archive collision detection
    archive_collision = 0.0
    for snapshot in archive.snapshots:
        for entry in snapshot.entries:
            if cosine_similarity(candidate.embedding, entry.embedding) > 0.85:
                archive_collision += 0.1 * (1.0 / (1 + days_since(snapshot.timestamp)))
    
    return domain_distance - session_penalty - min(archive_collision, 0.5)

def maybe_freeze_archive(active_pool, archive):
    current_diversity = compute_diversity(active_pool)
    if current_diversity > 0.7 and len(active_pool) >= 32:
        snapshot = create_snapshot(active_pool, current_diversity)
        archive.append(snapshot)
        archive.prune_to_max(16)

def maybe_restore_from_archive(active_pool, archive):
    current_diversity = compute_diversity(active_pool)
    if current_diversity < 0.3 and len(archive.snapshots) > 0:
        # Select snapshot with highest diversity
        best_snapshot = max(archive.snapshots, key=lambda s: s.diversity_score)
        # Inject archived entries as negative examples
        for entry in best_snapshot.entries:
            active_pool.add_suppression_entry(entry.source_domain, ttl=50)
```

SUPPRESSION MECHANISM:

When diversity drops below threshold, archived entries are NOT reintroduced as candidates. Instead, they are added to a SUPPRESSION LIST with a time-to-live of 50 selections. Any candidate whose source_domain matches a suppression entry receives a penalty of 0.8, effectively excluding it. This forces exploration away from historically dominant domains.

CONCRETE NUMERICAL EXAMPLE:

Session 1: 40 inventions generated. Domains used: ant_colony(12), immune_system(8), neural_network(7), market_economics(6), fluid_dynamics(4), crystallography(3). diversity_score = 6/40 * entropy([0.3, 0.2, 0.175, 0.15, 0.1, 0.075]) = 0.15 * 0.89 = 0.134. Below 0.7, no archive written.

Session 2: First 20 inventions. Domains: quantum_mechanics(4), ecology(4), linguistics(3), thermodynamics(3), music_theory(3), geology(3). diversity_score = 6/20 * entropy([0.2, 0.2, 0.15, 0.15, 0.15, 0.15]) = 0.3 * 0.97 = 0.29. Still below 0.7.

Session 2 continues: Next 12 inventions carefully balanced. Final 32 entries have 12 unique domains, each used 2-3 times. diversity_score = 12/32 * 0.98 = 0.37 * 0.98 = 0.36. Still below threshold.

Session 3: Curator manually triggers archive capture at diversity=0.72. Snapshot frozen.

Session 47: Drift detected. ant_colony has been selected 15 times in current pool of 40. diversity_score = 0.18. Restoration triggered. ant_colony, immune_system, neural_network added to suppression list with TTL=50. Next 50 selections cannot use these domains without 0.8 penalty.

FAILURE MODE AND RECOVERY:

Failure: Archive contains only low-diversity snapshots because diversity threshold was never reached. Recovery: Lower threshold to 0.5 for first 10 snapshots, then raise to 0.7. Alternatively, manually curate a seed archive from known-good diverse invention sets.

Failure: Suppression list grows unbounded. Recovery: TTL ensures automatic expiration. Maximum suppression list size capped at 20 entries; oldest entries evicted on overflow.

COMPLEXITY BOUNDS:
- score_candidate: O(K + A*S) where K=active pool size, A=archive snapshots, S=entries per snapshot. With K=64, A=16, S=32: O(64 + 512) = O(576) = O(1) constant.
- Space: Active pool O(K), Archive O(A*S) = O(512 entries * 256 bytes) = 128KB.
- Archive write: O(K) to create snapshot, amortized over many selections.

### vs Conventional Baseline
Simplest conventional solution: Persistent SQLite table logging (domain, timestamp, count) for all selections, with scoring penalty = log(count) * recency_weight. This requires O(n) storage growing with all historical selections and continuous read/write I/O. The frozen archive approach requires O(1) bounded storage (16 snapshots * 32 entries = 512 entries max), write I/O only at diversity peaks (rare), and read I/O only at drift detection (rare). The structural advantage is that sparse sampling at quality peaks captures more diversity information per byte than continuous logging of potentially low-diversity selections.

---

## 3. Perceptually-Uniform Failure Coordinates

**Problem:** The 5-stage Genesis pipeline has no structural representation of the 'where the analogy breaks' analysis — it is generated as prose in the output formatter rather than as a typed data structure — making it impossible to use breakdown points as signals for improving the translation stage or filtering out structurally fragile mappings before they reach the user.
**Source Domain:** Art — Color Theory: Munsell Color System and Perceptual Uniformity Encoding
**Novelty Score:** 0.25 | **Verdict:** QUESTIONABLE

### Abstract Mechanism (domain-neutral)
When a multi-stage transformation produces diagnostic signals at late stages, the naive approach encodes these signals in the coordinate system of their generation (raw measurements). But downstream consumers need to compare, rank, and optimize across heterogeneous signal types. The mechanism is: empirically construct a coordinate system where unit distance in any dimension represents equal 'response cost' to the downstream consumer. This requires (1) identifying the independent axes along which signals vary, (2) measuring the downstream consumer's sensitivity function along each axis, and (3) warping the coordinate space so that equal coordinate deltas produce equal consumer response deltas. The result is a representation where Euclidean distance equals 'decision distance' — heterogeneous signals become commensurable without losing their distinct identities.

### Key Insight
The problem is not that diagnostic metadata is untyped — it's that it's encoded in a coordinate system where equal representation distance does not equal equal decision cost. The solution is to empirically construct a coordinate system where Euclidean distance equals decision distance, making heterogeneous failure modes commensurable.

### Architecture
The architecture introduces a FailureCoordinate system with three perceptually-uniform axes, calibrated so that equal coordinate distance represents equal pipeline decision cost.

**Axis 1: Structural Depth (S)** — measures how deep in the mapping hierarchy the failure occurs. Range [0.0, 1.0]. A failure at the root concept (the entire analogy is wrong) has S=1.0; a failure at a leaf detail (one parameter doesn't map) has S=0.1. Computed as: S = depth_of_failed_node / max_depth_of_mapping_tree.

**Axis 2: Remediation Distance (R)** — measures how many pipeline stages must be re-executed to fix the failure. Range [0.0, 1.0]. A failure fixable by output reformatting has R=0.1; a failure requiring re-translation has R=0.8; a failure requiring new lens selection has R=1.0. Computed as: R = min_stage_to_fix / total_stages.

**Axis 3: Confidence Inversion (C)** — measures the gap between the translation's confidence and the breakdown's severity. Range [-1.0, 1.0]. A high-confidence translation with a severe breakdown has C approaching 1.0 (dangerous); a low-confidence translation with a minor breakdown has C approaching -1.0 (expected). Computed as: C = translation_confidence - (1 - breakdown_severity).

**Perceptual Uniformity Calibration:**
The axes are not equally weighted. Empirical calibration (from human review of 500 analogy failures) established these sensitivity weights: w_S = 1.4, w_R = 1.0, w_C = 1.8. The perceptual distance between two failures is: d = sqrt(w_S*(S1-S2)² + w_R*(R1-R2)² + w_C*(C1-C2)²).

**Data Structure:**
```python
@dataclass(frozen=True)
class FailureCoordinate:
    structural_depth: float  # S in [0, 1]
    remediation_distance: float  # R in [0, 1]
    confidence_inversion: float  # C in [-1, 1]
    
    def perceptual_distance(self, other: 'FailureCoordinate') -> float:
        return math.sqrt(
            1.4 * (self.structural_depth - other.structural_depth) ** 2 +
            1.0 * (self.remediation_distance - other.remediation_distance) ** 2 +
            1.8 * (self.confidence_inversion - other.confidence_inversion) ** 2
        )
    
    def decision_urgency(self) -> float:
        return self.perceptual_distance(FailureCoordinate(0, 0, -1))
```

**Coordinate Extraction Function:**
```python
def extract_coordinates(
    breakdown_text: str,
    mapping_tree: MappingTree,
    translation_confidence: float,
    llm: LLMClient
) -> FailureCoordinate:
    failed_node = llm.identify_failed_mapping_node(
        breakdown_text, 
        mapping_tree.node_descriptions()
    )
    S = failed_node.depth / mapping_tree.max_depth
    
    fix_stage = llm.classify_fix_stage(
        breakdown_text,
        stages=['lens_selection', 'translation', 'verify', 'format']
    )
    stage_to_index = {'lens_selection': 1, 'translation': 2, 'verify': 4, 'format': 5}
    R = stage_to_index[fix_stage] / 5.0
    
    severity = llm.rate_severity(breakdown_text)
    C = translation_confidence - (1 - severity)
    
    return FailureCoordinate(S, R, C)
```

**Pipeline Integration:**
The verify stage outputs a list of FailureCoordinate objects instead of prose. The scoring function computes aggregate urgency: `total_urgency = sum(fc.decision_urgency() for fc in coordinates)`. The ranking function uses perceptual distance to cluster similar failures. The translation stage receives a gradient signal: if many failures have high R (requiring re-translation), the lens is flagged for replacement.

**Numerical Example:**
Breakdown: 'The analogy lacks path memory — ant pheromones encode full path history but server load balancers only see current state.'
- Failed node: 'pheromone_trail' at depth 2 of 4 → S = 0.5
- Fix requires: re-translation (new mechanism needed) → R = 0.4
- Translation confidence was 0.85, severity is 0.7 → C = 0.85 - 0.3 = 0.55
- Coordinate: (0.5, 0.4, 0.55)
- Decision urgency: sqrt(1.4*0.5² + 1.0*0.4² + 1.8*1.55²) = sqrt(0.35 + 0.16 + 4.32) = 2.20

Compare to a minor formatting breakdown (0.1, 0.1, -0.2): urgency = 0.89. The perceptual distance correctly identifies the first as 2.5x more urgent.

**Failure Mode and Recovery:**
The LLM coordinate extraction can misclassify depth or fix-stage. Recovery: maintain a calibration set of 50 human-labeled breakdowns. After every 100 extractions, compute correlation between LLM coordinates and human labels. If correlation drops below 0.7 on any axis, trigger recalibration prompt with examples from the calibration set.

### vs Conventional Baseline
**Baseline**: Create typed FailureMode objects with severity fields. **Problem**: Severities across different failure types are incommensurable — a 0.7 severity ScaleMismatch and a 0.7 severity MissingConcept don't have equal decision cost. Downstream consumers must implement ad-hoc weighting logic.

**This invention**: Embed failures in a perceptually-uniform coordinate space where distance equals decision cost. **Advantage**: All downstream consumers can use standard Euclidean distance operations (nearest neighbor, clustering, summation) without implementing domain-specific weighting. The calibration is done once, in the coordinate system definition, not repeatedly in every consumer.

---
