# Load-Bearing Domain Check Design

## Goal

The load-bearing check asks whether a Stage 4 `Translation` actually depends on
both domains in the collision:

1. Source domain: the foreign mechanism that supplied the structural transfer.
2. Target domain: the concrete implementation substrate described by the
   translated architecture.

If removing either side leaves the mechanism essentially intact, that domain is
decorative rather than structurally load-bearing.

This follows the repo's existing V2 prompt rule:

- Remove Domain A logic. If the mechanism still works, Domain A is decorative.
- Remove Domain B logic. If the mechanism still works, Domain B is decorative.

## Scope

This change intentionally does **not** wire the check into `genesis.py` or
`verifier.py` yet. The goal of this pass is to establish:

- a standalone module,
- a small public API,
- deterministic tests,
- and a design contract the rest of the pipeline can consume later.

## Public API

The module lives at `src/hephaestus/core/load_bearing_check.py`.

Public surface:

- `DomainLoadBearingAssessment`
- `LoadBearingCheckResult`
- `check_source_domain_subtraction(translation)`
- `check_load_bearing_domains(translation, critique_harness=None, system=None)`

Design choices:

- `check_source_domain_subtraction(...)` is deterministic and synchronous.
- `check_load_bearing_domains(...)` is async because it may optionally call a
  `DeepForgeHarness` for a second-pass critique.
- The target-side subtraction helper stays private to keep the API small.

## Heuristic Strategy

The deterministic pass uses lexical and structural signals already present on a
`Translation`.

### Source-domain subtraction

The source domain is treated as load-bearing when the translation shows both:

- runtime footprint:
  source-derived operators still appear in architecture, insight, notes, proof,
  or limitations
- structural bridge:
  multiple mapped source elements contribute concrete mechanisms rather than
  simple relabeling

Extra confidence is added if the limitations explicitly discuss where the source
analogy breaks, because that usually means the source logic is active rather
than ornamental.

### Target-domain subtraction

The target domain is treated as load-bearing when the translation shows both:

- concrete target substrate:
  mappings land on specific target-side components instead of generic labels
- implementation footprint:
  architecture or notes stay anchored in target-side machinery even after
  excluding obvious source-domain vocabulary

This matters because a translation can fail in the opposite direction: it can
carry rich foreign-domain imagery but never really become an implementable
target-domain mechanism.

## Prompt-Based Critique

Heuristics are cheap and deterministic, but they are still approximations.
Because of that, the overall async API accepts an optional `critique_harness`.

When supplied:

1. Run the heuristic pass first.
2. Send the translation plus heuristic findings to a structured subtraction
   critic prompt.
3. Merge the JSON result back into the assessments.

Why optional:

- unit tests stay deterministic without model calls
- callers can opt into a stronger critique only where the extra cost is worth it
- the public surface remains small

## Result Model

Each domain assessment returns:

- pass/fail (`is_load_bearing`)
- subtraction outcome (`mechanism_survives_without_domain`)
- human-readable reasons
- confidence
- method (`heuristic` or `heuristic+critique`)

The overall result returns:

- overall pass/fail
- source assessment
- target assessment
- top-level reasons
- whether critique was used

## Known Limits

This module does **not** prove semantic necessity. It infers necessity from the
quality of the translation artifact.

Main limits:

- lexical heuristics can miss deeper structural dependence when the translation
  is very compressed
- target-domain detection is harder because `Translation` does not explicitly
  store a target-domain name
- prompt critique improves judgment, but only when a harness is supplied

## Expected Integration Path

Likely next steps after this standalone landing:

1. Run the check after Stage 4 translation.
2. Attach the result to Stage 5 verification output.
3. Use failures to reject decorative cross-domain inventions early.
4. Surface the subtraction reasons in interactive mode so users can refine weak
   translations.
