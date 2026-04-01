# Workspace Inventions for hephaestus

**Problems found:** 7
**Inventions attempted:** 3
**Inventions succeeded:** 3

## 1. Staged Channel Multiplexer with Commitment Routing

**Problem:** The 5-stage Genesis pipeline executes sequentially with no parallelism across domain candidates, making the ~45s latency dominated by serial LLM calls that could be overlapped
**Source Domain:** Bacterial Biofilm Formation — Water Channel Network Architecture and Parallel Nutrient Distribution
**Novelty Score:** 0.14 | **Verdict:** QUESTIONABLE

### Abstract Mechanism (domain-neutral)
A system where a single interface to an expensive external resource is transformed into multiple independent internal pathways through the construction of persistent routing infrastructure. The key mechanism has three parts: (1) CHANNEL MATERIALIZATION: Early-stage outputs are not merely data but include routing metadata that pre-allocates dedicated pathways to the external resource, converting a single shared bottleneck into N independent conduits. (2) COMMITMENT CASCADE: Each pathway, once allocated, becomes increasingly 'sticky' - partial results from the external resource are cached in the pathway itself, so that retries or continuations reuse accumulated state rather than starting fresh. The cost of abandoning a pathway increases with investment. (3) GRADIENT-DRIVEN PRIORITY: Pathways closer to completion (higher accumulated state) receive preferential access to the shared resource during contention, creating a natural flow toward finishing nearly-complete work before starting new work. The mathematical structure is: given a DAG with stages S1→S2→...→Sk where stage Si produces ni independent items, construct a routing layer R between Si and Si+1 such that R maintains ni persistent channels, each channel accumulates partial results, and channel priority is proportional to accumulated state. This differs from simple parallelism because the channels themselves carry state that influences future routing decisions.

### Key Insight
Converting passive work items into stateful channels that accumulate partial results and develop priority based on investment creates a self-organizing flow toward completion. The channels are not just parallel execution paths but persistent infrastructure that carries state across multiple resource acquisitions, making nearly-complete work preferentially finish before new work starts.

### Architecture
The architecture introduces a ChannelMatrix data structure that sits between the Search stage output and the Translate stage, and persists through Verify. Rather than treating candidates as passive data to be processed, each candidate becomes a Channel object with its own dedicated connection context, accumulated partial state, and commitment level.

DATA STRUCTURES:
```python
class Channel:
    id: int  # 0 to N-1
    candidate: DomainCandidate
    connection_ctx: ConnectionContext  # Dedicated HTTP session with keep-alive
    partial_state: Dict[str, Any]  # Accumulated LLM responses, embeddings, etc.
    commitment_level: float  # 0.0 (fresh) to 1.0 (nearly complete)
    bytes_invested: int  # Total tokens sent/received on this channel
    
class ChannelMatrix:
    channels: List[Channel]  # Fixed size N=8
    oracle_semaphore: asyncio.Semaphore  # Limits concurrent oracle calls to M
    priority_queue: heapq  # Max-heap by commitment_level
    
    def materialize(self, candidates: List[DomainCandidate]) -> None:
        """Called once after Search stage. Creates persistent channels."""
        for i, cand in enumerate(candidates):
            self.channels[i] = Channel(
                id=i,
                candidate=cand,
                connection_ctx=ConnectionContext.create_persistent(),
                partial_state={},
                commitment_level=0.0,
                bytes_invested=0
            )
    
    async def acquire_oracle(self, channel_id: int) -> OracleHandle:
        """Priority-aware oracle acquisition."""
        channel = self.channels[channel_id]
        # Higher commitment = higher priority in semaphore queue
        priority = channel.commitment_level
        await self.oracle_semaphore.acquire(priority=priority)
        return OracleHandle(channel.connection_ctx, release_fn=self.oracle_semaphore.release)
```

