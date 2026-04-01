# Workspace Inventions for hephaestus

**Problems found:** 7
**Inventions attempted:** 2
**Inventions succeeded:** 2

## 1. Circle-Take Pipeline with Dailies Buffer

**Problem:** The 5-stage invention pipeline executes sequentially with no feedback loops between stages, meaning poor decompositions propagate silently through all downstream stages without correction.
**Source Domain:** Film Cinematography — Dailies Review and Circle Takes System
**Novelty Score:** 0.05
**Verdict:** QUESTIONABLE

### Key Insight
The pipeline's apparent feedforward nature is an illusion caused by immediate commitment. By preserving stage preconditions (keeping the set standing) and flowing uncertainty metadata forward (circle takes), we create a temporal depth of field where the pipeline hasn't fully committed until the Dailies phase explicitly releases preconditions. This transforms terminal validation from a dead-end into a selective rewind point.

### Architecture
The pipeline transforms from Decompose→Search→Score→Translate→Verify into a two-phase architecture: a **Production Phase** that executes the full pipeline while accumulating metadata, and a **Dailies Phase** that analyzes failures and issues selective recomputation directives.

**Production Phase Data Structures:**
Each stage emits a `TakeBundle` rather than a raw output:
```python
@dataclass
class TakeBundle:
    stage_id: str
    output: Any
    input_snapshot: Any  # frozen copy of input received
    parameters: dict  # prompts, model params, etc.
    preconditions: PreconditionSet  # what's needed to re-execute
    circle_marks: List[CircleMark]  # uncertainty annotations
    precondition_valid_until: Optional[str]  # stage that invalidates these

@dataclass  
class CircleMark:
    dimension: str  # e.g., 'constraint_coverage', 'domain_relevance'
    confidence: float  # 0-1
    alternative_considered: Optional[str]  # what else was almost chosen
```

The `PreconditionSet` for each stage captures what's needed for re-execution:
- **Decompose**: original problem text, any retrieved context, embedding model state
- **Search**: structural form, domain corpus snapshot hash, search parameters
- **Score**: candidate list, scoring rubric version
- **Translate**: selected candidate, target domain context
- **Verify**: translation output, verification criteria

**Production Phase Execution:**
The pipeline executes normally but each stage:
1. Receives input from previous stage's TakeBundle.output
2. Executes its transformation
3. Self-annotates with CircleMarks (e.g., Decompose might mark `{dimension: 'constraint_extraction', confidence: 0.6, alternative_considered: 'cost constraint was ambiguous'}`)
4. Emits TakeBundle to a DailiesBuffer (append-only log)
5. Passes output to next stage

**Dailies Phase (triggered after Verify):**
```python
def dailies_review(buffer: DailiesBuffer, verify_result: VerifyResult) -> Optional[RecomputeDirective]:
    if verify_result.success:
        buffer.commit()  # finalize, release preconditions
        return None
    
    # Correlate failure mode with upstream circle marks
    failure_dimensions = verify_result.failure_analysis()  # e.g., ['structural_mismatch', 'constraint_violation']
    
    for stage_bundle in reversed(buffer.bundles):  # walk backward
        for mark in stage_bundle.circle_marks:
            if correlates(mark.dimension, failure_dimensions):
                # Found the likely source
                if stage_bundle.preconditions.still_valid():
                    return RecomputeDirective(
                        stage=stage_bundle.stage_id,
                        dimension=mark.dimension,
                        guidance=mark.alternative_considered,
                        reuse_downstream=compute_reusable_stages(buffer, stage_bundle)
                    )
    
    # No correlation found or preconditions expired
    return RecomputeDirective(stage='Decompose', full_restart=True)
```

**Selective Recomputation with Consistency Checking:**
When a RecomputeDirective targets stage k:
1. Retrieve stage k's PreconditionSet from buffer
2. Re-execute stage k with modified parameters (guided by `guidance` field)
3. **Consistency check**: Compare new output's structural signature with cached downstream inputs. If Search cached results depend on Decompose's structural form, verify the new form is compatible or mark Search for re-execution.
4. For stages marked reusable, verify their inputs haven't structurally changed
5. Execute only invalidated downstream stages

