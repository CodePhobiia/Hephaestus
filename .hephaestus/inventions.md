# Workspace Inventions for Hephaestus

**Problems found:** 7
**Inventions attempted:** 5
**Inventions succeeded:** 5

---

## 1. Immune-Cascade Pipeline Recovery

**Problem:** The genesis pipeline runs 5 stages sequentially, and a failure in Stage 3 (Score) discards all work from Stages 1-2. There's a `core/recovery.py` with checkpointing, but it's not wired into the actual pipeline — genesis.py has no try/catch around individual stages, so a single API timeout kills the entire run.

**Category:** reliability | **Severity:** high

**Source Domain:** Immune System — Complement Cascade
**Novelty Score:** 0.87
**Verdict:** NOVEL

### Key Insight
The complement cascade in immunology operates as a sequential amplification chain, but each stage deposits stable "opsonization markers" on the target. If the cascade is interrupted, earlier markers remain functional — downstream components can re-attach to existing markers and resume without restarting from scratch. The cascade is resumable by design because each stage produces a stable, self-describing intermediate.

### Architecture
Each pipeline stage writes a structured `StageResult` to the session before proceeding. The `StageResult` contains enough information for the next stage to start cold (problem structure, candidates, scored list, translations). When an error occurs, the pipeline catches it, records a `PipelineCheckpoint`, and offers three paths: (1) retry the failed stage, (2) skip to the next stage using partial data, (3) return the best result so far. On resume, the pipeline reads the last checkpoint and restarts from the failed stage, not from scratch.

### How to Implement in This Codebase
1. Wrap each stage in `invent_stream()` (genesis.py lines ~430-550) with a try/except that captures the `PipelineCheckpoint` from `core/recovery.py`
2. Before each stage, check for an existing checkpoint in the session and skip completed stages
3. After each stage, write the intermediate result to the `Session` transcript as an `EntryType.CHECKPOINT` entry
4. Add a `/resume` REPL command that loads the last checkpoint and restarts the pipeline

---

## 2. Mycelial Lens Selection Network

**Problem:** Lens selection in `lenses/selector.py` scores each lens independently against the problem structure. But lenses from related domains (e.g., "biology_chemotaxis" and "biology_quorum_sensing") often produce near-identical candidates, wasting search budget. The `core/diversity.py` module exists but isn't integrated into the search stage — it only operates post-hoc on results.

**Category:** performance | **Severity:** high

**Source Domain:** Mycology — Mycelial Networks
**Novelty Score:** 0.84
**Verdict:** NOVEL

### Key Insight
Mycelial networks (fungal root systems) solve a strikingly similar resource allocation problem: they must explore soil for nutrients using limited growth budget, and they must avoid sending multiple hyphae to the same nutrient pocket. They do this through chemical inhibition zones — when one hypha colonizes an area, it secretes compounds that redirect nearby hyphae elsewhere. The network explores maximally with minimal redundancy.

### Architecture
After the `LensSelector` scores all lenses, apply a "mycelial inhibition pass" before selecting the final lens set:
1. Score all lenses normally (existing behavior)
2. Sort by composite score descending
3. Select the top lens. Mark its domain family as "colonized"
4. For each subsequent lens, compute domain overlap with all colonized families. Apply a diversity penalty proportional to overlap (using the existing `compute_text_similarity` from `core/diversity.py`)
5. Re-sort after penalties. Select the next lens. Mark its family. Repeat.

This guarantees the search budget is spread across maximally diverse domains without losing high-quality candidates.

### How to Implement in This Codebase
1. In `lenses/selector.py`, after `score_lenses()` returns scores, apply `apply_diversity_rerank()` from `core/diversity.py` using the lens domain + axioms as the text comparator
2. The `domain_family` field already exists on lenses — use it for the inhibition zone grouping
3. The `diversity_weight` field in `LensScore` is already plumbed through but currently unused in the search stage — wire it

---

## 3. Tidal-Lock Adapter Failover

**Problem:** The pipeline uses separate adapters for each stage (decompose=Anthropic, search=OpenAI, etc.). But if one provider goes down mid-run, the pipeline crashes entirely. There's no failover — the `cross_model.py` module maps preset names to fixed model strings. The `retry.py` module retries the same adapter, but never switches providers.

**Category:** reliability | **Severity:** high

**Source Domain:** Planetary Science — Tidal Locking
**Novelty Score:** 0.81
**Verdict:** NOVEL

### Key Insight
Tidal locking in planetary mechanics is a stabilization phenomenon: a body that loses rotational freedom relative to one gravitational partner automatically redirects its stable face toward the dominant force. The key insight is that the "lock" happens naturally when one force dominates — and the body's response is to minimize energy by aligning with whatever pull is strongest. Applied to adapters: when the primary provider fails, the system should gravitationally "lock" to the next-strongest available provider without explicit routing logic.

