# Configuration Contract: Genesis & DeepForge Settings

This document dictates exactly how configurable variables affect the Hephaestus runtime. All implementation vectors (CLI, API, UI) must map directly to this contract.

## Primary Generation Knobs

### 1. `depth` (integer, ranges 1-10)
`depth` controls the exploration budget and computational scale. It strictly indexes the `DepthPolicyTable`. It is **NOT** simply an alias for pressure rounds.
* **Standard Mode Budget:** Determines `search_candidates`, `search_branching_loops`, `recomposition_ceiling`. `translate_pressure_rounds` is strictly `0`.
* **Forge Mode Budget:** Determines `search_candidates`, scales `translate_permutations`, and executes ACTUAL `translate_pressure_rounds` corresponding directly to iterations > 0.
* **No ad-hoc multipliers** exist outside `DepthPolicyTable`.

### 2. `exploration_mode` (string)
* `"standard"`: Proceeds deterministically via linear pass. DeepForge pressure is skipped.
* `"forge"`: Injects active interference (`AntiTrainingPressure`). Requires multiple model iterations per translated structure. DeepForge pressure is active.

### 3. `domain_hint` (optional string)
Provides a soft orientation bias for the searchers to seed cross-domain vectors. E.g., `domain_hint="botany"` adjusts the search generation without limiting it exclusively to botany sources.

### 4. `pressure_translate_enabled` (boolean)
Defines whether the translation engine utilizes the adversarial translation logic when in `exploration_mode="forge"`. Cannot be enabled when in `"standard"` mode.

### 5. `pressure_search_mode` (string)
* `"off"`: Search candidate pools remain fixed.
* `"adaptive"`: Engages the `AdaptiveExplorationController`. Enables mid-run modifications if structural variety crashes below threshold limits. 
* `"always"`: Enforces maximum breadth penalty.

## Invariant Policies
* `max_rounds=1` must be interpreted as ZERO pressure rounds (i.e., only the default mirror generation occurs). Iterative pressure demands `max_rounds >= 2`.
* Distance thresholds evaluating novelty MUST properly assess the mathematical delta correctly (i.e. `min_dist >= 0.75`), not identically to `1.0 - 0.75`.