TRANSLATE STAGE REFACTOR:
```python
async def translate_stage(matrix: ChannelMatrix, config: TranslateConfig) -> List[Translation]:
    """
    Fan-out all channels concurrently. Each channel uses its dedicated
    connection context and accumulates partial state.
    """
    async def translate_one(channel: Channel) -> Translation:
        # Phase 1: Structural extraction (commitment += 0.3)
        async with await matrix.acquire_oracle(channel.id) as oracle:
            extraction = await oracle.call(
                prompt=build_extraction_prompt(channel.candidate),
                session=channel.connection_ctx  # Reuses TCP connection
            )
            channel.partial_state['extraction'] = extraction
            channel.commitment_level = 0.3
            channel.bytes_invested += len(extraction)
        
        # Phase 2: Mapping generation (commitment += 0.4)
        async with await matrix.acquire_oracle(channel.id) as oracle:
            mapping = await oracle.call(
                prompt=build_mapping_prompt(
                    channel.candidate,
                    channel.partial_state['extraction']  # Uses accumulated state
                ),
                session=channel.connection_ctx
            )
            channel.partial_state['mapping'] = mapping
            channel.commitment_level = 0.7
            channel.bytes_invested += len(mapping)
        
        # Phase 3: Architecture synthesis (commitment += 0.3)
        async with await matrix.acquire_oracle(channel.id) as oracle:
            architecture = await oracle.call(
                prompt=build_architecture_prompt(
                    channel.candidate,
                    channel.partial_state['extraction'],
                    channel.partial_state['mapping']
                ),
                session=channel.connection_ctx
            )
            channel.commitment_level = 1.0
            return Translation(channel.candidate, extraction, mapping, architecture)
    
    # Fan-out: all channels run concurrently, semaphore limits active oracle calls
    return await asyncio.gather(*[translate_one(ch) for ch in matrix.channels])
```

VERIFY STAGE WITH GRADIENT PRIORITY:
```python
async def verify_stage(matrix: ChannelMatrix, translations: List[Translation]) -> List[VerifiedResult]:
    """
    Attack/defense rounds run in parallel across channels.
    Channels with higher commitment (more invested) get priority.
    """
    async def verify_one(channel: Channel, translation: Translation) -> VerifiedResult:
        attacks = []
        defenses = []
        
        for round_idx in range(config.num_rounds):  # Default: 3 rounds
            # Attack phase
            async with await matrix.acquire_oracle(channel.id) as oracle:
                attack = await oracle.call(
                    prompt=build_attack_prompt(translation, defenses),
                    session=channel.connection_ctx
                )
                attacks.append(attack)
                channel.partial_state[f'attack_{round_idx}'] = attack
                # Commitment increases with each round
                channel.commitment_level = min(1.0, 0.7 + 0.1 * (round_idx + 1))
            
            # Defense phase
            async with await matrix.acquire_oracle(channel.id) as oracle:
                defense = await oracle.call(
                    prompt=build_defense_prompt(translation, attacks),
                    session=channel.connection_ctx
                )
                defenses.append(defense)
                channel.partial_state[f'defense_{round_idx}'] = defense
        
        return VerifiedResult(translation, attacks, defenses)
    
    return await asyncio.gather(*[
        verify_one(matrix.channels[i], translations[i])
        for i in range(len(translations))
    ])
```

PRIORITY SEMAPHORE IMPLEMENTATION:
```python
class PrioritySemaphore:
    """Semaphore that releases waiters in priority order (highest first)."""
    def __init__(self, max_concurrent: int = 4):
        self.max_concurrent = max_concurrent
        self.current = 0
        self.waiters: List[Tuple[float, asyncio.Future]] = []  # Min-heap (negated priority)
        self.lock = asyncio.Lock()
    
    async def acquire(self, priority: float = 0.0):
        async with self.lock:
            if self.current < self.max_concurrent:
                self.current += 1
                return
            future = asyncio.Future()
            heapq.heappush(self.waiters, (-priority, future))  # Negate for max-heap behavior
        await future
    
    def release(self):
        asyncio.create_task(self._release_impl())
    
    async def _release_impl(self):
        async with self.lock:
            if self.waiters:
                _, future = heapq.heappop(self.waiters)
                future.set_result(None)
            else:
                self.current -= 1
```

