# Workspace Inventions for hephaestus

**Problems found:** 7
**Inventions attempted:** 3
**Inventions succeeded:** 3

## 1. Error-Gradient Coefficient Adaptation

**Problem:** The 80+ domain lenses are static YAML axiom sets that never update based on which structural matches actually produced high-quality inventions, creating a frozen knowledge graph that degrades relative to the expanding frontier of solved problems.
**Source Domain:** Acoustics — Adaptive Room Correction and Acoustic Feedback Cancellation
**Novelty Score:** 0.27 | **Verdict:** QUESTIONABLE

### Abstract Mechanism (domain-neutral)
A system with N fixed transformation elements (filters/templates) that process input signals. Each element has a coefficient (weight) determining its contribution to the output. A measurement subsystem continuously samples the actual output and compares it against a target response, producing an error signal. The error signal is decomposed to estimate each element's contribution to the total error. Element coefficients are updated by gradient descent: coefficient_i(t+1) = coefficient_i(t) - η * ∂error/∂coefficient_i. The key structural feature is that the elements themselves are IMMUTABLE — only their multiplicative weights change. The adaptation tracks non-stationary target distributions because the feedback loop operates continuously, not in batches. The error decomposition uses the correlation between each element's activation pattern and the residual error to estimate partial derivatives without requiring differentiable elements.

### Key Insight
The templates are immutable but their influence weights are not. By treating quality deviation as an error signal and distributing it across activated templates proportionally to their current weights, the system performs implicit gradient descent on template utility without modifying the templates themselves. The baseline adapts to track shifting quality norms, so the error signal always reflects relative rather than absolute performance.

### Architecture
ARCHITECTURE: Error-Gradient Coefficient Adaptation for Template Libraries

DATA STRUCTURES:
1. CoefficientVector: float[80] initialized to 1.0/80 (uniform prior)
2. ActivationHistory: RingBuffer<(template_id, problem_hash, timestamp)> of size 4096
3. OutcomeRegistry: HashMap<problem_hash, QualityScore> where QualityScore ∈ [0.0, 1.0]
4. ErrorAccumulator: float[80] initialized to 0.0
5. TargetBaseline: ExponentialMovingAverage with α=0.05, initialized to 0.5

CORE ALGORITHM:

```python
def on_template_selection(template_id: int, problem_hash: str):
    ActivationHistory.push((template_id, problem_hash, now()))

def on_outcome_observed(problem_hash: str, quality: float):
    OutcomeRegistry[problem_hash] = quality
    TargetBaseline.update(quality)
    
    # Find all templates activated for this problem
    activated = [t for (t, p, _) in ActivationHistory if p == problem_hash]
    
    # Compute error signal: deviation from adaptive baseline
    error = quality - TargetBaseline.value
    
    # Distribute error gradient across activated templates
    # Using correlation-based attribution
    for template_id in activated:
        # Each template gets credit/blame proportional to its current weight
        # This implements ∂error/∂coefficient estimation
        gradient = error * CoefficientVector[template_id]
        ErrorAccumulator[template_id] += gradient

def coefficient_update_step(learning_rate: float = 0.01):
    """Called periodically (e.g., every 100 outcomes)"""
    for i in range(80):
        # Gradient descent on coefficients
        CoefficientVector[i] += learning_rate * ErrorAccumulator[i]
        # Clamp to prevent negative or explosive weights
        CoefficientVector[i] = max(0.01, min(10.0, CoefficientVector[i]))
        ErrorAccumulator[i] = 0.0
    
    # Normalize to sum to 1 (optional, for probability interpretation)
    total = sum(CoefficientVector)
    CoefficientVector = [c/total for c in CoefficientVector]

def select_template(problem_features: Vector) -> int:
    """Template selection weighted by adapted coefficients"""
    # Base scores from structural matching (existing system)
    base_scores = compute_structural_match_scores(problem_features)
    
    # Modulate by learned coefficients
    weighted_scores = [base_scores[i] * CoefficientVector[i] for i in range(80)]
    
    # Softmax selection with temperature τ=0.5 for exploration
    τ = 0.5
    probs = softmax([s/τ for s in weighted_scores])
    return sample_categorical(probs)
```

COMPLEXITY BOUNDS:
- on_template_selection: O(1) amortized (ring buffer push)
- on_outcome_observed: O(k) where k = templates activated for that problem (typically 1-3)
- coefficient_update_step: O(80) = O(1) constant
- select_template: O(80) for scoring + O(80) for softmax = O(1) constant
- Space: O(4096) for activation history + O(80) for coefficients = O(1) constant

NUMERICAL EXAMPLE:
Initial state: All 80 coefficients = 0.0125, TargetBaseline = 0.5

