# doc04 creativity implementation report

## What changed

- Upgraded `BranchGenome` from a scalar-heuristic flow to a quality-diversity surface.
  - Added shared novelty-vector support via [`src/hephaestus/novelty/vector.py`](/tmp/heph-doc-impl-20260402-070453/doc04/src/hephaestus/novelty/vector.py).
  - Extended branch metrics with positive-archive overlap, load-bearing creativity, diversity credit, quality-diversity score, archive cell, island key, and retrieval-expansion readiness.
  - Added branch runtime metadata for archive placement, crossover parents, and branch-conditioned retrieval hints.
- Upgraded branch arena evolution and preservation.
  - Added positive archive / island elite tracking.
  - Promotion now preserves distinct archive cells and islands before filling globally.
  - Pruning now keeps uniquely valuable cells alive when they clear the quality-diversity floor.
  - Added bounded crossover branch creation between viable but structurally distinct islands.
- Improved novelty/evaluator surfaces.
  - `CandidateScorer` now executes both structural fidelity and mechanism-novelty scoring, emits a novelty vector, tracks creativity score, and folds mechanism novelty into ranking.
  - `ConvergenceDetector` now exposes novelty-vector components instead of only a scalar similarity.
  - `RejectionLedger` now supports positive-archive overlap queries and optional metadata persistence.
- Added retrieval expansion groundwork.
  - `CrossDomainSearcher` now accepts an optional `RetrievalExpansionRequest` and records/search-prompts branch-conditioned frontier hints.
  - Branch assay emits `retrieval_expansion_hints` so future runtime stages can request targeted frontier expansion without changing the branch API again.
- Wired the new branchgenome behavior into `core/genesis.py`.
  - Genesis now assays crossover branches, persists archive metadata to the ledger, and includes novelty/archive/crossover details in promoted branch outcomes.

## Tests run

```bash
pytest -q tests/test_branchgenome/test_assay.py tests/test_branchgenome/test_arena.py tests/test_branchgenome/test_ledger.py tests/test_branchgenome/test_genesis_integration.py tests/test_core/test_scorer.py tests/test_core/test_searcher.py tests/test_convergence/test_detector.py tests/test_core/test_structural_novelty.py tests/test_core/test_diversity.py tests/test_novelty/test_vector.py
```

- Result: `78 passed`

## Integration notes

- Retrieval expansion is groundwork, not a full second-pass search loop yet.
  - Branch assay now produces stable `retrieval_expansion_hints`.
  - Search supports `RetrievalExpansionRequest`.
  - Genesis does not yet re-enter search using those hints, which keeps this lane inside doc04 scope without forcing a broader runtime refactor.
- Crossover branches currently translate through the left parent candidate while carrying fused commitments from both parents.
  - This keeps translation compatibility with the existing scorer/translator contract.
  - If a later lane wants full dual-parent translation prompts, the branch runtime hooks now expose enough metadata to do it cleanly.
