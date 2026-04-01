# Workspace Inventions for hephaestus

**Problems found:** 7
**Inventions attempted:** 3
**Inventions succeeded:** 3

## 1. Prosodic Commitment Gating

**Problem:** The 5-stage Genesis pipeline executes sequentially with no checkpointing, so any failure at stage 4 (Translate) or 5 (Verify) discards all prior expensive LLM work and forces a full restart from scratch.
**Source Domain:** Linguistic Semantics — Garden-Path Sentence Processing and Reanalysis
**Novelty Score:** 0.07
**Verdict:** INVALID

### Key Insight
The parser doesn't checkpoint its parse tree — it limits how deeply it commits before seeing confirming evidence. Similarly, don't checkpoint pipeline state; instead, structure computation into shallow (cheap to regenerate) and deep (expensive) layers, and validate the shallow layer before materializing the deep layer. This transforms catastrophic late-stage failure into cheap shallow-layer regeneration.

### Architecture
The Prosodic Commitment Gating architecture transforms the Genesis pipeline from a deep-commitment sequential process into a staged-commitment process with early disambiguation probes. The core insight is that we don't checkpoint state — we checkpoint commitment depth by inserting cheap 'prosodic boundaries' that validate viability before expensive materialization.

**Stage 1-2 (Concept + Abstract): Full Execution with Semantic Fingerprinting**
These stages are relatively cheap. Execute normally, but extract a 'semantic fingerprint' — a minimal representation capturing the structural essence of the generated concept. This fingerprint is not a checkpoint; it's a prosodic cue that subsequent stages use for predictive disambiguation. The fingerprint includes: (a) the abstract structural form, (b) key constraints identified, (c) domain distance metrics. Store this fingerprint in memory (not disk) as a lightweight coordination signal.

**Stage 3 (Score): Commitment Gate Alpha**
Before executing the full scoring stage, insert a 'prosodic probe' — a minimal LLM call (~5% of stage cost) that asks: 'Given this structural fingerprint, what is the probability this concept has a viable translation?' This is analogous to how readers use comma placement to predict whether a reduced relative clause is coming. If probe returns <0.3 viability, abort early and regenerate from Stage 1 with modified parameters. The probe doesn't checkpoint — it prevents deep commitment to doomed paths.

**Stage 4 (Translate): Speculative Execution with Shallow Attachment**
Here's the key architectural innovation. Instead of generating a single deep translation, generate a 'prosodic phrase' — a translation skeleton with explicitly marked commitment boundaries. The skeleton contains: (a) the structural mapping (high confidence, cheap to regenerate), (b) the architecture outline (medium confidence), (c) implementation details (low confidence, expensive). The skeleton uses special markers [SHALLOW] and [DEEP] to indicate commitment depth. Only [SHALLOW] sections are fully materialized; [DEEP] sections remain as structured prompts that can be regenerated cheaply.

**Pre-Stage 5: Commitment Gate Beta (The Critical Innovation)**
Before full Verify execution, run a 'disambiguation probe' — a cheap validation (~10% of Verify cost) that tests only the [SHALLOW] skeleton against core verification criteria. This probe asks: 'Does this structural mapping have fatal flaws?' and 'Is the mathematical proof shape coherent?' If the probe fails, we only discard the [DEEP] sections and regenerate them with the probe's feedback incorporated into the prompt. The [SHALLOW] skeleton survives because it was never deeply committed. This is exactly how prosodic phrasing prevents garden-path reanalysis — by limiting commitment depth at ambiguity points.

**Stage 5 (Verify): Staged Materialization**
Only after Gate Beta passes do we fully materialize the [DEEP] sections. Verification now operates on a structure that has already passed shallow validation. If Verify fails at this point, the failure feedback is specific enough to guide targeted regeneration of only the failed [DEEP] components, not the entire pipeline.

