# Workspace Inventions for hephaestus

**Problems found:** 7
**Inventions attempted:** 3
**Inventions succeeded:** 3

## 1. Gestalt-Resistant Polysemous Encoding

**Problem:** The 5-stage Genesis pipeline executes sequentially with no inter-stage feedback, so a poor decomposition in Stage 1 propagates uncorrected through all downstream stages, wasting the full LLM budget on a flawed structural form.
**Source Domain:** Social Psychology — Impression Formation and Primacy Effects in Person Perception
**Novelty Score:** 0.19 | **Verdict:** QUESTIONABLE

### Abstract Mechanism (domain-neutral)
When a sequence of symbolic tokens is processed to form a unified representation, the first tokens encountered do not merely receive higher weight — they establish an interpretive frame that semantically transforms the encoding of all subsequent tokens. The mechanism operates through meaning-change rather than attention-weighting: token T₅ is not just 'less attended to' than T₁, but T₅'s semantic content is actively rewritten to be consistent with the frame established by T₁. This creates a non-commutative composition operation where encode([T₁, T₂, ..., Tₙ]) ≠ encode([Tₙ, ..., T₂, T₁]) even when the final representation is supposedly order-invariant. The frame crystallizes after processing k initial tokens (typically k=2-3), after which the system enters an assimilation regime where new information is force-fit into the existing schema rather than allowed to modify it. Critically, the transformation is invisible to the system itself — it believes it is processing T₅ objectively when it is actually processing T₅-as-interpreted-through-frame(T₁,T₂). No downstream signal can trigger re-evaluation because the original meaning of T₅ is lost; only the assimilated version persists.

### Key Insight
The first stage's output should not be a single interpretation but a superposition of incompatible interpretations, with the commitment to a single interpretation deferred until downstream processing provides discriminating evidence — converting early-binding to evidence-gated binding.

### Architecture
**Core Architecture: Polysemous Decomposition with Deferred Frame Commitment**

The key insight is that Stage 1 should NOT output a single structural form. Instead, it outputs a *polysemous encoding* — a data structure that preserves multiple incompatible interpretive frames simultaneously, deferring the commitment to a single frame until downstream stages provide discriminating evidence.

**Data Structure: PolysemousForm**
```python
@dataclass
class PolysemousForm:
    # Core problem statement (frame-invariant)
    invariant_core: str
    
    # Multiple incompatible interpretive frames
    frames: List[InterpretiveFrame]  # typically 3-5 frames
    
    # Frame-specific structural forms
    frame_forms: Dict[FrameID, StructuralForm]
    
    # Discrimination predicates: conditions that would favor one frame over another
    discriminators: List[Discriminator]
    
    # Commitment threshold: minimum discriminator evidence before collapsing
    commitment_threshold: float = 0.7

@dataclass
class InterpretiveFrame:
    frame_id: FrameID
    frame_description: str
    # What this frame emphasizes vs. backgrounds
    salience_mask: Dict[str, float]
    # What would confirm this frame is correct
    confirming_evidence: List[str]
    # What would disconfirm this frame
    disconfirming_evidence: List[str]

@dataclass
class Discriminator:
    # A predicate that can be evaluated by downstream stages
    predicate: str
    # Which frames it favors/disfavors and by how much
    frame_weights: Dict[FrameID, float]  # positive = favors, negative = disfavors
```

**Modified Pipeline Flow:**

```python
def genesis_pipeline_polysemous(problem: str, budget: int) -> Invention:
    # Stage 1: Decompose into PolysemousForm (not single form)
    poly_form = decompose_polysemous(problem, budget_fraction=0.15)
    
    # Stage 2: Search runs ONCE but tags results with frame affinity
    tagged_candidates = search_with_frame_tagging(
        poly_form, 
        budget_fraction=0.35
    )
    
    # Stage 2.5: Frame Collapse (NEW) - use search results as discriminating evidence
    committed_frame, collapse_confidence = collapse_frame(
        poly_form,
        tagged_candidates,
        threshold=poly_form.commitment_threshold
    )
    
    # If no frame achieves threshold, use ensemble scoring
    if collapse_confidence < poly_form.commitment_threshold:
        # Stage 3-5 run with weighted ensemble across frames
        return ensemble_downstream(poly_form, tagged_candidates, budget_fraction=0.50)
    else:
        # Stage 3-5 run with committed frame
        return committed_downstream(committed_frame, tagged_candidates, budget_fraction=0.50)
```

