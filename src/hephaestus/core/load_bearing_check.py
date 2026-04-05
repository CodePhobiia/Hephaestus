"""
Load-Bearing Domain Check.

Evaluates whether a translated mechanism genuinely depends on both domains in
the collision, rather than merely borrowing vocabulary from one of them.

The core subtraction test is simple:

1. Remove the source-domain logic. Does the mechanism still stand?
2. Remove the target-domain logic. Does the mechanism still stand?

If either answer is "yes", that domain is decorative rather than
structurally load-bearing.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field, replace
from typing import Any

from hephaestus.core.json_utils import loads_lenient
from hephaestus.core.translator import Translation
from hephaestus.deepforge.harness import DeepForgeHarness

logger = logging.getLogger(__name__)


_STOPWORDS = {
    "about",
    "after",
    "against",
    "algorithm",
    "also",
    "because",
    "before",
    "being",
    "between",
    "build",
    "built",
    "concrete",
    "design",
    "domain",
    "during",
    "each",
    "into",
    "logic",
    "mechanism",
    "method",
    "other",
    "problem",
    "process",
    "through",
    "using",
    "where",
    "which",
    "would",
}

_GENERIC_TERMS = {
    "agent",
    "architecture",
    "component",
    "control",
    "controller",
    "data",
    "element",
    "engine",
    "entity",
    "function",
    "input",
    "layer",
    "model",
    "module",
    "object",
    "operator",
    "output",
    "pattern",
    "platform",
    "process",
    "resource",
    "service",
    "signal",
    "solution",
    "state",
    "step",
    "structure",
    "system",
    "task",
    "unit",
    "workflow",
}

_TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9-]*")

_CRITIQUE_SYSTEM = """\
You are a structural subtraction critic.

Your task is to check whether both domains in a translated mechanism are
structurally load-bearing. Use two subtraction tests:

1. Remove all source-domain-specific logic. If the mechanism still functions,
   the source domain is decorative.
2. Remove all target-domain-specific implementation logic. If the mechanism
   still functions, the target domain is decorative.

Be rigorous. Reject superficial metaphors and relabeling.

Return JSON only:
{
  "source_domain_load_bearing": <bool>,
  "source_mechanism_survives_without_domain": <bool>,
  "source_reasons": ["<reason>", ...],
  "target_domain_load_bearing": <bool>,
  "target_mechanism_survives_without_domain": <bool>,
  "target_reasons": ["<reason>", ...],
  "overall_pass": <bool>
}
"""

_CRITIQUE_PROMPT_TEMPLATE = """\
TRANSLATION:
Invention: {invention_name}
Source domain: {source_domain}

ELEMENT MAPPINGS:
{mapping_text}

ARCHITECTURE:
{architecture}

IMPLEMENTATION NOTES:
{implementation_notes}

KEY INSIGHT:
{key_insight}

LIMITATIONS:
{limitations}

HEURISTIC FINDINGS:
Source-domain subtraction:
{source_reasons}

Target-domain subtraction:
{target_reasons}

