# Workspace Inventions for hephaestus

**Problems found:** 7
**Inventions attempted:** 2
**Inventions succeeded:** 2

## 1. Phase-Transition State Crystallization with Relational Identity Verification

**Problem:** The 5-stage Genesis pipeline executes sequentially with no intermediate result caching, so any stage failure forces a full re-run from scratch at ~$1.25 per attempt, with no way to resume from the last successful stage.
**Source Domain:** Art — Color Theory: Glazing Technique in Oil Painting
**Novelty Score:** 0.02
**Verdict:** QUESTIONABLE

### Key Insight
State identity for resumption should be determined by functional equivalence under a lossy projection, not by exact content match—this allows valid cache hits across environmentally-varied executions while the multi-channel verification prevents invalid resumptions

### Architecture
The pipeline maintains a StateManifold structure that stores not raw outputs but crystallized projections of each stage's result. When stage S_i completes, its output undergoes crystallization: a transformation that extracts the functionally-relevant subset of the output and computes a signature tuple (content_projection, predecessor_context_hash, execution_invariants). The content_projection is a lossy compression—it captures what matters for downstream stages while discarding execution-specific noise like timestamps, random seeds, or API response metadata.

The crystallization process uses opponent encoding: each stage output is decomposed into antagonistic channels that capture orthogonal dimensions of the result. For the Decompose stage, this might be (structural_complexity, semantic_density); for Search, (relevance_signal, coverage_breadth); for Score, (confidence_magnitude, uncertainty_spread). These opponent pairs cannot both be maximized simultaneously—they encode genuine tradeoffs in the computation. The crystallized signature is the tuple of opponent channel values.

When resuming execution, the system performs context-relative verification. It does not simply check 'does a cached result exist for this input hash.' Instead, it reconstructs what the current execution context would expect from the previous stage, then asks: 'does the crystallized state's signature match what I would accept as valid input?' This discounts environmental drift—if the LLM API returns slightly different formatting, or if configuration parameters changed in ways that don't affect downstream semantics, the system recognizes functional equivalence.

The verification uses a three-channel comparison: (1) structural_channel: does the cached output have the expected shape and required fields? (2) semantic_channel: does the content_projection fall within acceptable bounds for this problem class? (3) provenance_channel: is the predecessor_context_hash compatible with the current pipeline configuration? All three channels must pass for resumption; failure in any channel triggers re-execution from that stage.

Crystallized states are stored in a manifold indexed by (problem_signature, stage_index, context_invariant_hash). The problem_signature uses metameric hashing: different problem formulations that would produce functionally identical pipeline behavior map to the same signature. This enables cache hits across semantically equivalent but syntactically different inputs.

When a stage fails, the system walks backward through the manifold to find the most recent crystallized state that passes context-relative verification. It then re-executes only from that point forward. If the Verify stage fails an adversarial check, the system checks whether the Translate output's crystallized signature indicates the failure was due to translation quality (re-run Translate) or scoring quality (re-run from Score). The opponent channels encode enough information to localize failure causation without full re-execution.

### How to Implement in This Codebase
To implement this in hephaestus:
1. Identify the components in the codebase that relate to: The 5-stage Genesis pipeline executes sequentially with no intermediate result caching, so any stage
2. Apply the architectural pattern described above
3. Start with a minimal prototype of the core mechanism
4. Wire it into the existing architecture incrementally

---

## 2. Contrastive Structure Matching with Explanation-Type Priors

**Problem:** Domain lens selection during Search is static enumeration across all 80+ YAML lenses with no learned feedback loop, so the engine cannot improve domain-to-problem-shape matching over time despite accumulating a growing corpus of successful and failed invention runs.
**Source Domain:** Philosophy of Science — Inference to the Best Explanation (Abductive Reasoning)
**Novelty Score:** 0.05
**Verdict:** QUESTIONABLE

### Key Insight
Selection improves not by learning which operators work for which input types, but by learning which operators resolve which types of differences between structurally similar inputs — the contrastive structure of the selection problem is the true learning target.

### Architecture
The system maintains a Contrastive Index alongside the lens registry. When a new problem arrives at Search, it is not matched against lenses directly. Instead, the system computes its contrastive signature: what structural features distinguish this problem from its k-nearest neighbors in the historical problem embedding space?

Data structures: (1) ProblemEmbeddingIndex: vector store of past problem embeddings with associated run metadata. (2) ContrastiveSignatureCache: for each lens, a sparse vector of (contrast-feature → reward-differential) accumulated over all runs where that lens was applied. (3) LensContrastMatrix: a |lenses| × |contrast-features| matrix where entry [l, c] = mean reward differential when lens l was applied to problems exhibiting contrast-feature c.

Selection algorithm:
```
def select_lenses(problem_embedding, k_neighbors=5, top_n=10):
    # Step 1: Find structurally similar past problems
    neighbors = ProblemEmbeddingIndex.query(problem_embedding, k=k_neighbors)
    
    # Step 2: Compute contrastive signature
    contrast_features = {}
    for neighbor in neighbors:
        diff = compute_structural_diff(problem_embedding, neighbor.embedding)
        for feature, magnitude in diff.items():
            contrast_features[feature] = max(contrast_features.get(feature, 0), magnitude)
    
    # Step 3: Score lenses by contrastive match
    lens_scores = {}
    for lens in all_lenses:
        score = 0
        for feature, magnitude in contrast_features.items():
            score += magnitude * LensContrastMatrix[lens.id, feature]
        lens_scores[lens] = score
    
    # Step 4: Return top-scoring lenses, with exploration bonus for untested contrasts
    return sorted(lens_scores.items(), key=lambda x: x[1], reverse=True)[:top_n]
```

Feedback integration: After each run completes with a novelty score, the system updates the ContrastiveSignatureCache:
```
def update_contrastive_model(problem_embedding, lens_used, novelty_score):
    neighbors = ProblemEmbeddingIndex.query(problem_embedding, k=5)
    baseline = mean([n.best_novelty_score for n in neighbors])
    reward_differential = novelty_score - baseline
    
    contrast_features = compute_structural_diff(problem_embedding, centroid(neighbors))
    for feature, magnitude in contrast_features.items():
        LensContrastMatrix[lens_used.id, feature] += learning_rate * magnitude * reward_differential
    
    ProblemEmbeddingIndex.add(problem_embedding, lens_used, novelty_score)
```

The critical difference from baseline approaches: we do not learn 'lens L works for problem-type P'. We learn 'lens L resolves contrast-type C'. A problem that looks similar to past problems but differs in specific structural ways will be matched to lenses that historically resolved those specific differences, not lenses that worked on the similar problems.

### How to Implement in This Codebase
To implement this in hephaestus:
1. Identify the components in the codebase that relate to: Domain lens selection during Search is static enumeration across all 80+ YAML lenses with no learned
2. Apply the architectural pattern described above
3. Start with a minimal prototype of the core mechanism
4. Wire it into the existing architecture incrementally

---