**Frame Collapse Algorithm:**

```python
def collapse_frame(
    poly_form: PolysemousForm,
    tagged_candidates: List[TaggedCandidate],
    threshold: float
) -> Tuple[InterpretiveFrame, float]:
    """
    Use search results as discriminating evidence to collapse the polysemous
    form into a single committed frame.
    
    Time complexity: O(|frames| * |candidates| * |discriminators|)
    Space complexity: O(|frames|)
    """
    frame_scores = {f.frame_id: 0.0 for f in poly_form.frames}
    evidence_count = 0
    
    for candidate in tagged_candidates:
        # Each candidate provides evidence about which frame is correct
        for disc in poly_form.discriminators:
            if evaluate_predicate(disc.predicate, candidate):
                evidence_count += 1
                for frame_id, weight in disc.frame_weights.items():
                    frame_scores[frame_id] += weight * candidate.relevance_score
    
    # Normalize scores
    if evidence_count > 0:
        total = sum(abs(s) for s in frame_scores.values())
        if total > 0:
            frame_scores = {k: (v / total + 1) / 2 for k, v in frame_scores.items()}
    
    best_frame_id = max(frame_scores, key=frame_scores.get)
    confidence = frame_scores[best_frame_id]
    
    best_frame = next(f for f in poly_form.frames if f.frame_id == best_frame_id)
    return best_frame, confidence
```

**Concrete Numerical Example:**

Problem: "Optimize database query execution with limited memory"

Stage 1 outputs PolysemousForm with 3 frames:
- Frame A (resource-allocation): "This is about distributing a fixed budget across competing demands" (salience: memory=0.9, time=0.3)
- Frame B (search-problem): "This is about finding optimal execution paths in a large space" (salience: memory=0.3, time=0.9)
- Frame C (caching-problem): "This is about deciding what to remember vs. recompute" (salience: memory=0.7, time=0.7)

Discriminators:
- D1: "Candidate involves scheduling" → {A: +0.4, B: -0.1, C: 0.0}
- D2: "Candidate involves pruning search space" → {A: -0.2, B: +0.5, C: +0.1}
- D3: "Candidate involves eviction policies" → {A: 0.0, B: -0.2, C: +0.6}

Stage 2 Search returns 12 candidates. Evaluation:
- 4 candidates trigger D1 (avg relevance 0.6): Frame A gets +0.96
- 2 candidates trigger D2 (avg relevance 0.8): Frame B gets +0.80
- 5 candidates trigger D3 (avg relevance 0.7): Frame C gets +2.10

Normalized scores: A=0.37, B=0.35, C=0.71

Frame C exceeds threshold (0.7 ≥ 0.7), so pipeline commits to the caching-problem frame. Stages 3-5 now operate on the caching-specific structural form rather than the potentially wrong resource-allocation frame that might have been selected by a single-frame Stage 1.

**Failure Mode and Recovery:**

Failure: All frames score below threshold (e.g., max score = 0.55 < 0.7). This indicates the search results don't discriminate between interpretations.

Recovery: Run ensemble mode where Stages 3-5 maintain weighted superposition:
```python
def ensemble_downstream(poly_form, candidates, budget):
    results = []
    for frame in poly_form.frames:
        frame_budget = budget * frame_scores[frame.frame_id]
        if frame_budget > MIN_VIABLE_BUDGET:
            results.append(run_stages_3_5(frame, candidates, frame_budget))
    return merge_inventions(results, weights=frame_scores)
```

### vs Conventional Baseline
**Simplest conventional solution:** Run Stage 1 once, produce single structural form, hope it's right. If Verify score is low, return weak result.

**This invention's structural advantage:** By outputting multiple interpretations from Stage 1 and using Stage 2 results as discriminating evidence, the system can correct a poor initial interpretation without re-running any stage. The 'correction' happens at the collapse point between Stage 2 and Stage 3, using information that would otherwise be wasted (search results that don't match the committed frame are normally discarded; here they inform frame selection). Cost increase is ~25% in Stages 1-2, but avoids the 5x cost of full re-runs that feedback-loop approaches require.