Event sequence:
1. Problem P1 matched with Template T7, activated: [(7, P1, t1)]
2. Outcome: quality=0.85, error=0.85-0.5=+0.35
3. ErrorAccumulator[7] += 0.35 * 0.0125 = 0.004375
4. Problem P2 matched with Template T7, T12
5. Outcome: quality=0.3, error=0.3-0.52=-0.22 (baseline updated)
6. ErrorAccumulator[7] += -0.22 * 0.0125 = -0.00275
7. ErrorAccumulator[12] += -0.22 * 0.0125 = -0.00275

After 100 outcomes, coefficient_update_step():
- T7: 0.0125 + 0.01*(0.004375 - 0.00275 + ...) → adjusted based on net gradient
- Templates consistently producing above-baseline outcomes drift upward
- Templates consistently producing below-baseline outcomes drift downward

FAILURE MODE AND RECOVERY:
Failure: Cold-start problem — new templates or templates rarely selected accumulate no gradient signal, coefficients stagnate.
Recovery: Implement coefficient decay toward prior: coefficient_i(t+1) = (1-λ)*coefficient_i(t) + λ*prior, where λ=0.001 and prior=1/80. This prevents coefficients from locking at extreme values and ensures rarely-used templates slowly regress to neutral rather than staying at arbitrary historical values.

Failure: Distribution shift — problem domain changes rapidly, historical gradients become misleading.
Recovery: ErrorAccumulator uses exponential decay: ErrorAccumulator[i] *= 0.95 before each update. Recent outcomes contribute more than ancient ones. Additionally, TargetBaseline's exponential moving average automatically tracks shifting quality norms.

### vs Conventional Baseline
Simplest conventional solution: Log (template, problem, quality) tuples, compute mean quality per template, rank templates by mean, bias selection toward high-ranked templates. Structural advantage of this invention: (1) Adaptive baseline means 'high quality' is defined relative to current system performance, not absolute scale, enabling tracking of distribution shift. (2) Gradient accumulation with exponential decay weights recent outcomes more than historical ones. (3) Multiplicative coefficient update (c *= 1 + η*e) rather than additive ranking means templates that work well on hard problems (low absolute quality but above baseline) still accumulate positive gradients. (4) Continuous feedback loop rather than batch recomputation means the system responds to quality signals within ~100 outcomes rather than waiting for scheduled analysis.

---

## 2. Audience-Indexed Depletion Sampling

**Problem:** The anti-memory system in memory/anti_memory.py operates at the session level only, meaning convergence prevention resets between runs — the engine can rediscover the same 'novel' solution for structurally similar problems submitted days apart with no cross-session divergence.
**Source Domain:** Mythology — Oral Epic Tradition and Formulaic Composition
**Novelty Score:** 0.18 | **Verdict:** INVALID

### Abstract Mechanism (domain-neutral)
A generative system maintains a dual-layer selection structure: (1) a complete catalog of functionally-equivalent alternatives for each output slot, organized by the abstract function being fulfilled, and (2) a depletion map indexed by the tuple (requester-identity, structural-query-signature) rather than by session. When generating output, the system first resolves the requester-identity and query-signature, retrieves the depletion set for that tuple, and constrains selection to the complement of that set within the functional slot. The depletion map persists because it is keyed to entities that persist (requester identity, problem structure) rather than to the ephemeral session container. The key insight: persistence is achieved not by storing state in a persistent container, but by indexing state to naturally-persistent keys that can be reconstructed from the input itself. The requester identity and structural query signature are derivable from each request; the depletion state is encoded as a deterministic function of (identity, signature, prior-outputs) that can be reconstructed without explicit storage by re-deriving from the request's own persistent properties.

### Key Insight
Persistence is achieved not by storing state in a persistent container, but by indexing state to naturally-persistent keys that can be reconstructed from the input itself — the requester identity and structural query signature are derivable from each request, so the depletion state can be encoded as a deterministic function of these keys plus a time-derived index, eliminating the need for explicit cross-session storage.

### Architecture
The anti-memory system is restructured around three components: a Structural Signature Extractor, a Requester Identity Resolver, and a Deterministic Depletion Function.

**Structural Signature Extractor**: Given a problem statement P, extract a canonical structural signature S(P) that maps structurally equivalent problems to the same key. Implementation:
```python
def extract_signature(problem: str) -> bytes:
    # Parse to abstract structure: remove domain vocabulary
    abstract = normalize_to_abstract_form(problem)
    # Extract: (constraint_graph_hash, objective_type, variable_count_bucket)
    constraint_hash = hash_constraint_graph(abstract.constraints)
    obj_type = classify_objective(abstract.objective)  # enum: minimize, maximize, satisfy, explore
    var_bucket = bucket_variable_count(abstract.variables)  # 1-3, 4-10, 11-50, 50+
    return sha256(f"{constraint_hash}:{obj_type}:{var_bucket}".encode())[:16]
```
Complexity: O(n) where n is problem token count. Space: 16 bytes per signature.