COMPLEXITY ANALYSIS:
- Time: O(N * T / M) where N=candidates, T=oracle latency, M=max concurrent calls
- With N=8, M=4, T=5s per call, 3 calls per translate, 6 calls per verify:
  - Sequential: 8 * (3 + 6) * 5s = 360s
  - This architecture: ceil(8/4) * (3 + 6) * 5s = 90s (4x improvement)
  - Actual improvement depends on oracle rate limits
- Space: O(N * S) where S = size of partial_state per channel (~10KB typical)

NUMERICAL EXAMPLE:
- 8 candidates, 4 max concurrent oracle calls, 5s per oracle call
- Translate stage: 3 oracle calls per candidate = 24 total calls
  - Wave 1: Channels 0-3 start extraction (t=0s)
  - Wave 1 completes (t=5s), Channels 4-7 start extraction, Channels 0-3 start mapping
  - At t=10s: Channels 0-3 at commitment 0.7, Channels 4-7 at commitment 0.3
  - Channels 0-3 get priority for architecture call
  - Total translate time: ~20s (vs 120s sequential)
- Verify stage: 6 oracle calls per candidate = 48 total calls
  - Similar wave pattern, total ~35s (vs 240s sequential)
- End-to-end: ~55s (vs ~360s sequential) = 6.5x improvement

### vs Conventional Baseline
BASELINE: asyncio.gather() with N concurrent LLM calls, no state between calls, round-robin resource acquisition.

THIS INVENTION: (1) Persistent connections save ~100ms per call in TCP setup (8 candidates * 9 calls = 72 calls, saving ~7s total). (2) Priority semaphore ensures that when rate limits force queuing, nearly-complete candidates finish first, reducing time-to-first-result by up to 40%. (3) Partial state accumulation means a failed call at phase 3 retries only phase 3, not phases 1-2 (saving ~10s per retry). (4) The commitment cascade creates predictable completion order, enabling downstream stages to start processing early results while waiting for stragglers.

---

## 2. Spectral Decomposition Priority Router

**Problem:** Domain lens selection is static at query time — all 80+ lenses are searched with equal weight regardless of problem structure, producing no learning signal from which domains historically yield high-fidelity translations for which problem shapes
**Source Domain:** Music — Acoustic Instrument Design and Formant Matching
**Novelty Score:** 0.25 | **Verdict:** QUESTIONABLE

### Abstract Mechanism (domain-neutral)
A system decomposes incoming signals into a basis of orthogonal components (a 'spectrum'). Each transformation template is characterized not by a single compatibility score, but by a response function across this spectral basis—a vector of amplification factors at each basis component. When a new signal arrives, its spectral decomposition is computed, and templates are ranked by the inner product of the signal's spectrum with each template's response function. This inner product predicts energy transfer efficiency: templates whose response peaks align with the signal's spectral peaks will amplify; those with peaks at the signal's spectral nulls will waste energy. The key structural insight is that both signals and templates live in the same spectral space, and their compatibility is the overlap integral of their spectral representations. Historical observations update the estimated response function of each template via Bayesian inference on the spectral coefficients, not on a scalar 'success rate'. Cold-start for new templates uses spectral interpolation from templates with similar response functions. The mechanism fundamentally differs from scalar bandits because it exploits the internal structure of both queries and templates, not just their pairwise outcomes.

### Key Insight
Compatibility between a query and a transformation template is not a scalar property of the pair, but the overlap integral of their representations in a shared structural feature space. Learning this representation for templates (not just their scalar success rates) enables generalization: a template that works well on high-feedback-loop problems will be predicted to work well on NEW high-feedback-loop problems, even if that specific pairing was never observed.

### Architecture
**Data Structures:**

1. **Problem Spectral Basis (K dimensions):** Define K=12 orthogonal structural features extracted from each problem. These are not semantic embeddings but structural invariants: (1) graph_density: ratio of explicit relational constraints to entities, (2) temporal_depth: number of sequential dependencies, (3) hierarchy_levels: depth of containment/subsumption relations, (4) symmetry_index: presence of commutative/associative structures, (5) cardinality_class: log2 of entity count, (6) feedback_loops: count of cyclic dependencies, (7) constraint_tightness: ratio of constraints to degrees of freedom, (8) abstraction_level: ratio of abstract to concrete nouns in problem statement, (9) quantitative_density: count of numeric values per sentence, (10) causal_depth: longest causal chain, (11) uncertainty_markers: count of hedging language, (12) domain_specificity: inverse of vocabulary overlap with general corpus.