### Architecture
Extend `cross_model.py` with a `ModelFallbackChain`:
```
chain = ModelFallbackChain([
    ("anthropic", "claude-opus-4-6"),
    ("openai", "gpt-5"),
    ("openrouter", "anthropic/claude-opus-4-6"),
])
```
Each adapter call wraps in a try/except. On provider failure, the chain automatically advances to the next provider. On success, it "locks" to the working provider for subsequent calls to the same stage (avoiding unnecessary provider hops). If all providers fail, it raises with a combined error message showing which providers were tried.

### How to Implement in This Codebase
1. Add `ModelFallbackChain` class to `core/cross_model.py`
2. In `genesis.py` `_ensure_built()`, construct chains instead of single adapters for each stage
3. Wrap adapter instantiation in the chain — each entry lazily constructs its adapter only when tried
4. Log which provider was used for each stage in the `InventionReport`

---

## 4. Crystallographic Context Compaction

**Problem:** Session compaction in `session/compact.py` uses a simple strategy: keep the last N entries, summarize everything older into a single text block. But the summary loses structural information — which inventions were explored, which domains were tried and rejected, which refinement constraints were applied. After compaction, the model loses its working memory of what NOT to try again.

**Category:** architecture | **Severity:** medium

**Source Domain:** Crystallography — Lattice Compression
**Novelty Score:** 0.79
**Verdict:** NOVEL

### Key Insight
Crystallographic compression preserves the symmetry group of a crystal even when reducing its representation. A 3D crystal can be described by its full unit cell (expensive) or by its space group + asymmetric unit (compact but lossless for the structural information that matters). The principle: compress by identifying the symmetry, then store only the irreducible representation plus the symmetry operators needed to reconstruct the full structure.

### Architecture
Replace the single summary text with a structured `CompactionCrystal`:
```python
@dataclass
class CompactionCrystal:
    explored_domains: list[str]        # domains already tried
    rejected_candidates: list[str]     # candidates that failed verification
    active_constraints: list[str]      # user refinement constraints
    best_invention_snapshot: dict      # key fields of current best
    anti_memory_additions: list[str]   # new exclusions from this session
    turn_count: int                    # how many turns were compacted
    original_summary: str              # human-readable summary (existing)
```
When the model receives this crystal after compaction, it can reconstruct what matters: what to avoid, what worked, and what constraints are active — without re-reading the full transcript.

### How to Implement in This Codebase
1. Extend `CompactionSummary` in `session/compact.py` to include structured fields
2. In `build_continuation_summary()`, extract domain names, constraint text, and rejection reasons from the entries being compacted
3. Format the crystal as a structured section in the continuation prompt
4. Feed the crystal back to the model alongside the text summary

---

## 5. Quorum-Sensing Convergence Breaker

**Problem:** The `convergence/tracker.py` detects when repeated runs converge on similar solutions and warns the user. But it only detects — it doesn't break the convergence. The user has to manually change parameters (depth, intensity, domain hint). The system should automatically perturb its own parameters to escape local optima.

**Category:** architecture | **Severity:** medium

**Source Domain:** Microbiology — Quorum Sensing
**Novelty Score:** 0.83
**Verdict:** NOVEL

### Key Insight
Bacterial quorum sensing uses autoinducer molecules to coordinate collective behavior. When population density exceeds a threshold, the accumulated signal triggers a phase transition — the colony switches from individual exploration to collective action. Crucially, some species use *quorum quenching* enzymes to deliberately degrade the signal and PREVENT premature convergence, keeping the colony in exploration mode longer. The counter-signal is as important as the signal.

### Architecture
When `ConvergenceTracker.check()` detects convergence:
1. **Quench the dominant domain**: add the ceiling domain to anti-memory exclusions for the next run
2. **Boost divergence**: temporarily increase `divergence_intensity` by one level (STANDARD→AGGRESSIVE, AGGRESSIVE→MAXIMUM)
3. **Inject a random lens**: force-select one lens from an underrepresented domain family
4. **Log the perturbation**: record what was changed so the user can see why results shifted

This creates an automatic "exploration vs exploitation" balance — the system converges until convergence is detected, then automatically perturbs itself to explore new territory.

### How to Implement in This Codebase
1. In the REPL pipeline runner (after each invention), call `tracker.check()`
2. If converging, call a new `auto_perturb(state, signal)` function that modifies `SessionState` in-place
3. Show a notice: "[dim]Convergence detected — auto-perturbing: excluded {domain}, boosted intensity[/]"
4. After one perturbed run, reset parameters to user defaults

---

*Generated by Hephaestus workspace analysis on 2026-04-01*