**Implementation Data Structures**
```python
@dataclass
class ProsodicSkeleton:
    semantic_fingerprint: dict  # Lightweight coordination signal
    shallow_sections: dict      # High-confidence, cheap to regenerate
    deep_prompts: dict          # Structured prompts, not materialized content
    commitment_markers: list    # [SHALLOW] and [DEEP] boundary positions
    probe_results: list         # Results from Gates Alpha and Beta

def commitment_gate(skeleton: ProsodicSkeleton, gate_type: str) -> tuple[bool, str]:
    """Run prosodic probe to test viability before deep commitment."""
    probe_prompt = build_probe_prompt(skeleton, gate_type)
    result = llm_call(probe_prompt, max_tokens=200)  # Cheap probe
    viability = parse_viability(result)
    return (viability > THRESHOLD[gate_type], result.feedback)

def staged_translate(concept: Concept) -> ProsodicSkeleton:
    """Generate translation skeleton with explicit commitment boundaries."""
    skeleton = ProsodicSkeleton()
    skeleton.shallow_sections = generate_mapping_and_outline(concept)  # Cheap
    skeleton.deep_prompts = prepare_implementation_prompts(skeleton)   # Deferred
    skeleton.commitment_markers = identify_ambiguity_points(skeleton)
    return skeleton

def materialize_deep(skeleton: ProsodicSkeleton, feedback: str = None) -> Translation:
    """Only called after Gate Beta passes. Materializes deferred sections."""
    for section_key in skeleton.deep_prompts:
        prompt = skeleton.deep_prompts[section_key]
        if feedback:
            prompt = incorporate_feedback(prompt, feedback)
        skeleton.shallow_sections[section_key] = llm_call(prompt)
    return Translation.from_skeleton(skeleton)
```

### How to Implement in This Codebase
To implement this in hephaestus:
1. Identify the components in the codebase that relate to: The 5-stage Genesis pipeline executes sequentially with no checkpointing, so any failure at stage 4 
2. Apply the architectural pattern described above
3. Start with a minimal prototype of the core mechanism
4. Wire it into the existing architecture incrementally

---

## 2. Hyphal Diameter Lens Selector

**Problem:** The 80+ domain lenses are static YAML axiom sets with no feedback loop — there is no mechanism to learn which lenses consistently produce high-novelty, high-fidelity inventions and which produce low-scoring matches, so lens selection remains uniformly random across domains regardless of accumulated run history.
**Source Domain:** Fungal Networks — Adaptive Hyphal Resource Allocation in Phanerochaete velutina
**Novelty Score:** 0.07
**Verdict:** DERIVATIVE

### Key Insight
The fungal network has no memory system separate from its physical structure — the tube diameters ARE the memory. By making selection probability proportional to diameter^4 (matching actual fluid dynamics in hyphae), we embed the entire learning algorithm into a single emergent property: wider tubes carry more flow. There is no bandit, no controller, no weight update rule to tune. The network's architecture IS the policy, and it restructures itself through the same mechanism that selects from it.

### Architecture
The system maintains a 'mycelium state file' (JSON or SQLite) that stores, for each lens, exactly three values: current_diameter (float), invocation_count (int), and last_invoked_run (int). On system initialization, all lenses start with diameter = 1.0, representing uniform exploratory growth.

Lens selection proceeds as follows: (1) Load all lens diameters. (2) For lenses with invocation_count < MIN_SAMPLES (e.g., 5), temporarily inflate diameter by EXPLORATION_BOOST (e.g., 2.0×). (3) Compute selection weights as diameter^4 for each lens. (4) Normalize to probability distribution. (5) Sample lens from this distribution. The fourth-power relationship is critical — it comes directly from the Hagen-Poiseuille equation for laminar flow through tubes, where volumetric flow rate scales with radius^4. This creates strong preferential attachment to high-diameter lenses without requiring explicit exploitation logic.