2. **Lens Response Function (per lens, K-dimensional vector + K×K covariance matrix):** For each lens L, maintain a Gaussian posterior over its 'response spectrum' R_L ∈ ℝ^K. R_L[i] represents how much lens L amplifies problems with high loading on spectral component i. Initialize R_L = 0, Σ_L = I (unit prior).

3. **Historical Observation Store:** A table of (problem_id, spectral_vector[K], lens_id, fidelity_score) tuples.

**Algorithm: Spectral Priority Routing**

```python
def compute_problem_spectrum(problem_text: str) -> np.ndarray:
    # Returns K-dimensional spectral vector s ∈ [0,1]^K
    s = np.zeros(12)
    s[0] = count_relations(problem_text) / max(1, count_entities(problem_text))
    s[1] = extract_temporal_depth(problem_text)  # returns 0-1 normalized
    s[2] = extract_hierarchy_depth(problem_text) / 5.0  # cap at 5 levels
    s[3] = detect_symmetry_structures(problem_text)  # binary or graded
    s[4] = np.log2(max(1, count_entities(problem_text))) / 10.0
    s[5] = count_cycles_in_dependency_graph(problem_text) / 5.0
    s[6] = count_constraints(problem_text) / max(1, count_free_variables(problem_text))
    s[7] = count_abstract_nouns(problem_text) / max(1, count_concrete_nouns(problem_text))
    s[8] = count_numbers(problem_text) / max(1, count_sentences(problem_text))
    s[9] = longest_causal_chain(problem_text) / 5.0
    s[10] = count_hedging_words(problem_text) / max(1, count_sentences(problem_text))
    s[11] = 1.0 - vocabulary_overlap_with_common_corpus(problem_text)
    return np.clip(s, 0, 1)

def compute_expected_fidelity(problem_spectrum: np.ndarray, lens_id: int) -> tuple[float, float]:
    # Returns (expected_fidelity, uncertainty) using Bayesian posterior
    R_L = lens_response_means[lens_id]  # K-vector
    Sigma_L = lens_response_covariances[lens_id]  # K×K matrix
    
    # Expected fidelity is inner product of spectra
    expected = np.dot(problem_spectrum, R_L)
    
    # Uncertainty is sqrt(s^T Σ s) — how uncertain we are about this specific pairing
    uncertainty = np.sqrt(problem_spectrum @ Sigma_L @ problem_spectrum)
    
    return expected, uncertainty

def select_lenses(problem_text: str, budget: int = 5, exploration_weight: float = 1.5) -> list[int]:
    s = compute_problem_spectrum(problem_text)
    
    scores = []
    for lens_id in range(NUM_LENSES):
        exp_fid, unc = compute_expected_fidelity(s, lens_id)
        # Upper confidence bound with spectral uncertainty
        ucb_score = exp_fid + exploration_weight * unc
        scores.append((ucb_score, lens_id))
    
    scores.sort(reverse=True)
    return [lens_id for _, lens_id in scores[:budget]]

def update_lens_response(lens_id: int, problem_spectrum: np.ndarray, observed_fidelity: float):
    # Bayesian update: treat fidelity = s^T R + noise, noise ~ N(0, σ²)
    # This is a linear Gaussian observation model
    sigma_noise = 0.15  # observation noise std
    
    R_L = lens_response_means[lens_id]
    Sigma_L = lens_response_covariances[lens_id]
    
    # Kalman-style update
    s = problem_spectrum
    k = Sigma_L @ s / (s @ Sigma_L @ s + sigma_noise**2)  # Kalman gain
    innovation = observed_fidelity - np.dot(s, R_L)
    
    lens_response_means[lens_id] = R_L + k * innovation
    lens_response_covariances[lens_id] = Sigma_L - np.outer(k, s @ Sigma_L)
```

