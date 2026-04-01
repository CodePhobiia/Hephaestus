# Failure Log Design

## Goal

Capture rejected invention attempts without coupling analytics deeply into the
Genesis pipeline yet. The log is intended to answer questions like:

- Which source → target domain pairs keep failing?
- Which verifier critiques recur?
- Which inventions are collapsing back into burn-off baselines?
- Which rejection modes dominate: fatal flaws, derivative verdicts, or low feasibility?

## Storage Model

Failure records are stored as append-only JSON Lines under:

`~/.hephaestus/failures/`

Records are partitioned by UTC day:

- `~/.hephaestus/failures/2026-04-01.jsonl`
- `~/.hephaestus/failures/2026-04-02.jsonl`

This keeps writes simple and cheap while staying easy to inspect with normal
Unix tools.

## Record Shape

Each record stores:

- `record_id`
- `timestamp`
- `problem`
- `invention_name`
- `source_domain`
- `target_domain`
- `domain_pair`
- `rejection_reasons`
- `baseline_overlaps`
- `key_insight`
- `architecture`
- `limitations`
- `novelty_score`
- `structural_validity`
- `implementation_feasibility`
- `feasibility_rating`
- `prior_art_status`
- `verifier_critique`

`verifier_critique` preserves the parts of Stage 5 that are most useful for
later analysis:

- `verdict`
- `strongest_objection`
- `fatal_flaws`
- `structural_weaknesses`
- `validity_notes`
- `feasibility_notes`
- `novelty_notes`

## Rejection Classification

The analytics layer classifies a verified invention as rejected when any of the
following are true:

- Verifier returned fatal flaws
- Verifier verdict is `QUESTIONABLE`, `DERIVATIVE`, or `INVALID`
- Feasibility rating is `LOW` or `THEORETICAL`
- The invention text overlaps a burn-off baseline

The stored rejection reason codes are stable query keys:

- `fatal_flaws`
- `verdict_questionable`
- `verdict_derivative`
- `verdict_invalid`
- `low_feasibility`
- `theoretical_feasibility`
- `baseline_overlap`

## Baseline Overlap Heuristic

Baseline overlap is intentionally heuristic, not semantic:

- direct normalized substring match, or
- at least 60% token overlap for baselines with 3+ informative tokens

This is cheap, deterministic, and good enough for first-pass analytics. If it
proves noisy, it can later be replaced with embedding or structured-comparison
logic without changing the record format.

## API Surface

`FailureLog` exposes:

- `append(record)`
- `append_many(records)`
- `append_rejected_inventions(inventions, target_domain, ...)`
- `query(...)`

`query()` is scan-based and currently supports filters for:

- `source_domain`
- `target_domain`
- `domain_pair`
- `rejection_reason`
- `verdict`
- `baseline_overlap`
- `invention_name`
- `since`
- `until`
- `limit`

## Integration Boundary

Genesis only has a best-effort post-verification hook:

1. Run verifier
2. Ask `FailureLog` to persist rejected inventions
3. Continue even if logging fails

This keeps the failure log useful immediately without making pipeline success
depend on analytics infrastructure.

## Why JSONL Instead Of SQLite

For this first pass:

- append performance is trivial
- the schema is flexible
- inspection is easy during development
- no migration system is required

If query volume grows or cross-run analytics become more sophisticated, the same
record schema can be mirrored into SQLite or a vector store later.