**Requester Identity Resolver**: Extract a stable requester identity R from the session context. This may be an API key hash, a user ID, or a derived fingerprint from request metadata. If no identity is available, use a global identity (all anonymous users share depletion state).
```python
def resolve_identity(session_context: dict) -> bytes:
    if 'user_id' in session_context:
        return sha256(session_context['user_id'].encode())[:8]
    if 'api_key' in session_context:
        return sha256(session_context['api_key'].encode())[:8]
    return b'\x00' * 8  # global identity
```

**Deterministic Depletion Function**: The core insight — instead of persisting the depletion set explicitly, encode it as a deterministic function of (R, S, generation_index). The generation_index is derived from the request itself by including a monotonic counter in the request or by hashing (R, S, timestamp_bucket). For each (R, S) pair, the system generates outputs from a deterministic sequence seeded by (R, S), and the current position in that sequence is communicated via the request.

```python
class DeterministicDepletionSampler:
    def __init__(self, solution_manifold: list, k_variants: int = 64):
        self.manifold = solution_manifold
        self.k = k_variants  # number of distinct variants per structural slot
    
    def sample(self, requester_id: bytes, signature: bytes, generation_index: int) -> any:
        # Seed determines the permutation of the manifold for this (R, S) pair
        seed = int.from_bytes(sha256(requester_id + signature).digest()[:8], 'big')
        rng = Random(seed)
        permuted_manifold = self.manifold.copy()
        rng.shuffle(permuted_manifold)
        
        # generation_index selects position in the permutation
        # Wraps after k variants, but with warning
        effective_index = generation_index % self.k
        if generation_index >= self.k:
            log_warning(f"Depletion cycle complete for ({requester_id.hex()}, {signature.hex()}), recycling")
        
        return permuted_manifold[effective_index]
```

**Integration with anti_memory.py**:
```python
class CrossSessionAntiMemory:
    def __init__(self, solution_variants_per_slot: int = 64):
        self.k = solution_variants_per_slot
        self.samplers = {}  # structural_slot -> DeterministicDepletionSampler
    
    def register_slot(self, slot_name: str, variants: list):
        self.samplers[slot_name] = DeterministicDepletionSampler(variants, self.k)
    
    def generate(self, problem: str, session_context: dict, generation_index: int) -> any:
        signature = extract_signature(problem)
        requester_id = resolve_identity(session_context)
        slot = classify_structural_slot(problem)
        
        if slot not in self.samplers:
            raise ValueError(f"Unknown structural slot: {slot}")
        
        return self.samplers[slot].sample(requester_id, signature, generation_index)
```

**The generation_index problem**: How does the system know which index to use without persistent state? Three options:
1. **Client-provided**: The client includes a counter in the request (e.g., "this is my 3rd question about rate limiting"). Simple but requires client cooperation.
2. **Timestamp-bucketed**: Derive index from floor(timestamp / bucket_size). With bucket_size = 7 days and k = 64, the system cycles through all variants over ~1.2 years before repeating.
3. **Content-hash chaining**: Include a hash of the previous response in the next request, allowing reconstruction of the chain position.

**Concrete numerical example**:
- User A (id=0xABCD) submits "rate limiting under bursty load" on Monday
- signature = sha256("constraint:queue_overflow,obj:minimize,vars:4-10")[:16] = 0x7F3E...
- generation_index = 0 (first request this week for this signature)
- seed = sha256(0xABCD + 0x7F3E...)[:8] = 0x91C2...
- Permuted manifold for this (R, S): [variant_47, variant_12, variant_3, ...]
- Output: variant_47

- Same user submits "queue management under Poisson arrivals" on Friday
- signature = sha256("constraint:queue_overflow,obj:minimize,vars:4-10")[:16] = 0x7F3E... (same!)
- generation_index = 1 (second request this week for this signature)
- Same seed, same permutation
- Output: variant_12 (different!)

**Failure mode and recovery**: If the signature extraction is too coarse, unrelated problems map to the same signature and deplete each other's variants. Recovery: monitor for premature depletion warnings and refine the signature extraction to increase granularity. If too fine, no cross-session divergence occurs. Tune via A/B testing on repetition rate.