**Complexity Bounds:**
- Spectrum computation: O(|problem_text|) for parsing + O(K) for feature extraction
- Lens selection: O(N × K²) where N=80 lenses, K=12 features — approximately O(11,520) operations per query
- Posterior update: O(K²) per observation
- Space: O(N × K²) for covariance matrices ≈ 80 × 144 × 8 bytes ≈ 92KB

**Concrete Numerical Example:**

Problem: 'Design a rate limiter for an API that handles bursty traffic with fairness constraints across tenants.'

Spectral decomposition:
- s[0] graph_density = 0.4 (moderate relational structure)
- s[1] temporal_depth = 0.7 (strong sequential/rate aspect)
- s[2] hierarchy_levels = 0.3 (tenant → request hierarchy)
- s[3] symmetry_index = 0.6 (fairness implies symmetry)
- s[4] cardinality_class = 0.5 (moderate entity count)
- s[5] feedback_loops = 0.8 (rate limiting is inherently feedback)
- s[6] constraint_tightness = 0.7 (fairness + rate = tight constraints)
- s[7] abstraction_level = 0.4 (concrete engineering problem)
- s[8] quantitative_density = 0.3 (rates are numeric)
- s[9] causal_depth = 0.5 (moderate causal chains)
- s[10] uncertainty_markers = 0.2 (fairly concrete)
- s[11] domain_specificity = 0.6 (API-specific vocabulary)

Lens 'fluid_dynamics' has learned response function R = [0.3, 0.8, 0.2, 0.4, 0.3, 0.9, 0.7, 0.3, 0.5, 0.4, 0.2, 0.4]

Expected fidelity = s · R = 0.4×0.3 + 0.7×0.8 + ... = 0.62

Lens 'economics_game_theory' has R = [0.5, 0.3, 0.4, 0.8, 0.6, 0.3, 0.6, 0.5, 0.4, 0.5, 0.3, 0.3]

Expected fidelity = s · R = 0.52

Fluid dynamics lens is prioritized due to higher spectral overlap on temporal_depth and feedback_loops.

**Failure Mode and Recovery:**

Failure: Spectral decomposition misidentifies problem structure (e.g., parses 'rate' as financial rate not temporal rate). The wrong spectral signature leads to poor lens selection.

Recovery: After observing low fidelity, the Bayesian update *correctly* attributes the error. If problem spectrum s led to low fidelity with lens L, the update R_L ← R_L + k×(low - s·R_L) will *reduce* R_L in the direction of s. Over time, the system learns that this spectral signature doesn't actually match this lens, even if the initial decomposition was wrong. The covariance update also increases uncertainty in that spectral region, triggering more exploration. Additionally, maintain a 'spectral anomaly detector': if a problem's spectrum is >2σ from the centroid of historical problems, flag for manual review and increase exploration_weight to 3.0.

### vs Conventional Baseline
**Simplest conventional solution:** Multi-armed bandit (UCB1) tracking mean fidelity per lens. Selects lens with highest (mean + c×sqrt(log(t)/n_lens)) score.

**Structural advantage of spectral routing:**
1. **Generalization:** UCB1 requires trying each lens on each problem type to learn. Spectral routing learns that 'fluid_dynamics lens works on high-feedback problems' and applies this to ALL high-feedback problems, even novel ones.
2. **Sample efficiency:** With 80 lenses and ~10 problem types, UCB1 needs O(800) observations to have reasonable estimates for all pairs. Spectral routing needs O(80×K)=O(960) observations to learn all response functions, but these observations generalize across problem types.
3. **Cold-start for new problem types:** UCB1 has no information. Spectral routing predicts based on the new problem's structural features.
4. **Interpretability:** UCB1 says 'lens 37 is good.' Spectral routing says 'lens 37 amplifies temporal_depth and feedback_loops, which this problem has.'

---

## 3. Activation-Competitive Novelty Suppression