After invention scoring, the feedback loop executes: (1) Retrieve the lens's current diameter. (2) If score > HIGH_THRESHOLD (e.g., 0.7), set diameter = min(diameter + Δ_GROW, MAX_DIAMETER). (3) If score < LOW_THRESHOLD (e.g., 0.3), set diameter = max(diameter - Δ_SHRINK, MIN_DIAMETER). (4) Scores in the middle band cause no diameter change — this is the 'maintenance zone' where the pathway is sustained but not reinforced. (5) Increment invocation_count. (6) Write state back.

The passive decay mechanism runs every DECAY_INTERVAL runs (e.g., every 100 runs): all lens diameters are multiplied by (1 - DECAY_RATE), e.g., 0.99. This ensures that lenses which were once productive but have not been invoked recently will gradually constrict, freeing 'flow capacity' for currently active pathways. It also means a lens that performed well 1000 runs ago but has been dormant will have decayed significantly, preventing stale lock-in.

The MIN_DIAMETER floor (e.g., 0.1) ensures no lens ever reaches zero probability. This is biologically accurate — fungi maintain minimal hyphal connections even to poor resources, enabling rapid re-expansion if conditions change. In the system, this means every lens retains at least (0.1)^4 / Σ(diameters^4) selection probability, ensuring eventual re-exploration.

Implementation pseudocode for selection:
```
def select_lens(mycelium_state, current_run):
    diameters = []
    for lens_id, state in mycelium_state.items():
        d = state['diameter']
        if state['invocation_count'] < MIN_SAMPLES:
            d *= EXPLORATION_BOOST
        diameters.append((lens_id, d ** 4))
    
    total = sum(w for _, w in diameters)
    probs = [(lid, w / total) for lid, w in diameters]
    return weighted_random_choice(probs)
```

Implementation pseudocode for feedback:
```
def update_diameter(mycelium_state, lens_id, score, current_run):
    state = mycelium_state[lens_id]
    if score > HIGH_THRESHOLD:
        state['diameter'] = min(state['diameter'] + DELTA_GROW, MAX_DIAMETER)
    elif score < LOW_THRESHOLD:
        state['diameter'] = max(state['diameter'] - DELTA_SHRINK, MIN_DIAMETER)
    state['invocation_count'] += 1
    state['last_invoked_run'] = current_run
```

Implementation pseudocode for decay:
```
def apply_decay(mycelium_state, current_run):
    if current_run % DECAY_INTERVAL == 0:
        for state in mycelium_state.values():
            state['diameter'] = max(state['diameter'] * (1 - DECAY_RATE), MIN_DIAMETER)
```

### How to Implement in This Codebase
To implement this in hephaestus:
1. Identify the components in the codebase that relate to: The 80+ domain lenses are static YAML axiom sets with no feedback loop — there is no mechanism to le
2. Apply the architectural pattern described above
3. Start with a minimal prototype of the core mechanism
4. Wire it into the existing architecture incrementally

---

## 3. Selectional Grammar Harness

**Problem:** The DeepForge anti-consensus harness applies cognitive interference uniformly across all problem types and intensity levels, with no structural model of which interference patterns are effective for which problem shapes — making the 'anti-training pressure' mechanism empirically unvalidated and potentially self-defeating for certain problem classes.
**Source Domain:** Linguistics — Syntactic Structure: Early Generative Grammar (Pre-Transformational)
**Novelty Score:** 0.09
**Verdict:** INVALID

### Key Insight
Problems have deep structure that is invisible on their surface, and interference must respect selectional restrictions — constraints on which perturbation types are compatible with which problem features. By parsing problems into constituency trees, annotating with features, and leaving traces when interference applies, the system makes the interference-outcome relationship structurally visible without building explicit feedback loops. The novelty module can decompose its scores by trace, revealing which interference rules contributed to novelty versus degradation, because the traces are embedded in the representation itself — just as syntactic traces allow distant elements to be interpreted in relation to their original position.

