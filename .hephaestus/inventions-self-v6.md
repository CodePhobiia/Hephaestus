# Workspace Inventions for hephaestus

**Problems found:** 7
**Inventions attempted:** 3
**Inventions succeeded:** 3

## 1. Behavioral Signature Distillation Index

**Problem:** Lens YAML files are static axiom sets with no structural fingerprinting, forcing the Search stage to rely entirely on LLM judgment to match problem shapes to domains rather than having a computable similarity metric that could prune the 80+ lens space before expensive LLM calls
**Source Domain:** Fermentation — Sourdough Starter Microbiome Stabilization
**Novelty Score:** 0.17 | **Verdict:** QUESTIONABLE

### Abstract Mechanism (domain-neutral)
A high-dimensional complex state (the full specification of a system's components and their relationships) is subjected to a standardized perturbation protocol — a fixed sequence of probe inputs applied under controlled conditions. The system's responses to these probes are measured along cheap-to-compute dimensions (timing, magnitude, ordering of outputs). These response measurements form a low-dimensional signature vector that reliably predicts the system's behavior on novel inputs structurally similar to the probes, without requiring full analysis of the internal state. The key insight: the perturbation protocol acts as a dimensionality-reducing hash function where the hash is computed by observing behavior rather than analyzing structure. Systems with similar signatures under the probe protocol will behave similarly on structurally related real inputs. The protocol must be designed so that the response dimensions are (a) cheap to measure, (b) stable under irrelevant variations in internal state, and (c) discriminative for the functional behaviors that matter for selection.

### Key Insight
A standardized battery of structural probes, applied once at indexing time, compresses each knowledge unit's high-dimensional semantic content into a low-dimensional behavioral signature that predicts relevance to novel queries — enabling sublinear retrieval by comparing signatures rather than full content.

### Architecture
**Behavioral Signature Distillation Index (BSDI)**

Each lens YAML is subjected to a fixed 'probe battery' — a set of 12-16 synthetic problem sketches designed to elicit discriminative responses. These probes are not real problems but minimal structural templates: 'a system with feedback loops and delay', 'a resource allocation under scarcity', 'a pattern recognition with noise', etc.

**Data Structures:**
```python
@dataclass
class ProbeResult:
    probe_id: int  # 0-15
    relevance_score: float  # 0.0-1.0, from lightweight LLM call
    response_latency_ms: int  # time to generate response
    axiom_activation_count: int  # how many axioms were cited
    primary_axiom_indices: List[int]  # top-3 axioms by citation

@dataclass
class LensSignature:
    lens_id: str
    signature_vector: np.ndarray  # shape (16, 4) flattened to (64,)
    probe_response_hash: int  # 64-bit locality-sensitive hash
    cluster_id: int  # pre-computed cluster assignment
    last_updated: datetime

# Index structure
class BSDIndex:
    signatures: Dict[str, LensSignature]  # lens_id -> signature
    lsh_buckets: Dict[int, List[str]]  # hash -> list of lens_ids
    cluster_centroids: np.ndarray  # shape (k, 64) for k clusters
```

**Probe Battery Construction (one-time, amortized):**
```python
PROBE_BATTERY = [
    {'id': 0, 'sketch': 'System with delayed feedback affecting future state'},
    {'id': 1, 'sketch': 'Resource allocation under competing demands'},
    {'id': 2, 'sketch': 'Pattern matching with noisy or incomplete data'},
    {'id': 3, 'sketch': 'Hierarchical decomposition of complex structure'},
    {'id': 4, 'sketch': 'Temporal sequencing with ordering constraints'},
    {'id': 5, 'sketch': 'Equilibrium seeking under perturbation'},
    {'id': 6, 'sketch': 'Information flow through constrained channels'},
    {'id': 7, 'sketch': 'Adaptation to changing environmental conditions'},
    {'id': 8, 'sketch': 'Redundancy and fault tolerance mechanisms'},
    {'id': 9, 'sketch': 'Compression or abstraction of detailed state'},
    {'id': 10, 'sketch': 'Competition for limited attention or bandwidth'},
    {'id': 11, 'sketch': 'Irreversible transformation with path dependence'},
    {'id': 12, 'sketch': 'Synchronization across distributed components'},
    {'id': 13, 'sketch': 'Gradient-following optimization under constraints'},
    {'id': 14, 'sketch': 'Boundary detection and edge case handling'},
    {'id': 15, 'sketch': 'Emergent behavior from local interaction rules'},
]
```

**Signature Generation (per lens, at indexing time):**
```python
def generate_lens_signature(lens: LensYAML) -> LensSignature:
    results = []
    for probe in PROBE_BATTERY:
        response = llm_probe_call(
            prompt=f"Given lens axioms: {lens.axioms[:500]}...\n"
                   f"Problem sketch: {probe['sketch']}\n"
                   f"Rate relevance 0-10 and list top 3 axiom indices.",
            max_tokens=30
        )
        results.append(ProbeResult(
            probe_id=probe['id'],
            relevance_score=response.relevance / 10.0,
            response_latency_ms=response.latency,
            axiom_activation_count=len(response.cited_axioms),
            primary_axiom_indices=response.cited_axioms[:3]
        ))
    
    signature_vector = np.array([
        [r.relevance_score, 
         r.axiom_activation_count / 10.0,
         r.primary_axiom_indices[0] / len(lens.axioms) if r.primary_axiom_indices else 0,
         r.primary_axiom_indices[1] / len(lens.axioms) if len(r.primary_axiom_indices) > 1 else 0]
        for r in results
    ]).flatten()
    
    lsh_hash = compute_lsh(signature_vector, num_planes=8)
    
    return LensSignature(
        lens_id=lens.id,
        signature_vector=signature_vector,
        probe_response_hash=lsh_hash,
        cluster_id=-1,
        last_updated=datetime.now()
    )
```

**Query-Time Retrieval (sublinear):**
```python
def search_lenses(problem: ProblemDescription, top_k: int = 5) -> List[str]:
    problem_signature = generate_problem_signature(problem)
    problem_hash = compute_lsh(problem_signature, num_planes=8)
    candidate_ids = set(index.lsh_buckets.get(problem_hash, []))
    
    for i in range(8):
        adjacent_hash = problem_hash ^ (1 << i)
        candidate_ids.update(index.lsh_buckets.get(adjacent_hash, []))
    
    if len(candidate_ids) < top_k * 2:
        nearest_cluster = find_nearest_cluster(problem_signature, index.cluster_centroids)
        candidate_ids.update(get_cluster_members(nearest_cluster))
    
    ranked = []
    for lens_id in candidate_ids:
        sig = index.signatures[lens_id]
        similarity = cosine_similarity(problem_signature, sig.signature_vector)
        ranked.append((lens_id, similarity))
    
    ranked.sort(key=lambda x: -x[1])
    return [lens_id for lens_id, _ in ranked[:top_k]]
```

### vs Conventional Baseline
SIMPLEST CONVENTIONAL SOLUTION: Evaluate all 80 lenses against each query using full LLM calls. Cost: O(n) LLM calls per query, or one call with O(n) context size.

BSDI STRUCTURAL ADVANTAGE: Amortize LLM cost to indexing time (16 calls per lens, once). Query time uses only 16 lightweight calls + O(1) hash lookup + O(|bucket|) float comparisons. As n grows, query cost remains constant while conventional solution grows linearly. For n=80, BSDI uses ~16 lightweight calls vs ~80 full calls — 5x reduction in LLM tokens. For n=500, BSDI uses ~16 lightweight calls vs ~500 full calls — 30x reduction.

---

## 2. Syndromic Signature Registry with Local-Global Novelty Stratification

**Problem:** The anti-memory system in memory/anti_memory.py tracks convergence at the session level but has no cross-session or cross-problem deduplication, meaning the engine will rediscover and re-output the same structural mappings (e.g. ACO for routing problems) across independent runs with no awareness that it has already produced that invention
**Source Domain:** Epidemiology — Sentinel Surveillance and Syndromic Detection Networks
**Novelty Score:** 0.24 | **Verdict:** QUESTIONABLE

### Abstract Mechanism (domain-neutral)
A two-tier novelty classification system where local detection contexts maintain ephemeral working state while querying a persistent global registry before making uniqueness claims. The key structural insight is the STRATIFICATION of novelty into levels: (1) 'locally novel' means not seen in current context, (2) 'regionally novel' means not seen in structurally adjacent contexts, (3) 'globally novel' means not present in the persistent registry. Each detection event computes a canonical signature from its structural features and queries the registry at multiple resolution levels. The registry maintains not just presence/absence but CIRCULATION METADATA: when was this signature first seen, how many independent contexts have generated it, what is its 'prevalence' (frequency of generation). This prevalence data enables a critical distinction: high-prevalence signatures are 'endemic' (expected, low-value), while low-prevalence signatures with specific structural features are 'emergent' (potentially valuable). The mechanism includes a SYNDROMIC GROUPING function that clusters structurally similar signatures into 'strains', allowing detection of near-duplicates even when exact signatures differ. Finally, the system implements THRESHOLD-BASED ALERTING: only signatures below a prevalence threshold trigger full novelty claims, while endemic signatures return cached results with explicit 'previously known' attribution.

### Key Insight
Novelty is not binary but stratified by scope: an output can be locally novel (first in this context), regionally novel (first in structurally similar contexts), or globally novel (first ever). Tracking prevalence across contexts transforms novelty from a boolean claim into a quantified measure, enabling different handling for endemic (high-frequency, low-value) vs emergent (low-frequency, high-value) outputs.

### Architecture
The architecture consists of three components: a Signature Extractor, a Stratified Registry, and a Novelty Classifier.

**Signature Extractor** transforms each invention into a canonical structural fingerprint:
```python
def extract_signature(invention: Invention) -> StructuralSignature:
    # Extract the mapping skeleton: source_domain_type -> target_domain_type
    mapping_skeleton = frozenset(
        (type(m.source).__name__, type(m.target).__name__, m.mechanism_class)
        for m in invention.mappings
    )
    # Extract the problem shape: dimensionality, constraint types, objective class
    problem_shape = (
        invention.problem.dimensionality,
        frozenset(type(c).__name__ for c in invention.problem.constraints),
        invention.problem.objective_class
    )
    # Compute hierarchical hash at multiple resolutions
    fine_hash = sha256(canonical_serialize(mapping_skeleton, problem_shape))
    coarse_hash = sha256(canonical_serialize(problem_shape))  # ignores specific mapping
    return StructuralSignature(fine=fine_hash, coarse=coarse_hash, raw=mapping_skeleton)
```

**Stratified Registry** is a persistent store with three index levels:
```python
class StratifiedRegistry:
    def __init__(self, db_path: str):
        self.db = sqlite3.connect(db_path)
        self._init_schema()
    
    def _init_schema(self):
        self.db.execute('''
            CREATE TABLE IF NOT EXISTS signatures (
                fine_hash BLOB PRIMARY KEY,
                coarse_hash BLOB,
                first_seen_ts INTEGER,
                generation_count INTEGER DEFAULT 1,
                context_set BLOB,  -- serialized set of context IDs
                strain_id INTEGER,
                raw_mapping BLOB
            )
        ''')
        self.db.execute('CREATE INDEX IF NOT EXISTS idx_coarse ON signatures(coarse_hash)')
        self.db.execute('CREATE INDEX IF NOT EXISTS idx_strain ON signatures(strain_id)')
    
    def query(self, sig: StructuralSignature) -> RegistryResult:
        # Exact match
        exact = self.db.execute(
            'SELECT generation_count, first_seen_ts, context_set FROM signatures WHERE fine_hash = ?',
            (sig.fine,)
        ).fetchone()
        if exact:
            return RegistryResult(
                novelty_level='KNOWN',
                prevalence=exact[0],
                first_seen=exact[1],
                context_count=len(deserialize(exact[2]))
            )
        # Strain match (coarse hash collision)
        strain_matches = self.db.execute(
            'SELECT fine_hash, raw_mapping, generation_count FROM signatures WHERE coarse_hash = ?',
            (sig.coarse,)
        ).fetchall()
        if strain_matches:
            # Compute structural similarity to each strain member
            similarities = [
                (row[0], jaccard_similarity(sig.raw, deserialize(row[1])), row[2])
                for row in strain_matches
            ]
            best_match = max(similarities, key=lambda x: x[1])
            if best_match[1] > 0.85:  # Near-duplicate threshold
                return RegistryResult(
                    novelty_level='STRAIN_VARIANT',
                    prevalence=best_match[2],
                    similar_to=best_match[0],
                    similarity=best_match[1]
                )
            return RegistryResult(novelty_level='STRAIN_NOVEL', strain_size=len(strain_matches))
        return RegistryResult(novelty_level='GLOBALLY_NOVEL')
    
    def register(self, sig: StructuralSignature, context_id: str) -> None:
        existing = self.db.execute(
            'SELECT context_set, generation_count FROM signatures WHERE fine_hash = ?',
            (sig.fine,)
        ).fetchone()
        if existing:
            contexts = deserialize(existing[0])
            contexts.add(context_id)
            self.db.execute(
                'UPDATE signatures SET generation_count = ?, context_set = ? WHERE fine_hash = ?',
                (existing[1] + 1, serialize(contexts), sig.fine)
            )
        else:
            # Assign to strain based on coarse hash
            strain = self.db.execute(
                'SELECT strain_id FROM signatures WHERE coarse_hash = ? LIMIT 1',
                (sig.coarse,)
            ).fetchone()
            strain_id = strain[0] if strain else self._next_strain_id()
            self.db.execute(
                'INSERT INTO signatures VALUES (?, ?, ?, 1, ?, ?, ?)',
                (sig.fine, sig.coarse, int(time.time()), serialize({context_id}), strain_id, serialize(sig.raw))
            )
        self.db.commit()
```

**Novelty Classifier** integrates with the generation pipeline:
```python
class NoveltyClassifier:
    ENDEMIC_THRESHOLD = 10  # Signatures seen >10 times are endemic
    
    def __init__(self, registry: StratifiedRegistry):
        self.registry = registry
        self.session_cache = {}  # Within-session dedup (existing anti_memory)
    
    def classify_and_decide(self, invention: Invention, context_id: str) -> Decision:
        sig = extract_signature(invention)
        
        # Level 1: Session-local check (existing behavior)
        if sig.fine in self.session_cache:
            return Decision(action='SKIP', reason='session_duplicate')
        
        # Level 2: Global registry check
        result = self.registry.query(sig)
        
        if result.novelty_level == 'KNOWN':
            if result.prevalence >= self.ENDEMIC_THRESHOLD:
                # Endemic signature: return cached, charge nothing
                return Decision(
                    action='RETURN_CACHED',
                    reason=f'endemic_signature (seen {result.prevalence} times)',
                    cached_invention=self.registry.get_cached(sig.fine)
                )
            else:
                # Known but rare: regenerate but mark as previously known
                return Decision(
                    action='GENERATE_WITH_ATTRIBUTION',
                    reason=f'known_signature (seen {result.prevalence} times)',
                    prior_contexts=result.context_count
                )
        
        elif result.novelty_level == 'STRAIN_VARIANT':
            return Decision(
                action='GENERATE_WITH_ATTRIBUTION',
                reason=f'strain_variant (similarity={result.similarity:.2f})',
                similar_to=result.similar_to
            )
        
        elif result.novelty_level in ('STRAIN_NOVEL', 'GLOBALLY_NOVEL'):
            return Decision(
                action='GENERATE_AND_REGISTER',
                reason=result.novelty_level,
                novelty_claim_valid=True
            )
        
        self.session_cache[sig.fine] = True
        return Decision(action='GENERATE_AND_REGISTER', novelty_claim_valid=True)
```

**Numerical Example**: User submits routing optimization problem. Signature extractor produces:
- fine_hash: `0x3a7f...` (specific ACO-to-routing mapping)
- coarse_hash: `0x9c2b...` (routing problem shape)

Registry query returns: `{novelty_level: 'KNOWN', prevalence: 47, first_seen: 1699234567, context_count: 31}`

Since prevalence (47) > ENDEMIC_THRESHOLD (10), system returns cached ACO-routing invention with message: "This structural mapping has been generated 47 times across 31 independent sessions. Returning cached result. Novelty claim: FALSE."

**Failure Mode and Recovery**: If registry becomes corrupted, system falls back to session-only dedup (current behavior) and logs warning. Registry can be rebuilt from invention logs if they exist. If signature extraction is non-deterministic (e.g., due to floating point), use tolerance-based hashing with quantization.

**BEFORE/AFTER Comparison**:
- BEFORE: User runs same problem twice, pays full LLM cost twice, receives identical output with false novelty claim both times.
- AFTER: Second run queries registry in O(1), returns cached result with explicit "previously known" attribution, charges nothing.
- Measurable improvement: For endemic signatures (top 20% most common mappings), eliminates 100% of redundant computation. For the system as a whole, expected cost reduction of 60-80% based on Zipf distribution of structural mappings.

**Minimal Viable Version**: Skip strain clustering entirely. Implement only exact-match registry with fine_hash. This captures 80% of benefit (exact duplicates) with 20% of complexity. Add strain clustering later when exact-match hit rate data reveals the prevalence of near-duplicates.

### vs Conventional Baseline
Simplest conventional solution: Persistent hash-based cache with problem-signature keys. Returns cached result on exact match, generates on miss. Structural advantage of this invention: (1) Hierarchical signatures enable near-duplicate detection via coarse-hash clustering, catching semantically equivalent but syntactically different inputs. (2) Prevalence tracking enables endemic/emergent stratification, so the system can distinguish 'this is the 50th time someone asked for ACO-routing' from 'this is a genuinely novel mapping'. (3) Context-set tracking enables provenance claims ('this was first generated on date X by context Y'). The baseline is binary (hit/miss); this system provides a spectrum of novelty levels with associated metadata.

---

## 3. Interpretive Grammar Anchoring Controller

**Problem:** The DeepForge harness applies cognitive interference uniformly across all five pipeline stages, but the Decompose stage (which must produce a precise abstract structural form) and the Translate stage (which must produce a faithful element-by-element mapping) require opposite cognitive postures — interference that helps divergent search actively degrades the precision of structural decomposition and translation fidelity
**Source Domain:** Film Cinematography — Deep Focus vs Shallow Focus Across Multi-Plane Compositions
**Novelty Score:** 0.17 | **Verdict:** QUESTIONABLE

### Abstract Mechanism (domain-neutral)
In a sequential parsing system where a global parameter must serve N stages with heterogeneous optima, the key insight is that early stages do not merely produce outputs — they establish the interpretive grammar through which all subsequent outputs are parsed. The mechanism recognizes that the global parameter cannot be optimized for all stages, but it CAN be optimized for a specific purpose: ensuring that the interpretive grammar established by stage 1 is maximally coherent, because all downstream interpretation depends on this grammar being stable. The mechanism works by: (1) Running stage 1 in isolation under a temporary parameter override that maximizes its precision. (2) Extracting from stage 1's output a 'grammar signature' — a compact representation of the structural constraints that downstream stages must respect. (3) Injecting this grammar signature as a hard constraint into all subsequent stages, so that even when the global parameter induces noise in stages 2-N, the noise is constrained to be grammar-compatible. The global parameter remains uniform across stages 2-N, but the grammar signature acts as a stabilizing anchor that prevents noise from corrupting the foundational structure. This is NOT per-stage parameter tuning — the global parameter is never changed. Instead, it's a two-phase execution where phase 1 extracts invariants and phase 2 enforces them as constraints.

### Key Insight
When a sequential parsing system must operate under a uniform global parameter, the first stage's output is not merely an input to later stages — it is the interpretive grammar that constrains what counts as valid output from all subsequent stages. Extracting this grammar explicitly and enforcing it as a hard constraint allows later stages to operate under high noise while preserving structural coherence.

### Architecture
The architecture introduces a 'Grammar Extraction Phase' that runs before the main pipeline, extracting structural invariants from the Decompose stage that become hard constraints for all subsequent stages.

**Data Structures:**
```python
@dataclass
class GrammarSignature:
    structural_skeleton: Dict[str, Any]  # Abstract form extracted from Decompose
    element_count: int  # Expected number of mapping elements
    relationship_graph: nx.DiGraph  # Directed graph of element dependencies
    checksum: bytes  # SHA256 of canonical serialization
    tolerance_bounds: Dict[str, Tuple[float, float]]  # Per-element acceptable ranges
```

**Algorithm:**
```python
def grammar_anchored_pipeline(problem: Problem, harness: Harness) -> Result:
    # PHASE 1: Grammar Extraction (interference temporarily suspended)
    with harness.suspended_interference():
        decompose_result = decompose_stage(problem)
        grammar = extract_grammar_signature(decompose_result)
    
    # PHASE 2: Constrained Pipeline (full interference, grammar-anchored)
    search_result = search_stage(
        decompose_result, 
        constraint=GrammarConstraint(grammar)
    )
    score_result = score_stage(
        search_result,
        constraint=GrammarConstraint(grammar)
    )
    translate_result = translate_stage(
        score_result,
        constraint=GrammarConstraint(grammar, strict=True)
    )
    synthesize_result = synthesize_stage(
        translate_result,
        constraint=GrammarConstraint(grammar)
    )
    return synthesize_result
```

**Complexity Bounds:**
- Grammar extraction: O(E) where E is element count
- Graph isomorphism check: O(E^3) typical case
- Per-candidate validation: O(E)
- Space: O(E^2) for relationship graph

**Minimal Viable Version:**
1. Add `suspended_interference()` context manager to harness
2. Extract element count from Decompose output
3. Add element count check before Translate stage, rejecting mismatched candidates

### vs Conventional Baseline
**Simplest conventional solution:** Per-stage parameter configuration. Set interference=0.0 for Decompose, interference=1.0 for Search/Score, interference=0.2 for Translate. This requires 5 configuration values and violates the 'global parameter uniformity' constraint.

**This invention's structural advantage:** Maintains uniform global parameter for stages 2-5 while achieving equivalent precision preservation through constraint injection. The grammar signature acts as a 'structural anchor' that prevents noise from corrupting foundational structure, even when interference is high. This is superior when: (a) per-stage configuration is architecturally prohibited, (b) the interference parameter has side effects that require uniform application, (c) the goal is to preserve divergent exploration in later stages while protecting early-stage precision.

---