**Problem:** The anti-memory and convergence-pruning subsystems operate on per-session state only, with no cross-session memory of which structural translations have already been produced, allowing the engine to re-invent the same cross-domain mapping across different user sessions
**Source Domain:** Linguistic Semantics — Lexical Coinage and Neologism Blocking via Morphological Productivity
**Novelty Score:** 0.22 | **Verdict:** QUESTIONABLE

### Abstract Mechanism (domain-neutral)
In a distributed system of independent generative partitions, each partition maintains a local activation map over an abstract semantic space. When a partition attempts to generate an output for an input, it first projects the input into semantic coordinates and performs spreading activation in a local neighborhood. The activation query is broadcast to a shared activation accumulator that aggregates activation signals from all partitions without storing the outputs themselves. If the accumulated activation in the semantic neighborhood exceeds a threshold (indicating that other partitions have previously generated in this region), the novelty score is penalized proportionally to the activation strength. Crucially, the shared layer stores only activation weights keyed by semantic coordinates — not the actual outputs — making it a coordination signal rather than a memoization table. Activation weights decay over time (recency) and are incremented by generation events (frequency). This creates emergent blocking: high-traffic semantic regions develop strong activation that suppresses redundant generation, while low-traffic regions remain open for novel production. The equivalence class is defined by semantic proximity in the projected space, not by exact input identity.

### Key Insight
Novelty verification can be achieved through competitive activation in a shared coordinate space rather than exact-match lookup in a stored registry — the system does not need to remember what was generated, only where generation activity has occurred, with activity strength encoding both frequency and recency.

### Architecture
The architecture introduces an Activation Accumulator Service (AAS) that maintains a sparse activation map over a semantic coordinate space, plus modifications to each session's novelty-checking logic to query and update this shared activation layer.

**Semantic Projection Function:**
Each structural-form input is projected into a 64-dimensional semantic coordinate using a locality-sensitive hash (LSH) that preserves structural similarity. The projection function `project(structural_form) -> float[64]` operates on the abstract structural form (the normalized representation already computed by the engine), not the raw input. Two structurally similar inputs (e.g., both are load-balancing problems with N workers and M tasks) will project to nearby coordinates.

```python
def project(structural_form: StructuralForm) -> np.ndarray:
    # Extract canonical features: arity of relations, graph topology signature,
    # constraint types, symmetry groups
    features = extract_canonical_features(structural_form)
    # LSH projection preserving cosine similarity
    return lsh_project(features, dim=64, num_hyperplanes=128)
```

**Activation Accumulator Service (AAS):**
The AAS maintains a sparse map from quantized semantic coordinates to activation weights. Coordinates are quantized to a grid with cell size `delta = 0.1` in each dimension, yielding approximately `10^64` possible cells (but only occupied cells are stored).

```python
class ActivationAccumulator:
    def __init__(self, decay_rate=0.995, activation_radius=3):
        self.activations: Dict[Tuple[int,...], ActivationEntry] = {}
        self.decay_rate = decay_rate  # per-hour decay
        self.radius = activation_radius  # neighborhood radius in grid cells
    
    def quantize(self, coord: np.ndarray) -> Tuple[int,...]:
        return tuple((coord / 0.1).astype(int))
    
    def query_neighborhood(self, coord: np.ndarray) -> float:
        center = self.quantize(coord)
        total_activation = 0.0
        # Query all cells within L-infinity radius
        for offset in itertools.product(range(-self.radius, self.radius+1), repeat=64):
            neighbor = tuple(c + o for c, o in zip(center, offset))
            if neighbor in self.activations:
                entry = self.activations[neighbor]
                distance = max(abs(o) for o in offset)  # L-infinity distance
                weight = 1.0 / (1.0 + distance)  # distance decay
                age_hours = (now() - entry.last_update).total_seconds() / 3600
                decayed = entry.strength * (self.decay_rate ** age_hours)
                total_activation += decayed * weight
        return total_activation
    
    def record_generation(self, coord: np.ndarray, strength: float = 1.0):
        cell = self.quantize(coord)
        if cell in self.activations:
            self.activations[cell].strength += strength
            self.activations[cell].last_update = now()
        else:
            self.activations[cell] = ActivationEntry(strength=strength, last_update=now())
```

