# Domain Selection Diversity

## Purpose

Hephaestus already excludes the problem's exact native domain during Stage 2 lens
selection. That was not enough to create reliable cross-family diversity: a
software problem could still heavily favor engineering-adjacent lenses, and a
biology problem could still cluster around nearby life-science domains.

This document defines the added family-level diversity layer.

## Domain Families

Each lens is classified into a high-level `domain_family`. The classifier first
checks explicit aliases, then falls back to token hints so decomposed problem
domains like `distributed_systems` and `finance` resolve sensibly even when they
do not exactly match a lens `domain`.

Canonical families currently used by the selector:

- `physical_sciences`
- `biology`
- `economics`
- `myth`
- `linguistics`
- `arts`
- `military`
- `agriculture`
- `psychology`
- `mathematics`
- `engineering`
- `general`

Examples:

- `physics`, `chemistry`, `astronomy`, `materials` -> `physical_sciences`
- `biology`, `neuroscience`, `epidemiology` -> `biology`
- `economics`, `finance`, `markets` -> `economics`
- `mythology` -> `myth`
- `linguistics`, `syntax`, `semantics` -> `linguistics`
- `art`, `music`, `film`, `textiles` -> `arts`
- `military`, `martial_arts`, `sports` -> `military`
- `agriculture`, `forestry`, `cooking`, `culinary` -> `agriculture`
- `psychology`, `sociology` -> `psychology`
- `math`, `mathematics`, `philosophy` -> `mathematics`
- `engineering`, `cs`, `distributed_systems`, `architecture`, `urban_planning` -> `engineering`

## Selector Weighting

The selector still computes the base score from semantic distance and structural
relevance:

```text
base_score = distance^alpha * relevance
```

It now multiplies that by a family diversity weight:

```text
composite_score = base_score * diversity_weight
```

Weights:

- Same family as the target domain: `0.40`
- Near family: `0.75`
- Distant or unrelated family: `1.00`

The target family is derived from:

- `target_domain`, when provided
- `exclude_domains`, as a fallback or secondary signal

Current near-family graph is intentionally small and explicit. Examples:

- `engineering` is near `mathematics`, `physical_sciences`, `economics`, `military`
- `biology` is near `physical_sciences`, `agriculture`, `psychology`
- `arts` is near `linguistics` and `myth`

This is a down-weight, not a hard filter. Nearby domains can still win when
their semantic distance and structural relevance are substantially stronger.

## Implementation Notes

- `src/hephaestus/lenses/loader.py`
  - adds `classify_domain_family(...)`
  - assigns `Lens.domain_family`
  - includes `domain_family` in lightweight lens metadata
- `src/hephaestus/lenses/selector.py`
  - derives target families
  - applies same-family and near-family penalties during ranking
  - records `domain_family` and `diversity_weight` on `LensScore`
- `src/hephaestus/core/searcher.py`
  - passes `structure.native_domain` into the selector as `target_domain`

## Expected Effect

For a problem in `distributed_systems`, the selector should now prefer
cross-family domains such as mythology, arts, biology, or agriculture over
equally scored engineering-adjacent domains like `cs`, `architecture`, or
`urban_planning`.

The result is not randomization. It is a controlled bias toward structurally
foreign source domains while keeping exact-domain exclusion and structural
relevance intact.