Perform the two subtraction tests. Return JSON only.
"""


@dataclass
class DomainLoadBearingAssessment:
    """Assessment for one side of the domain subtraction test."""

    domain_name: str
    is_load_bearing: bool
    mechanism_survives_without_domain: bool
    reasons: list[str] = field(default_factory=list)
    confidence: float = 0.0
    method: str = "heuristic"


@dataclass
class LoadBearingCheckResult:
    """Combined result for the source and target domain subtraction tests."""

    passed: bool
    source_assessment: DomainLoadBearingAssessment
    target_assessment: DomainLoadBearingAssessment
    reasons: list[str] = field(default_factory=list)
    critique_used: bool = False

    def summary(self) -> str:
        return (
            f"load-bearing={'PASS' if self.passed else 'FAIL'} "
            f"| source={'PASS' if self.source_assessment.is_load_bearing else 'FAIL'} "
            f"| target={'PASS' if self.target_assessment.is_load_bearing else 'FAIL'}"
        )


def check_source_domain_subtraction(translation: Translation) -> DomainLoadBearingAssessment:
    """
    Check whether the source-domain logic is structurally necessary.

    If the translated mechanism can mostly be read and implemented after
    stripping away the source-domain operators, the source domain is decorative.
    """
    text = _combined_translation_text(translation)
    target_markers = _extract_markers(
        [mapping.target_element for mapping in translation.mapping],
        exclude_generic=True,
    )
    source_markers = _extract_source_markers(translation, target_markers)
    source_hits = _mentions(text, source_markers)

    substantive_mappings = sum(
        1 for mapping in translation.mapping if _is_substantive(mapping.mechanism)
    )
    mapped_source_elements = sum(
        1 for mapping in translation.mapping if _extract_markers([mapping.source_element])
    )
    source_limit_hits = sum(
        1 for limitation in translation.limitations if _mentions(limitation.lower(), source_markers)
    )

    runtime_footprint = len(source_hits) >= 2
    structural_bridge = mapped_source_elements >= 2 and substantive_mappings >= 2
    source_failure_awareness = source_limit_hits >= 1
    is_load_bearing = runtime_footprint and (structural_bridge or source_failure_awareness)

    reasons: list[str] = []
    if runtime_footprint:
        reasons.append(
            f"Architecture retains source-derived operators: {', '.join(source_hits[:3])}."
        )
    else:
        reasons.append(
            "Architecture can mostly be read without source-domain operators, "
            "so removing the source logic leaves the mechanism largely intact."
        )

    if structural_bridge:
        reasons.append(
            f"{substantive_mappings} mapped source elements contribute concrete "
            "mechanisms instead of pure relabeling."
        )
    else:
        reasons.append(
            "The mapping does not carry enough independent source-side mechanisms "
            "to make the source domain indispensable."
        )

    if source_failure_awareness:
        reasons.append(
            "Limitations explicitly describe where the source analogy breaks, "
            "which suggests the source logic is actually in play."
        )

    return DomainLoadBearingAssessment(
        domain_name=translation.source_domain,
        is_load_bearing=is_load_bearing,
        mechanism_survives_without_domain=not is_load_bearing,
        reasons=reasons,
        confidence=_score_confidence(
            is_load_bearing=is_load_bearing,
            primary_signal=runtime_footprint,
            secondary_signals=structural_bridge + source_failure_awareness,
        ),
    )


async def check_load_bearing_domains(
    translation: Translation,
    critique_harness: DeepForgeHarness | None = None,
    system: str | None = None,
) -> LoadBearingCheckResult:
    """
    Run the load-bearing check for both domains.

    The deterministic heuristic runs first. If a ``critique_harness`` is
    provided, a prompt-based subtraction critique is used as a second pass.
    """
    source_assessment = check_source_domain_subtraction(translation)
    target_assessment = _check_target_domain_subtraction(translation)
    result = _build_result(source_assessment, target_assessment, critique_used=False)

    if critique_harness is None:
        return result

    critique = await _run_prompt_critique(
        translation=translation,
        critique_harness=critique_harness,
        source_assessment=source_assessment,
        target_assessment=target_assessment,
        system=system,
    )
    if critique is None:
        return result

    merged_source = _merge_assessment(
        heuristic=source_assessment,
        load_bearing=_as_bool(
            critique.get("source_domain_load_bearing"),
            fallback=source_assessment.is_load_bearing,
        ),
        survives_without_domain=_as_bool(
            critique.get("source_mechanism_survives_without_domain"),
            fallback=source_assessment.mechanism_survives_without_domain,
        ),
        critique_reasons=_as_string_list(critique.get("source_reasons")),
    )
    merged_target = _merge_assessment(
        heuristic=target_assessment,
        load_bearing=_as_bool(
            critique.get("target_domain_load_bearing"),
            fallback=target_assessment.is_load_bearing,
        ),
        survives_without_domain=_as_bool(
            critique.get("target_mechanism_survives_without_domain"),
            fallback=target_assessment.mechanism_survives_without_domain,
        ),
        critique_reasons=_as_string_list(critique.get("target_reasons")),
    )
    merged = _build_result(merged_source, merged_target, critique_used=True)
    if "overall_pass" in critique:
        merged.passed = _as_bool(critique.get("overall_pass"), fallback=merged.passed)
    return merged


def _check_target_domain_subtraction(translation: Translation) -> DomainLoadBearingAssessment:
    text = _combined_translation_text(translation)
    target_markers = _extract_markers(
        [mapping.target_element for mapping in translation.mapping],
        exclude_generic=True,
    )
    source_markers = _extract_source_markers(translation, target_markers)
    target_hits = _mentions(text, target_markers)

    target_specific_elements = sum(
        1
        for mapping in translation.mapping
        if _extract_markers([mapping.target_element], exclude_generic=True)
    )
    source_marker_set = set(source_markers)
    target_impl_markers = [
        marker
        for marker in _extract_markers(
            [translation.implementation_notes],
            exclude_generic=True,
        )
        if marker not in source_marker_set
    ][:6]
    generic_target_elements = len(translation.mapping) - target_specific_elements
    generic_ratio = (
        generic_target_elements / len(translation.mapping) if translation.mapping else 1.0
    )

    target_runtime_footprint = len(target_hits) >= 2 or len(target_impl_markers) >= 3
    concrete_target_substrate = target_specific_elements >= 2 or len(target_impl_markers) >= 3
    over_generic = (
        generic_ratio >= 0.75 and len(target_impl_markers) < 2
    ) or target_specific_elements < 2
    is_load_bearing = target_runtime_footprint and concrete_target_substrate and not over_generic

    reasons: list[str] = []
    if target_specific_elements >= 2:
        reasons.append(
            "Mapping lands on concrete target-side components rather than generic placeholders."
        )
    else:
        reasons.append(
            "target-side mapping is too generic, so subtracting target-domain logic leaves "
            "mostly an abstract or source-domain story."
        )

    if len(target_hits) >= 2:
        reasons.append(
            "Architecture refers back to translated target-side components: "
            f"{', '.join(target_hits[:3])}."
        )
    elif len(target_impl_markers) >= 3:
        reasons.append(
            "Architecture and implementation notes still anchor the mechanism in a concrete "
            "target substrate."
        )
    else:
        reasons.append(
            "Architecture is not yet anchored strongly enough in target-side implementation details."
        )

    if over_generic:
        reasons.append(
            "Most target elements collapse to generic labels, which is a common sign that the "
            "target domain is decorative."
        )

    return DomainLoadBearingAssessment(
        domain_name="target domain",
        is_load_bearing=is_load_bearing,
        mechanism_survives_without_domain=not is_load_bearing,
        reasons=reasons,
        confidence=_score_confidence(
            is_load_bearing=is_load_bearing,
            primary_signal=target_runtime_footprint,
            secondary_signals=concrete_target_substrate + (not over_generic),
        ),
    )


def _build_result(
    source_assessment: DomainLoadBearingAssessment,
    target_assessment: DomainLoadBearingAssessment,
    *,
    critique_used: bool,
) -> LoadBearingCheckResult:
    passed = source_assessment.is_load_bearing and target_assessment.is_load_bearing
    if passed:
        reasons = _unique_reasons(source_assessment.reasons[:2] + target_assessment.reasons[:2])
    else:
        reasons = _unique_reasons(
            (source_assessment.reasons[:2] if not source_assessment.is_load_bearing else [])
            + (target_assessment.reasons[:2] if not target_assessment.is_load_bearing else [])
        )
    return LoadBearingCheckResult(
        passed=passed,
        source_assessment=source_assessment,
        target_assessment=target_assessment,
        reasons=reasons,
        critique_used=critique_used,
    )


async def _run_prompt_critique(
    translation: Translation,
    critique_harness: DeepForgeHarness,
    source_assessment: DomainLoadBearingAssessment,
    target_assessment: DomainLoadBearingAssessment,
    system: str | None,
) -> dict[str, Any] | None:
    mapping_text = "\n".join(
        (f"- {mapping.source_element} -> {mapping.target_element}: {mapping.mechanism}")
        for mapping in translation.mapping[:8]
    )
    limitations_text = (
        "\n".join(f"- {limitation}" for limitation in translation.limitations[:5])
        or "- (none listed)"
    )
    prompt = _CRITIQUE_PROMPT_TEMPLATE.format(
        invention_name=translation.invention_name,
        source_domain=translation.source_domain,
        mapping_text=mapping_text or "- (no explicit mapping provided)",
        architecture=translation.architecture[:2000],
        implementation_notes=translation.implementation_notes[:1000] or "(none)",
        key_insight=translation.key_insight[:500] or "(none)",
        limitations=limitations_text,
        source_reasons="\n".join(f"- {reason}" for reason in source_assessment.reasons),
        target_reasons="\n".join(f"- {reason}" for reason in target_assessment.reasons),
    )

    try:
        result = await critique_harness.forge(
            prompt,
            system=system or _CRITIQUE_SYSTEM,
            max_tokens=1200,
            temperature=0.2,
        )
    except Exception as exc:
        logger.warning("Load-bearing critique failed, keeping heuristic result: %s", exc)
        return None

    parsed = _parse_json(result.output)
    return parsed if parsed else None


def _merge_assessment(
    heuristic: DomainLoadBearingAssessment,
    *,
    load_bearing: bool,
    survives_without_domain: bool,
    critique_reasons: list[str],
) -> DomainLoadBearingAssessment:
    reasons = critique_reasons or heuristic.reasons
    return replace(
        heuristic,
        is_load_bearing=load_bearing,
        mechanism_survives_without_domain=survives_without_domain,
        reasons=reasons,
        confidence=max(heuristic.confidence, 0.8),
        method="heuristic+critique",
    )


def _extract_source_markers(
    translation: Translation,
    target_markers: list[str],
) -> list[str]:
    lens_axioms = translation.source_candidate.lens_used.axioms[:3]
    source_texts = [
        translation.source_domain,
        translation.source_candidate.source_solution,
        translation.source_candidate.mechanism,
        *lens_axioms,
        *[mapping.source_element for mapping in translation.mapping],
    ]
    markers = _extract_markers(source_texts)
    exclusive = [marker for marker in markers if marker not in set(target_markers)]
    return exclusive or markers


def _combined_translation_text(translation: Translation) -> str:
    parts = [
        translation.architecture,
        translation.key_insight,
        translation.implementation_notes,
        translation.mathematical_proof,
        *translation.limitations,
    ]
    return " ".join(part.strip() for part in parts if part and part.strip()).lower()


def _extract_markers(
    texts: list[str],
    *,
    exclude_generic: bool = False,
) -> list[str]:
    markers: list[str] = []
    blocked = _STOPWORDS | (_GENERIC_TERMS if exclude_generic else set())
    for text in texts:
        for raw_token in _TOKEN_RE.findall(text.lower()):
            token = raw_token.strip("-")
            if len(token) < 4 or token in blocked:
                continue
            markers.append(token)
    return sorted(set(markers), key=len, reverse=True)


def _mentions(text: str, markers: list[str]) -> list[str]:
    hits = [marker for marker in markers if marker in text]
    return hits[:6]


def _is_substantive(text: str) -> bool:
    return len(_TOKEN_RE.findall(text)) >= 4


def _score_confidence(
    *,
    is_load_bearing: bool,
    primary_signal: bool,
    secondary_signals: int,
) -> float:
    base = 0.55
    if is_load_bearing:
        return min(0.95, base + (0.18 if primary_signal else 0.0) + (0.1 * secondary_signals))
    missing_signals = (0 if primary_signal else 1) + max(0, 2 - secondary_signals)
    return min(0.95, base + (0.1 * missing_signals))


def _parse_json(raw: str) -> dict[str, Any]:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned, count=1)
        cleaned = re.sub(r"\n?```\s*$", "", cleaned)

    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        return {}

    try:
        parsed = loads_lenient(match.group(), default={}, label="load_bearing")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _as_bool(value: Any, *, fallback: bool) -> bool:
    return value if isinstance(value, bool) else fallback


def _as_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value]
    return []


def _unique_reasons(reasons: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for reason in reasons:
        if reason in seen:
            continue
        seen.add(reason)
        unique.append(reason)
    return unique


__all__ = [
    "DomainLoadBearingAssessment",
    "LoadBearingCheckResult",
    "check_load_bearing_domains",
    "check_source_domain_subtraction",
]