**Modified Novelty Scoring in Session:**
The session's novelty checker queries the AAS before computing local novelty, and updates the AAS after successful generation.

```python
def compute_novelty_score(structural_form: StructuralForm, 
                          local_anti_memory: AntiMemory,
                          aas: ActivationAccumulator) -> float:
    # Local novelty (existing logic)
    local_score = local_anti_memory.novelty_score(structural_form)
    
    # Global activation query
    coord = project(structural_form)
    global_activation = aas.query_neighborhood(coord)
    
    # Blocking penalty: sigmoid suppression based on activation
    # At activation=0, penalty=0. At activation=10, penalty≈0.9.
    blocking_penalty = 1.0 - (1.0 / (1.0 + math.exp(-0.5 * (global_activation - 5))))
    
    # Combined score: local novelty multiplied by (1 - blocking_penalty)
    combined_score = local_score * (1.0 - blocking_penalty)
    
    return combined_score

def on_successful_generation(structural_form: StructuralForm,
                             mapping: CrossDomainMapping,
                             aas: ActivationAccumulator):
    coord = project(structural_form)
    # Strength proportional to mapping quality (better mappings block more strongly)
    strength = mapping.fidelity_score
    aas.record_generation(coord, strength)
```

**Numerical Example:**
Session A receives a load-balancing problem. `project()` yields coordinates `[0.23, -0.15, 0.87, ...]`. AAS query returns activation=0.0 (no prior generations nearby). Local novelty=0.92. Combined score=0.92. Generation proceeds; AAS records activation=0.78 (the fidelity score) at quantized cell `(2, -2, 9, ...)`.

Session B receives a structurally similar load-balancing problem an hour later. `project()` yields `[0.25, -0.14, 0.88, ...]` — same quantized cell. AAS query returns activation=0.78 * 0.995^1 = 0.776. Blocking penalty = 1 - 1/(1+exp(-0.5*(0.776-5))) = 1 - 0.89 = 0.11. Local novelty=0.91. Combined score=0.91 * 0.89 = 0.81. Generation proceeds but with reduced novelty claim.

Session C receives the same problem a week later. AAS query returns activation=0.78 * 0.995^168 = 0.34. Blocking penalty=0.05. The activation has decayed enough that the region is partially reopened.

**Complexity Bounds:**
- Projection: O(F) where F is number of canonical features (~100)
- Neighborhood query: O(R^D) where R=radius=3, D=64 — but this is prohibitive! 
- **Optimization:** Use approximate nearest neighbor (ANN) index over occupied cells only. With ~1M occupied cells, query is O(log N) using ball trees.
- Space: O(N * 64) for N occupied cells, plus ANN index overhead.

**Failure Mode and Recovery:**
Failure: LSH collision causes unrelated structural forms to map to same neighborhood, causing false blocking. Detection: Monitor ratio of blocked generations to total generations. If >30% of novel-seeming inputs are blocked, the projection function is too coarse. Recovery: Increase LSH dimensionality or decrease quantization cell size. Fallback: If AAS is unavailable, sessions operate in local-only mode with degraded novelty guarantees (explicitly flagged in output).

### vs Conventional Baseline
Baseline: PostgreSQL table with structural-form hash → mapping. Query is exact-match lookup. Hit returns prior mapping or flags duplicate. Miss proceeds with generation.

This invention: Activation map over semantic coordinates. Query returns graded activation level. High activation penalizes novelty score but does not prevent generation. Generation increments activation with decay.

Structural advantage: (1) Catches near-duplicates that differ in surface form but share structural essence — the baseline misses these entirely. (2) Allows temporal re-exploration as activation decays — the baseline permanently blocks. (3) Provides graded novelty scores rather than binary duplicate detection — the baseline is all-or-nothing. (4) Stores only scalar activation weights, not full mappings — the baseline requires storing all prior outputs. (5) Blocking strength reflects community consensus (frequent generation = strong blocking) — the baseline treats all prior generations equally.

---