---

## 2. Harmonic Spectrum Policy Router

**Problem:** Domain lens selection is static per-run with no cross-run learning, so the engine cannot improve its lens-to-problem-class routing over time despite accumulating a rich history of scored invention attempts.
**Source Domain:** Music — Acoustic Instrument Design and Organ Pipe Voicing
**Novelty Score:** 0.25 | **Verdict:** QUESTIONABLE

### Abstract Mechanism (domain-neutral)
A selection system decomposes each input instance into a characteristic signature consisting of a fundamental structural type plus a series of secondary structural features at decreasing strengths (analogous to a fundamental frequency plus overtones). The catalog of operators is similarly decomposed: each operator has a 'spectral response profile' describing which input signatures it amplifies (produces high scores) and which it attenuates (produces low scores). Selection proceeds by computing the interference pattern between the input's signature spectrum and each operator's response profile. Operators whose response profiles show constructive interference with the input signature are selected; those showing destructive interference are suppressed. The learned component is the response profile for each operator, built incrementally from outcome signals. Critically, the system exploits resonance: when an input's signature matches an operator's 'natural frequency' (the input class where it historically excels), even weak feature signals in the input produce strong selection confidence. The system also tracks 'room acoustics' — contextual modifiers (time of day, recent problem sequence, user preferences) that shift which operators resonate with which inputs, analogous to how room geometry changes which frequencies reach the listener.

### Key Insight
Operators have characteristic response profiles across input feature dimensions, and the dot product between input features and operator profiles predicts outcome quality — but sharply-tuned operators (high variance in their profile) should be boosted when inputs match their peak and suppressed otherwise, because specialization indicates reliable signal rather than noise

### Architecture
The Harmonic Spectrum Policy Router maintains three persistent data structures:

**1. Input Signature Decomposer (ISD):** A function that extracts a fixed-length spectral vector from each problem instance. The vector has K=16 dimensions, where dimension 0 represents the 'fundamental' (primary problem class, e.g., 'distributed-systems') and dimensions 1-15 represent 'overtones' (secondary features like 'Poisson-arrival', 'stateless', 'latency-sensitive'). Each dimension has an amplitude in [0,1] representing feature strength. The decomposition is deterministic and uses a pre-trained embedding model fine-tuned on problem descriptions.

```python
def decompose_input(problem_text: str) -> np.ndarray:
    embedding = embed_model.encode(problem_text)  # 384-dim
    fundamental = classify_primary_domain(embedding)  # one-hot over 8 domains
    overtones = extract_secondary_features(embedding)  # 8 continuous features
    return np.concatenate([fundamental, overtones])  # 16-dim spectral vector
```

**2. Operator Response Profile Matrix (ORPM):** A matrix R of shape (80, 16) where R[i,j] represents lens i's historical effectiveness when input dimension j is active. Initialized to 0.5 (neutral). Updated after each run using exponential moving average with α=0.1:

```python
def update_orpm(lens_id: int, input_spectrum: np.ndarray, fidelity_score: float):
    # Compute contribution of each spectral component to this outcome
    for j in range(16):
        if input_spectrum[j] > 0.1:  # feature was active
            old = ORPM[lens_id, j]
            # Weight update by feature amplitude
            contribution = input_spectrum[j] * fidelity_score
            ORPM[lens_id, j] = (1 - alpha) * old + alpha * contribution
```

**3. Resonance Amplification Index (RAI):** For each lens, track the variance of its response profile. High-variance lenses are 'sharply tuned' — they resonate strongly with specific input types but attenuate others. Low-variance lenses are 'broadband' — moderate effectiveness across all inputs. This is computed as:

```python
def compute_resonance_sharpness(lens_id: int) -> float:
    profile = ORPM[lens_id, :]
    return np.std(profile) / (np.mean(profile) + 0.01)
```

**Selection Algorithm:**

