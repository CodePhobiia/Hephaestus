# Solution Shape Detector Design

## Purpose

The Solution Shape Detector is a standalone heuristic module for answering one narrow question:

> Does a generated invention collapse back onto the same coarse architecture shape as a banned baseline?

This is not a semantic novelty engine and it is not a prior-art searcher. It is a lightweight structural filter that tags text with recurring architecture archetypes such as:

- `classifier_threshold`
- `recommender_ranker`
- `marketplace_reputation`
- `centralized_registry`
- `feedback_controller`
- `graph_ranker`
- `monitoring_intervention_loop`
- `pipeline`
- `consensus_quorum`
- `broker_queue_dispatch`
- `cache_fallback`
- `ensemble_gating`

The module lives at [src/hephaestus/novelty/solution_shapes.py](/home/ubuntu/.openclaw/workspace/hephaestus/src/hephaestus/novelty/solution_shapes.py).

## Design Goals

- Stay standalone. No model calls, no embeddings, no changes to `genesis.py` or `verifier.py`.
- Work on both banned baseline strings and generated invention objects.
- Support multi-label classification. An invention can be both a `pipeline` and a `graph_ranker`.
- Produce an overlap score that is tolerant of partial matches instead of only exact set equality.
- Be explainable. Every match includes lexical evidence.

## Core Model

The detector uses a small library of `ShapeDefinition` objects.

Each shape contains:

- A canonical key and human-readable label
- A description and example phrases
- Required signal groups
- Optional signal groups
- A minimum confidence threshold

Each signal group contains weighted lexical cues. A shape is detected only if:

1. Every required signal group matches at least one cue
2. The total weighted score clears the shape's `min_score`

That gives the detector two useful properties:

- It avoids matching on one generic word like `graph` or `pipeline`
- It still allows richer text to score higher via optional evidence

## Text Normalization

All inputs are normalized before matching:

- Lowercased
- Punctuation collapsed to spaces
- Whitespace collapsed

This makes phrase checks stable across text like:

- `classifier+threshold`
- `classifier / threshold`
- `classifier-threshold`

The matcher also includes a few inflection-aware regexes for common verbs such as `ingest`, `monitor`, `adjust`, and `intervene`.

## Input Types

The module supports three entry paths:

- `classify_banned_baseline(text)`
- `classify_architecture_text(text)`
- `classify_generated_invention(obj_or_dict_or_text)`

`classify_generated_invention(...)` is intentionally duck-typed. It can extract text from:

- Raw strings
- Dict payloads
- `Translation`-like objects
- `VerifiedInvention`-like objects

The extractor looks across fields such as:

- `invention_name`
- `architecture`
- `key_insight`
- `implementation_notes`
- `mathematical_proof`
- `limitations`
- `mapping`
- Nested `translation`

That means later integration can pass existing pipeline objects directly without adapter code.

## Confidence Scoring

For one shape:

```text
confidence = matched_group_weight / total_group_weight
```

Only matched groups contribute weight. Required groups gate eligibility. Optional groups raise confidence but are not necessary for a detection.

Example:

- `classifier_threshold` requires both a classifier cue and a threshold cue
- Mentioning `confidence` or `score` increases confidence slightly

## Aggregation

`aggregate_shape_scores(...)` builds a profile across many classifications.

Important rule:

- Repeated mentions of the same shape keep the maximum confidence instead of summing scores

That prevents a long banned-baseline list from inflating one archetype simply by repeating it several times.

## Overlap Score

`shape_overlap_score(...)` compares aggregated baseline and invention profiles using weighted Jaccard similarity:

```text
sum(min(b_i, i_i)) / sum(max(b_i, i_i))
```

Interpretation:

- `1.0`: same detected shape profile
- `0.0`: disjoint detected shape profiles
- Between `0` and `1`: partial overlap

This is better than plain set intersection because it:

- Handles multi-label profiles
- Preserves confidence
- Penalizes extra unmatched shapes

## Why Heuristics Instead of Embeddings

This module is meant to be cheap, deterministic, and debuggable.

Embeddings could be useful later, but for the first pass they introduce problems:

- Harder to explain why a shape fired
- Threshold tuning is less transparent
- More runtime and dependency cost
- Easier to overgeneralize on vague architectural prose

The current detector is intentionally lexical and conservative.

## Extension Path

To add a new shape:

1. Add a new `ShapeDefinition` to `COMMON_ARCHITECTURE_SHAPES`
2. Define required signal groups that capture the minimum structural identity
3. Add optional signal groups for confidence refinement
4. Add tests with both positive and negative examples

Rules for adding shapes:

- Prefer coarse reusable architecture archetypes, not domain-specific implementations
- Required groups should represent the minimum structure, not incidental vocabulary
- Avoid generic cues that fire on unrelated prose

## Current Limits

- It is still lexical, so highly abstract phrasing can evade detection
- It does not reason about whether two differently worded shapes are functionally equivalent unless the cues overlap
- It does not score invention quality or feasibility
- It does not yet integrate into `genesis` or `verifier`

That is deliberate. This module is designed as a solid standalone primitive first.