### Architecture
The Selectional Grammar Harness replaces uniform interference injection with a three-phase architecture: PARSE, SELECT, TRACE.

**PHASE 1: PARSE** — Problem Constituency Analysis
Every incoming problem is parsed into a constituency tree using a problem grammar. The grammar is defined as:
```
PROBLEM → DOMAIN CONSTRAINTS SOLUTION_SPACE
DOMAIN → ENTITIES RELATIONS
CONSTRAINTS → HARD_CONSTRAINTS SOFT_CONSTRAINTS
SOLUTION_SPACE → DISCRETE | CONTINUOUS | HYBRID
```
The parser annotates each node with binary feature bundles: [±abstract], [±overconstrained], [±compositional], [±temporal], [±adversarial]. This is not ML classification — it is rule-based feature extraction from problem structure. For example, presence of quantifiers over time → [+temporal]; presence of competing agents → [+adversarial].

**PHASE 2: SELECT** — Selectional Restriction Matching
The interference rule inventory is annotated with selectional restrictions. Each rule specifies which feature combinations it is compatible with:
```python
INTERFERENCE_RULES = {
  'temperature_spike': {'selects': ['+abstract', '-overconstrained'], 'level': 'PROBLEM'},
  'constraint_relaxation': {'selects': ['+overconstrained'], 'level': 'CONSTRAINTS'},
  'entity_substitution': {'selects': ['+compositional'], 'level': 'ENTITIES'},
  'temporal_inversion': {'selects': ['+temporal'], 'level': 'RELATIONS'},
  'adversarial_flip': {'selects': ['+adversarial'], 'level': 'SOLUTION_SPACE'},
}
```
The SELECT phase performs unification: for each node in the problem tree, find all rules whose selectional restrictions unify with the node's features. This produces a *licensed interference set* for the problem — the rules that are structurally compatible.

**PHASE 3: TRACE** — Provenance-Preserving Application
When an interference rule applies, it does not simply transform the problem; it leaves a *trace* at the application site. The trace is a lightweight marker: `(t_i, rule_id, node_path, timestamp)`. These traces are embedded in the problem representation itself, not in external telemetry.

The novelty/ module, when scoring output, receives the traced problem representation. It extracts the trace chain and computes a *trace-conditioned novelty score*: `novelty(output | traces)`. This score is decomposed by trace, producing a per-rule novelty contribution without explicit feedback loop infrastructure.

The key mechanism: traces create *long-distance dependencies* between interference application and novelty scoring. The novelty module doesn't need to query the harness; the information is structurally present in the representation, just as traces in syntax allow distant elements to be interpreted in relation to their base position.

**CONVERGENCE INTEGRATION**
The convergence/ module monitors whether the solution is approaching consensus. When convergence is detected, it broadcasts a *movement trigger* — analogous to wh-movement in syntax. This trigger causes the harness to apply *displacement rules*: move a constraint from its base position to a higher scope position, changing the problem's interpretation. The original position retains a trace, ensuring the transformation is recoverable.

**GRAMMAR EVOLUTION** (non-ML)
The selectional restrictions are not learned but *parameterized*. The system maintains a small set of binary parameters (analogous to UG parameters). Engineers can flip parameters to produce different interference grammars:
- [+aggressive]: interference applies at PROBLEM level by default
- [+conservative]: interference applies at leaf level only
- [+compositional]: interference rules can recursively embed

Parameter settings are versioned and can be A/B tested at the grammar level, not the individual rule level — reducing the search space from exponential to linear in the number of parameters.

### How to Implement in This Codebase
To implement this in hephaestus:
1. Identify the components in the codebase that relate to: The DeepForge anti-consensus harness applies cognitive interference uniformly across all problem typ
2. Apply the architectural pattern described above
3. Start with a minimal prototype of the core mechanism
4. Wire it into the existing architecture incrementally

---