```python
def select_lenses(problem_text: str, k: int = 5) -> List[int]:
    input_spectrum = decompose_input(problem_text)
    
    scores = []
    for lens_id in range(80):
        response_profile = ORPM[lens_id, :]
        
        # Compute interference: dot product gives constructive/destructive sum
        interference = np.dot(input_spectrum, response_profile)
        
        # Apply resonance amplification: sharply-tuned lenses get boosted
        # when input matches their peak, penalized otherwise
        sharpness = RAI[lens_id]
        peak_match = np.corrcoef(input_spectrum, response_profile)[0,1]
        resonance_bonus = sharpness * max(0, peak_match) ** 2
        
        final_score = interference + resonance_bonus
        scores.append((lens_id, final_score))
    
    # Select top-k by score, but ensure diversity in fundamental coverage
    scores.sort(key=lambda x: -x[1])
    selected = []
    fundamentals_covered = set()
    
    for lens_id, score in scores:
        lens_fundamental = np.argmax(ORPM[lens_id, :8])
        if len(selected) < k:
            if lens_fundamental not in fundamentals_covered or len(selected) >= k-2:
                selected.append(lens_id)
                fundamentals_covered.add(lens_fundamental)
    
    return selected
```

**Destructive Interference Detection:** The system also identifies 'anti-resonant' pairs — lenses that historically produce poor results when applied together to the same problem class (their combined spectral responses cancel out useful signal):

```python
def detect_destructive_pairs() -> List[Tuple[int, int]]:
    bad_pairs = []
    for i in range(80):
        for j in range(i+1, 80):
            combined = ORPM[i, :] + ORPM[j, :]
            # If combined profile is flatter than either individual
            if np.std(combined) < 0.5 * min(np.std(ORPM[i,:]), np.std(ORPM[j,:])):
                bad_pairs.append((i, j))
    return bad_pairs
```

**Concrete Numerical Example:**

Problem: 'Design a rate limiter for a distributed API gateway handling bursty Poisson-arrival traffic'

Input spectrum: [0.9, 0.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.7, 0.3, 0.8, 0.1, 0.0, 0.0, 0.0, 0.0]
(Fundamental: distributed-systems=0.9; Overtones: Poisson-arrival=0.7, stateless=0.3, latency-sensitive=0.8)

Lens 'biology/swarm' has ORPM row: [0.85, 0.2, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.9, 0.4, 0.7, 0.2, 0.1, 0.1, 0.1, 0.1]

Interference score: dot product = 0.9*0.85 + 0.7*0.9 + 0.3*0.4 + 0.8*0.7 = 0.765 + 0.63 + 0.12 + 0.56 = 2.075
Resonance sharpness: 0.31
Peak match correlation: 0.89
Resonance bonus: 0.31 * 0.89^2 = 0.245
Final score: 2.32

Lens 'economics/auction' has ORPM row: [0.3, 0.1, 0.8, 0.1, 0.1, 0.1, 0.1, 0.1, 0.2, 0.1, 0.3, 0.1, 0.1, 0.1, 0.1, 0.1]

Interference score: 0.9*0.3 + 0.7*0.2 + 0.3*0.1 + 0.8*0.3 = 0.27 + 0.14 + 0.03 + 0.24 = 0.68
Final score: ~0.72 (low resonance bonus due to poor peak match)

Result: biology/swarm lens ranks much higher than economics/auction for this problem.

**Failure Mode and Recovery:** If the ORPM becomes corrupted (e.g., a bug causes all values to converge to 0.5), the system detects this via entropy monitoring: if the variance across the entire matrix drops below 0.05, trigger a 'recalibration phase' where 20% of runs use uniform random lens selection to rebuild the response profiles. Recovery takes approximately 50 runs to restore meaningful differentiation.

### vs Conventional Baseline
The simplest conventional solution is a lookup table mapping problem keywords to historically successful lenses. This fails when problems have novel keyword combinations, provides no mechanism for detecting lens interactions, and treats all historical successes as equally informative regardless of problem-lens specificity. The Harmonic Spectrum Policy Router instead builds continuous response profiles that generalize across feature combinations, explicitly models lens specialization via variance tracking, and detects destructive interference between lens pairs — enabling both better generalization and identification of lens combinations to avoid.

---

## 3. Gradient-Discriminated Score Calibration

