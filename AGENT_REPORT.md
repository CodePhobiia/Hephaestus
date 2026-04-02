# doc01 Pantheon Consensus Lane

## What changed

- Extended Pantheon issue ledger semantics in `src/hephaestus/pantheon/models.py`.
- Added explicit issue typing, claim/evidence/discharge fields, repair-branch metadata, round phase metadata, and Pantheon observability counters.
- Reworked `src/hephaestus/pantheon/coordinator.py` around:
  - independent first-pass ballots before peer-visible council behavior
  - masked/sparse issue replay instead of full objection transcript replay
  - issue-type-aware convergence rules
  - disagreement-sensitive council invocation with `debate_invoked` / `debate_skip_reason`
  - targeted repair branches clustered by issue type instead of one blunt global reforge
  - Apollo tie-break adjudication for close repair branches
  - fail-loud forwarding of non-fatal unresolved candidates to verification
  - strict fail-closed behavior preserved for open fatal `TRUTH` / `NOVELTY` issues
- Updated Pantheon prompts in `src/hephaestus/pantheon/prompts.py` to match the new issue ledger schema, masked communication contract, and branch repair flow.
- Exported `PANTHEON_ISSUE_TYPES` from `src/hephaestus/pantheon/__init__.py`.
- Expanded `tests/test_pantheon/test_coordinator.py` to cover:
  - masked first-pass ballots
  - adaptive skip behavior
  - targeted multi-branch repair
  - fail-loud forwarding with open non-fatal issues

## Tests run

- `pytest -q tests/test_pantheon/test_coordinator.py`
- `pytest -q tests/test_core/test_genesis.py -k pantheon tests/test_output/test_formatter.py -k pantheon tests/test_export/test_markdown.py -k pantheon`
- `pytest -q -k pantheon`
- `python -m py_compile src/hephaestus/pantheon/models.py src/hephaestus/pantheon/prompts.py src/hephaestus/pantheon/coordinator.py src/hephaestus/pantheon/__init__.py`

## Integration notes

- Pantheon state now carries additional observability fields. Existing consumers that treat `pantheon_state` as an opaque dict/object should remain compatible.
- A new outcome tier, `FORWARDED_WITH_OPEN_ISSUES`, is now possible when Pantheon preserves truth but does not reach full consensus before handing candidates to verification.
- `allow_fail_closed=False` no longer forces no-output on repairable non-fatal disagreement; fatal `TRUTH` / `NOVELTY` issues still hard-block output.
- Repair branching stays local to Pantheon and does not reach into runtime orchestration or BranchGenome lanes.