**Cost Optimization:**
The system maintains a `RecomputationBudget`. Each directive has an estimated cost (stages to re-execute × stage cost). The Dailies phase can:
- Attempt cheapest fixes first (recompute only Score with different weights)
- Escalate to more expensive recomputations if cheap fixes fail
- Abandon after budget exhaustion

**Precondition Lifecycle:**
Preconditions are memory-intensive. The system uses a tiered approach:
- Hot: Full preconditions for most recent pipeline run (in memory)
- Warm: Preconditions for last N runs (on disk, quick restore)
- Cold: Only output hashes (preconditions released, full restart required)

### How to Implement in This Codebase
To implement this in hephaestus:
1. Identify the components in the codebase that relate to: The 5-stage invention pipeline executes sequentially with no feedback loops between stages, meaning 
2. Apply the architectural pattern described above
3. Start with a minimal prototype of the core mechanism
4. Wire it into the existing architecture incrementally

---

## 2. Phenotypic Field-Memory Selector

**Problem:** The domain lens library is a static YAML corpus with no runtime feedback mechanism, so lenses that consistently produce low-novelty or low-fidelity matches are never down-weighted and lenses that produce high-value inventions are never amplified.
**Source Domain:** Agriculture — Traditional Seed Selection and Landraces
**Novelty Score:** 0.05
**Verdict:** QUESTIONABLE

### Key Insight
The agricultural insight is that performance feedback must be contextualized by field position (problem structure) and season phase (session timing) — a seed that thrives in wet soil fails in dry soil, and a lens that excels early in ideation may produce redundant candidates late. Contextual memory, not aggregate statistics, is what transforms mass selection into phenotypic selection.

### Architecture
The system maintains a 'Field Memory' data structure — a sparse tensor indexed by three dimensions: (lens_id, structure_hash, session_phase). Each cell contains a 'phenotypic record': {score_sum, score_count, last_updated_timestamp, rotation_debt}. The structure_hash is computed from the problem's abstract structural form using a locality-sensitive hash that groups structurally similar problems.

At lens selection time, the selector computes a 'planting probability' for each lens. First, it retrieves all phenotypic records matching the current problem's structure_hash (with fuzzy matching to nearby hashes). For each lens, it computes an 'affinity score' = (score_sum / score_count) * recency_weight(last_updated) * (1 + rotation_debt). Lenses with no records for this structure receive a 'virgin soil bonus' — elevated probability to ensure exploration of untested pairings.

The rotation_debt accumulates when a lens is not selected: each selection round increments rotation_debt for all non-selected lenses by 0.1. When a lens is selected, its rotation_debt resets to 0. This implements the crop rotation principle — lenses that haven't been 'planted' recently accumulate pressure to be selected, preventing monoculture lock-in.

Session phase is tracked as a discrete variable: 'early' (first 20% of candidates generated), 'mid' (20-60%), 'late' (60-100%). Performance is recorded separately for each phase, allowing the system to learn that some lenses are 'early season performers' (good for initial exploration) while others are 'late season performers' (good for refinement once obvious solutions are exhausted).

After scoring, the system performs 'harvest marking': it writes back to the Field Memory the lens_id, structure_hash, session_phase, and score. Critically, it also records 'neighbor contamination' — if a lens produces a high score, nearby lenses in the domain-distance graph receive a smaller positive signal (simulating pollen drift / genetic similarity). This creates clusters of related high-performing lenses rather than isolated peaks.

The Field Memory is persisted as a SQLite database with three tables: phenotypic_records (the main tensor), structure_signatures (cached structure hashes with their source problems for debugging), and rotation_ledger (tracking rotation_debt across sessions). On startup, loader.py reads the rotation_ledger and phenotypic_records to reconstruct selection probabilities.

### How to Implement in This Codebase
To implement this in hephaestus:
1. Identify the components in the codebase that relate to: The domain lens library is a static YAML corpus with no runtime feedback mechanism, so lenses that c
2. Apply the architectural pattern described above
3. Start with a minimal prototype of the core mechanism
4. Wire it into the existing architecture incrementally

---