**Problem:** The novelty scoring function (fidelity × distance^1.5) is a fixed formula with hand-tuned exponents, making it impossible to detect when scores are inflated by the LLM's own prior knowledge of cross-domain analogies rather than genuine structural discovery.
**Source Domain:** Coral Reef Symbiosis — Symbiodinium Clade Recognition and Fidelity
**Novelty Score:** 0.28 | **Verdict:** INVALID

### Abstract Mechanism (domain-neutral)
An evaluator receives signals from a source whose internal state is unobservable and potentially biased. The evaluator cannot distinguish whether high signal values reflect genuine quality or source-specific optimization for the evaluation context. The mechanism breaks this confound by presenting the source with a GRADIENT of evaluation contexts that vary along a dimension orthogonal to the quality being measured. A source with narrow prior optimization will produce high signals only in matching contexts, while a source with genuine quality produces consistent signals across the gradient. The evaluator computes two statistics: (1) the mean signal across contexts, and (2) the variance of signals across contexts. The ratio of variance to mean serves as a confound detector — high variance relative to mean indicates context-specific optimization (prior exposure), while low variance relative to mean indicates robust quality. The final score is the mean signal DISCOUNTED by a monotonic function of the variance-to-mean ratio. Mathematically: if S_i is the signal in context i, final_score = mean(S) × f(1 - CV(S)) where CV is coefficient of variation and f is a sigmoid that maps [0,1] → [0.3, 1.0]. This creates an instrumental variable from the gradient itself — the gradient dimension is chosen to be uncorrelated with true quality but correlated with prior optimization.

### Key Insight
An oracle's prior exposure to an item inflates its reported quality only in evaluation contexts that match its training context. By evaluating across a gradient of contexts and measuring score variance, we create a synthetic instrumental variable that reveals the latent confound without requiring ground-truth labels.

### Architecture
The scoring system evaluates each proposed analogy not once but across a PROMPT GRADIENT — a set of 5-7 systematically varied evaluation contexts that differ in framing, abstraction level, and domain vocabulary while asking about the same structural mapping.

CONCRETE DATA STRUCTURES:
```
struct PromptGradient {
  base_analogy: Analogy,
  contexts: Vec<EvalContext>,  // length 5-7
}

struct EvalContext {
  abstraction_level: f32,      // 0.0 = concrete, 1.0 = abstract
  vocabulary_set: VocabMask,   // which domain terms to use/avoid
  framing: FrameType,          // {structural, functional, causal, temporal}
}

struct GradientScores {
  fidelity_vec: [f32; 7],      // fidelity scores per context
  distance_vec: [f32; 7],      // distance scores per context
  consistency_coefficient: f32, // 1 - max(CV(fidelity), CV(distance))
}
```

ALGORITHM:
```python
def gradient_calibrated_score(analogy: Analogy, llm: Oracle) -> CalibratedScore:
    # Generate 7 evaluation contexts along orthogonal dimensions
    contexts = generate_prompt_gradient(analogy, n=7)
    
    fidelity_scores = []
    distance_scores = []
    
    for ctx in contexts:
        prompt = render_eval_prompt(analogy, ctx)
        f, d = llm.evaluate(prompt)  # returns fidelity, distance
        fidelity_scores.append(f)
        distance_scores.append(d)
    
    # Compute coefficient of variation for each signal
    cv_fidelity = std(fidelity_scores) / (mean(fidelity_scores) + 1e-6)
    cv_distance = std(distance_scores) / (mean(distance_scores) + 1e-6)
    
    # Consistency coefficient: low CV = high consistency = likely genuine
    # High CV = context-dependent = likely prior-optimized
    consistency = 1.0 - max(cv_fidelity, cv_distance)
    
    # Sigmoid mapping: consistency [0,1] -> discount [0.3, 1.0]
    # k=10 gives sharp transition around consistency=0.5
    discount = 0.3 + 0.7 * sigmoid(10 * (consistency - 0.5))
    
    # Base score uses original formula
    base_score = mean(fidelity_scores) * (mean(distance_scores) ** 1.5)
    
    # Final score applies consistency discount
    return CalibratedScore(
        raw=base_score,
        calibrated=base_score * discount,
        consistency=consistency,
        cv_fidelity=cv_fidelity,
        cv_distance=cv_distance
    )

def generate_prompt_gradient(analogy: Analogy, n: int = 7) -> List[EvalContext]:
    """Generate n contexts that vary orthogonally to analogy quality."""
    contexts = []
    for i in range(n):
        ctx = EvalContext(
            abstraction_level = i / (n - 1),  # 0.0 to 1.0
            vocabulary_set = rotate_vocab_mask(i, n),  # cycle through vocab subsets
            framing = FRAME_TYPES[i % len(FRAME_TYPES)]
        )
        contexts.append(ctx)
    return contexts
```

