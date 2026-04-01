# Invention Quality Improvement Plan

## Root Cause Analysis

After reading every system prompt, data structure, and pipeline stage, the core quality problems are:

### 1. The translator prompt asks for metaphor, not mechanism
The `_TRANSLATE_SYSTEM` prompt says "not a metaphor, but a genuine engineering blueprint" — but then asks for `invention_name` (which incentivizes creative naming), `mapping.elements` (which is literally a metaphor table), and `architecture` as free text. The model naturally produces dressed-up analogies because the output schema rewards it.

**Fix:** Add a mandatory `mechanism_differs_from_baseline` field that forces the model to explicitly state what this does DIFFERENTLY from the obvious solution. Add a `subtraction_test` field where the model must explain what breaks if you remove the source domain's logic entirely.

### 2. The search prompt doesn't constrain against obvious matches
`_SEARCH_SYSTEM` says "find ONE real, well-understood solved problem that shares the SAME MATHEMATICAL STRUCTURE." This is correct but insufficient — it doesn't say "and the solution must use a mechanism that is NON-OBVIOUS in the target domain." The model finds structurally matching problems but the solutions they use are often well-known patterns (caching, retry, weighting) that any engineer would reach for.

**Fix:** Add an explicit anti-obviousness constraint: "The mechanism must be one that a domain expert in the TARGET domain would NOT independently reach for."

### 3. The scorer doesn't penalize conventional mechanisms
`CandidateScorer` evaluates structural fidelity and domain distance but never asks "is the proposed mechanism actually novel in the target domain?" A candidate from biology that proposes "cache successful results" gets high domain distance (biology → CS = far!) but the mechanism itself (caching) is the most obvious thing in CS.

**Fix:** Add a `mechanism_novelty` score that evaluates whether the mechanism is surprising in the target domain, independent of the source domain's distance.

### 4. The verifier's novelty score is self-referential  
The validity assessor rates novelty 0.0-1.0 but has no grounding — it's just the same model's opinion. The prior art search hits rate limits and returns nothing useful. The novelty score is essentially made up.

**Fix:** Ground novelty scoring in concrete tests: (a) Can you describe this mechanism without mentioning the source domain? If yes, it's probably known. (b) Does removing the source domain vocabulary change the architecture? If no, the transfer is decorative.

### 5. The load-bearing check exists but isn't in the pipeline
`load_bearing_check.py` does exactly what's needed — subtraction tests — but it's not called during the genesis pipeline. It's a standalone module.

**Fix:** Wire it into Stage 5 (Verify). If the load-bearing check fails, downgrade the invention.

## 12-Cycle Execution Plan

### Cycle 1: Translator prompt hardening
- Add `mechanism_differs_from_baseline` to translation schema
- Add `subtraction_test` to translation schema  
- Add `if_you_removed_source_domain` field
- Update tests

### Cycle 2: Search anti-obviousness
- Add anti-obviousness constraint to `_SEARCH_SYSTEM`
- Add `mechanism_novelty_in_target` field to SearchCandidate
- Model must rate: "How surprising is this mechanism to a target-domain expert?"

### Cycle 3: Scorer mechanism novelty
- Add `mechanism_novelty` dimension to CandidateScorer
- Score: "Is the proposed mechanism conventional in the target domain?"
- Weight it into combined_score

### Cycle 4: Wire load-bearing check into pipeline
- Call check_load_bearing_domains() in Stage 5
- If load-bearing check fails → downgrade novelty score by 50%
- Add load_bearing_passed field to VerifiedInvention

### Cycle 5: Ground novelty scoring
- Replace the verifier's opinion-based novelty with concrete tests
- Test 1: "Describe this without source domain words" — if coherent, it's known
- Test 2: "What's the simplest baseline that solves this?" — compare to invention
- Test 3: Prior art keyword extraction + web search

### Cycle 6: Test run + evaluate
- Run the pipeline on 3 real problems
- Rate each invention honestly
- Document what improved, what didn't

### Cycle 7: Baseline comparison gate
- Add Stage 5.5: "What would a senior engineer build without cross-domain thinking?"
- Compare invention to baseline
- If they're essentially the same mechanism → DERIVATIVE
- Compute delta_novelty = invention - baseline

### Cycle 8: Crutch filter integration  
- Wire deepforge/crutch_filter.py into translation output
- Filter banned phrases that signal metaphor-not-mechanism
- "leverages", "inspired by", "analogous to" → force concrete rewrite

### Cycle 9: Anti-memory sharpening
- After each run, add the MECHANISM (not the domain) to anti-memory
- "Caching successful results" goes to anti-memory, not "T-cell memory"
- Forces genuinely different mechanisms on next run

### Cycle 10: Test run + evaluate  
- Run on same 3 problems as Cycle 6
- Compare quality before/after
- Document improvements

### Cycle 11: Prompt refinement based on results
- Adjust prompts based on Cycle 10 findings
- Tighten or loosen constraints as needed

### Cycle 12: Final test + report
- Run on 5 diverse problems
- Full quality assessment
- Ship the improved pipeline