### vs Conventional Baseline
Baseline: Store (signature, requester_id, output) tuples in a database; on each request, query for prior outputs and exclude them from sampling. Requires O(n) storage where n is total historical outputs, O(log n) lookup time, database infrastructure, and explicit persistence management. This invention: O(1) storage (zero), O(1) computation (hash + permutation + index lookup), no infrastructure beyond the application itself. The tradeoff: baseline can handle arbitrary depletion patterns; this invention is constrained to sequential depletion through a fixed permutation, but that constraint matches the actual use case (users don't skip around in the variant space, they just want 'something different than last time').

---

## 3. Activation-Barrier Certificate Architecture

**Problem:** The novelty proof in output/proof.py generates a structural isomorphism claim at invention time but has no mechanism to invalidate or update that proof when prior art is later published, leaving users holding stale novelty certificates.
**Source Domain:** Culinary — Emulsification: Pickering Stabilization and Interfacial Armor
**Novelty Score:** 0.28 | **Verdict:** QUESTIONABLE

### Abstract Mechanism (domain-neutral)
A metastable state is maintained against continuous destabilizing pressure not by detecting when destabilization occurs, but by interposing structural barriers that make any transition from the current state to an alternative state require crossing a high activation energy threshold. The barriers are passive and stateless — they do not monitor the destabilizing force, they simply make all state transitions expensive. The system remains practically stable not because the destabilizing conditions are absent, but because the transition rate is negligible on decision-relevant timescales. Critically, the barrier is at the interface between the protected state and its consumers — every attempt to USE the protected state must pass through the barrier, which forces re-engagement with current conditions. The barrier particles are 'ambivalent' — they have affinity for both the protected state and the external reality, and this dual affinity is what allows them to lodge at the interface and resist displacement.

### Key Insight
A validity certificate can be made self-verifying at consumption time by embedding queries that must return unchanged results — the certificate doesn't need to know when it's invalid, it just needs to make every use require re-checking against current reality

### Architecture
The certificate is restructured so that it cannot be consumed without crossing a verification barrier. The certificate contains not a validity claim but a validity *challenge* — a cryptographic commitment to the state of the knowledge base at generation time, plus a verification protocol that any consumer must execute.

Data structure:
```
struct ArmoredCertificate {
  claim_hash: bytes32,           // H(invention_description)
  knowledge_state_root: bytes32, // Merkle root of prior art DB at time T
  generation_timestamp: uint64,
  barrier_particles: Vec<BarrierParticle>,
  activation_energy: uint32,     // default: 3 (number of particles that must verify)
}

struct BarrierParticle {
  query_template: String,        // e.g., "semantic_search(claim_hash, top_k=10)"
  expected_null_proof: bytes32,  // H(empty_result) at generation time
  verification_endpoint: URI,    // where to re-run the query
}
```

Verification protocol (must be executed before any certificate consumption):
```
fn verify_certificate(cert: ArmoredCertificate) -> VerificationResult {
  let mut passed = 0;
  let mut failed_particles = vec![];
  
  for particle in cert.barrier_particles {
    let current_result = execute_query(particle.verification_endpoint, particle.query_template);
    let current_hash = hash(current_result);
    
    if current_hash == particle.expected_null_proof {
      passed += 1;
    } else {
      failed_particles.push(BarrierFailure {
        particle: particle,
        new_witnesses: current_result,
        displacement_energy: calculate_semantic_distance(cert.claim_hash, current_result),
      });
    }
  }
  
  if passed >= cert.activation_energy {
    return VerificationResult::StillValid { 
      confidence: passed as f32 / cert.barrier_particles.len() as f32,
      timestamp: now(),
    };
  } else {
    return VerificationResult::BarrierBroken {
      failed_particles: failed_particles,
      invalidation_evidence: failed_particles.iter().flat_map(|f| f.new_witnesses).collect(),
    };
  }
}
```

The key architectural property: the certificate is *useless* without executing the verification protocol. Any system that consumes the certificate must call `verify_certificate()` first. This is enforced by making the certificate's actual validity claim derivable only from the verification result, not stored in the certificate itself.

Complexity: O(n_particles * query_cost) per verification; space O(n_particles) per certificate.

### vs Conventional Baseline
Simplest conventional solution: Add TTL field, mark certificates expired after 30 days, require manual re-verification. This architecture's advantage: (1) No arbitrary time threshold — certificates remain valid exactly as long as the underlying reality supports them. (2) No central re-verification service — verification is distributed to consumers. (3) Graceful degradation — partial barrier failure (some particles pass, some fail) gives confidence scores rather than binary valid/invalid. (4) Evidence preservation — when invalidation occurs, the failing particles identify exactly which new publications caused it.

---