COMPLEXITY BOUNDS:
- Time: O(n × T_llm) where n=7 and T_llm is single LLM call latency
- Space: O(n × prompt_size) for storing gradient prompts
- Can be parallelized to O(T_llm) wall-clock time with n parallel calls

NUMERICAL EXAMPLE:
Consider two analogies being scored:

Analogy A (well-known: ACO → load balancing):
- Context 1 (concrete, structural): fidelity=0.91, distance=0.88
- Context 2 (abstract, functional): fidelity=0.72, distance=0.65
- Context 3 (concrete, causal): fidelity=0.89, distance=0.85
- Context 4 (abstract, temporal): fidelity=0.68, distance=0.61
- Context 5 (mixed, structural): fidelity=0.85, distance=0.82
- Context 6 (concrete, functional): fidelity=0.90, distance=0.87
- Context 7 (abstract, causal): fidelity=0.70, distance=0.63

mean_f=0.809, std_f=0.098, CV_f=0.121
mean_d=0.759, std_d=0.117, CV_d=0.154
consistency = 1 - 0.154 = 0.846
discount = 0.3 + 0.7 * sigmoid(10*(0.846-0.5)) = 0.3 + 0.7*0.969 = 0.978
base_score = 0.809 * 0.759^1.5 = 0.535
calibrated_score = 0.535 * 0.978 = 0.523

Analogy B (genuinely novel: coral symbiosis → score calibration):
- Context 1: fidelity=0.82, distance=0.93
- Context 2: fidelity=0.79, distance=0.91
- Context 3: fidelity=0.84, distance=0.94
- Context 4: fidelity=0.80, distance=0.90
- Context 5: fidelity=0.83, distance=0.92
- Context 6: fidelity=0.81, distance=0.93
- Context 7: fidelity=0.82, distance=0.91

mean_f=0.816, std_f=0.017, CV_f=0.021
mean_d=0.920, std_d=0.014, CV_d=0.015
consistency = 1 - 0.021 = 0.979
discount = 0.3 + 0.7 * sigmoid(10*(0.979-0.5)) = 0.3 + 0.7*0.992 = 0.994
base_score = 0.816 * 0.920^1.5 = 0.720
calibrated_score = 0.720 * 0.994 = 0.716

Result: Analogy B scores higher despite similar raw fidelity because its scores are CONSISTENT across evaluation contexts, indicating the model is discovering structure rather than recalling memorized associations.

FAILURE MODE AND RECOVERY:
Failure: If the LLM has seen an analogy so thoroughly that it has internalized the abstract structure (not just the surface mapping), scores will be consistent across contexts even for prior-known analogies.
Detection: Track historical CV distributions. If mean CV across all analogies drops below 0.05, the gradient is no longer discriminating.
Recovery: Increase gradient extremity — push abstraction_level to [0.0, 1.0] with steeper steps, use more exotic framing types, or add adversarial vocabulary constraints that force the model to reason from scratch.

### vs Conventional Baseline
BASELINE: Score = fidelity × distance^1.5, with hand-tuned penalties for observed anomalies. Problem: Both fidelity and distance are inflated together for prior-known analogies, so no combination of penalties on the final score can distinguish genuine from spurious. INVENTION: Score = mean(fidelity) × mean(distance)^1.5 × discount(CV), where CV is computed across a prompt gradient. Advantage: The prompt gradient creates a dimension of variation that is orthogonal to analogy quality but correlated with prior exposure. A genuinely novel analogy scores consistently across contexts; a prior-known analogy scores high only in contexts matching its training distribution. The variance signal is not available to the baseline.

---
