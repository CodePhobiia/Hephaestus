"""
Stage 4: Solution Translation.

Takes the top-N ``ScoredCandidate`` objects and builds a concrete structural
bridge between the foreign domain and the target domain.

For each candidate, uses Opus via DeepForge (with **cognitive interference
ACTIVE** — the lens is injected mid-reasoning) to produce:

1. **Explicit element-by-element structural mapping** — every component of the
   foreign solution mapped to its target-domain counterpart.
2. **Working architecture / pseudocode** in the target domain — concrete enough
   to implement.
3. **Honest limitations** — where the analogy breaks, what the mapping cannot
   handle.

The cognitive interference lens is active during translation to prevent the
model from defaulting to conventional solutions when bridging.

Usage::

    translator = SolutionTranslator(harness)
    translations = await translator.translate(scored_candidates, structure, top_n=3)
    for t in translations:
        print(t.architecture[:200])
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

from hephaestus.core.decomposer import ProblemStructure
from hephaestus.core.json_utils import extract_outermost_json_object, loads_lenient
from hephaestus.core.parallel import ParallelConfig, gather_with_semaphore
from hephaestus.core.scorer import ScoredCandidate
from hephaestus.deepforge.harness import DeepForgeHarness, ForgeTrace, HarnessConfig
from hephaestus.deepforge.interference import InjectionStrategy
from hephaestus.deepforge.interference import Lens as ForgeLens
from hephaestus.lenses.bundles import BundleComposer
from hephaestus.lenses.cells import build_reference_state
from hephaestus.lenses.guards import evaluate_handoff_guards

logger = logging.getLogger(__name__)


def _timeout_seconds(harness: Any) -> float:
    value = getattr(getattr(harness, "config", None), "timeout_seconds", 0.0)
    return float(value) if isinstance(value, (int, float)) else 0.0


def _pressure_enabled(harness: Any) -> bool:
    value = getattr(getattr(harness, "config", None), "use_pressure", False)
    return value if isinstance(value, bool) else False


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_TRANSLATE_SYSTEM = """\
You are a structural translation engine. You perform cross-domain structural
transfer in TWO MANDATORY PHASES. Both phases must be completed.

PHASE 1 — MECHANISM EXTRACTION (source domain only, NO target domain language):
First, describe the foreign mechanism in purely ABSTRACT terms. Strip all
domain-specific vocabulary. What is the mechanism doing structurally?
Not "T-cells remember pathogens" but "entities that encountered a stimulus
retain a modified state that accelerates future response to structurally
similar stimuli, with the modification encoding both the stimulus signature
and the response pathway."

SELF-CHECK FOR PHASE 1: After writing the abstract mechanism, ask:
"Is this just [parallel execution / caching / retry / queuing /
load balancing / pub-sub / observer pattern / state machine]?"
If yes, STOP. These are elementary engineering patterns. Cross-domain
transfer should find mechanisms that are NOT in the standard engineering
toolkit. If your Phase 1 reduces to a well-known pattern, set
mechanism_is_decorative to true and try to find a DIFFERENT mechanism
from the source domain — one that is specific enough to be genuinely
transferable.

PHASE 2 — MECHANISM APPLICATION (target domain only, NO source domain language):
Now take the abstract mechanism from Phase 1 and build a concrete architecture
in the target domain. Do NOT reference the source domain at all. If you cannot
describe a novel architecture without mentioning the source domain, the transfer
is decorative and you must set mechanism_is_decorative to true.

CONCRETENESS REQUIREMENTS FOR PHASE 2:
- Name specific data structures (not "a data structure" but "a ring buffer of
  size 2^k indexed by hash(request_id) mod k")
- Include specific parameters with reasonable default values
- Write actual pseudocode with function signatures, not prose descriptions
- Specify complexity bounds (time and space)
- Include at least one concrete numerical example showing the mechanism in action
- Describe the failure mode and recovery procedure
- Include a BEFORE/AFTER comparison: "Without this mechanism, the system does X.
  With this mechanism, the system does Y. The specific measurable improvement is Z."
- If possible, describe the MINIMAL VIABLE VERSION — what is the smallest change
  that captures 80% of the benefit? Engineers want to prototype, not build the
  full system on day one.

CRITICAL SELF-TEST: After writing the architecture, ask: "Is this mechanism
already known in the target domain under a different name?" If yes, your
transfer added no value. Set mechanism_is_decorative to true and explain
what known pattern it collapses to.

If active branch recovery operators are provided, you MUST preserve them as
concrete architectural commitments, not just mention them. For example:
- attractor breaker: explicitly forbid the closest obvious baseline as the
  primary organizing primitive
- subtraction probe: explain what still differs after source-domain words are removed
- order inversion: derive the normal path from failure/recovery logic first
- load-bearing ablation: identify what breaks if the imported mechanism is removed

You must output ONLY valid JSON matching this schema:
{
  "invention_name": "<short name (3-5 words MAX) that describes what the mechanism DOES in the target domain. NOT the source domain name. Good: 'Prediction-Error Rate Controller'. Bad: 'Immune-Memory Inspired Scheduler'. The name should make sense to a target-domain engineer who has never heard of the source domain.>",
  "phase1_abstract_mechanism": "<PHASE 1: The foreign mechanism described in purely abstract structural terms. NO source or target domain vocabulary. What is the mechanism doing mathematically/structurally?>",
  "phase2_target_architecture": "<PHASE 2: The mechanism applied to the target domain. NO source domain references. Concrete pseudocode, algorithms, data structures. 3-8 paragraphs.>",
  "mechanism_is_decorative": <bool — true if the mechanism is already known in the target domain>,
  "known_pattern_if_decorative": "<if decorative: what known pattern does this collapse to?>",
  "mapping": {
    "elements": [
      {
        "source_element": "<component in the foreign domain>",
        "target_element": "<component in the target domain>",
        "mechanism": "<how the structural correspondence works>"
      }
    ]
  },
  "architecture": "<COPY of phase2_target_architecture for backward compatibility>",
  "mathematical_proof": "<formal statement of structural isomorphism>",
  "limitations": ["<where the mechanism genuinely fails, not platitudes>"],
  "implementation_notes": "<practical engineering notes>",
  "key_insight": "<the ONE insight that makes this work — must be statable WITHOUT source domain words>",
  "mechanism_differs_from_baseline": "<What does this do that the obvious solution does not?>",
  "subtraction_test": "<Architecture described using ONLY target-domain language>",
  "baseline_comparison": "<Simplest conventional solution vs this invention's structural advantage>",
  "recovery_commitments": ["<for each active recovery operator, state the concrete commitment preserved in the architecture>"],
  "future_option_preservation": "<Which future implementation options remain open because this branch avoided early collapse, and what must not be collapsed into a standard baseline?>"
}

REQUIREMENTS:
- Phase 1 MUST use only abstract/mathematical language — no domain words from either side
- Phase 2 MUST use only target domain language — no source domain references
- If the mechanism is a known pattern (caching, retry, queue, etc.), set mechanism_is_decorative: true
- The architecture must be implementable — pseudocode, algorithms, data structures
- Limitations must be honest failure modes, not hedging
- If you find yourself writing "inspired by" or "analogous to" — STOP. The transfer is decorative.
"""

_TRANSLATE_PROMPT_TEMPLATE = """\
TARGET PROBLEM:
{original_problem}
{banned_baselines_section}
ABSTRACT STRUCTURAL FORM:
{structure}

MATHEMATICAL SHAPE:
{mathematical_shape}

CONSTRAINTS:
{constraints}

FOREIGN DOMAIN SOLUTION:
Source domain: {source_domain}
Solution: {source_solution}
Core mechanism: {mechanism}

DOMAIN LENS (active cognitive interference):
{lens_axioms}

STRUCTURAL FIDELITY SCORE: {fidelity:.2f}
DOMAIN DISTANCE: {distance:.2f}
{guidance_section}
{branch_commitments_section}
{bundle_proof_section}
{handoff_section}

Build the complete structural translation. Map every element. Write concrete architecture.
Be honest about limitations. Return JSON only.
"""


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class ElementMapping:
    """A single element mapping between the foreign and target domains."""

    source_element: str
    target_element: str
    mechanism: str


@dataclass
class Translation:
    """
    The output of Stage 4 for a single candidate.

    Attributes
    ----------
    invention_name:
        Short memorable name for the resulting invention.
    mapping:
        List of element-by-element mappings between domains.
    architecture:
        Concrete working architecture/pseudocode in the target domain.
    mathematical_proof:
        Brief formal statement of structural isomorphism.
    limitations:
        Honest list of where the analogy breaks or the solution fails.
    implementation_notes:
        Practical notes for engineers.
    key_insight:
        The single most important insight enabling the translation.
    source_candidate:
        The ``ScoredCandidate`` this translation is derived from.
    cost_usd:
        API cost for this translation.
    duration_seconds:
        Wall-clock time for this translation.
    trace:
        DeepForge trace (includes interference injection details).
    """

    invention_name: str
    mapping: list[ElementMapping]
    architecture: str
    mathematical_proof: str
    limitations: list[str]
    implementation_notes: str
    key_insight: str
    source_candidate: ScoredCandidate
    phase1_abstract_mechanism: str = ""
    phase2_target_architecture: str = ""
    mechanism_is_decorative: bool = False
    known_pattern_if_decorative: str = ""
    mechanism_differs_from_baseline: str = ""
    subtraction_test: str = ""
    baseline_comparison: str = ""
    recovery_commitments: list[str] = field(default_factory=list)
    future_option_preservation: str = ""
    cost_usd: float = 0.0
    duration_seconds: float = 0.0
    trace: ForgeTrace | None = None
    bundle_proof: Any | None = None
    bundle_lineage: Any | None = None
    guard_results: list[Any] = field(default_factory=list)
    guard_failed: bool = False
    selection_mode: str = "singleton"
    bundle_role: str = ""
    reference_signature: str = ""
    research_signature: str = ""
    branch_signature: str = ""
    recomposition_events: list[dict[str, Any]] = field(default_factory=list)

    @property
    def source_domain(self) -> str:
        return self.source_candidate.source_domain

    @property
    def lens_id(self) -> str:
        return self.source_candidate.lens_id

    @property
    def combined_score(self) -> float:
        return self.source_candidate.combined_score

    @property
    def domain_distance(self) -> float:
        return self.source_candidate.domain_distance

    @property
    def structural_fidelity(self) -> float:
        return self.source_candidate.structural_fidelity

    def summary(self) -> str:
        """One-line summary."""
        return (
            f"[{self.invention_name}] from {self.source_domain} "
            f"| mappings={len(self.mapping)} limitations={len(self.limitations)}"
        )


@dataclass
class TranslationGuidance:
    """Pipeline-native guidance injected into translation prompts."""

    structural_form: str = ""
    mandatory_constraints: list[str] = field(default_factory=list)
    anti_goals: list[str] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=list)
    false_framings: list[str] = field(default_factory=list)
    reality_summary: str = ""
    ecosystem_constraints: list[str] = field(default_factory=list)
    user_operator_constraints: list[str] = field(default_factory=list)
    adoption_risks: list[str] = field(default_factory=list)
    implementation_leverage_points: list[str] = field(default_factory=list)

    def has_content(self) -> bool:
        return any(
            [
                self.structural_form.strip(),
                self.mandatory_constraints,
                self.anti_goals,
                self.success_criteria,
                self.false_framings,
                self.reality_summary.strip(),
                self.ecosystem_constraints,
                self.user_operator_constraints,
                self.adoption_risks,
                self.implementation_leverage_points,
            ]
        )


# ---------------------------------------------------------------------------
# Translator
# ---------------------------------------------------------------------------


class TranslationError(Exception):
    """Raised when translation fails for a candidate."""


@dataclass
class TranslationRuntimeResult:
    """Adaptive runtime metadata for translation orchestration."""

    retrieval_mode: str
    bundle_proof: Any | None = None
    guard_history: list[Any] = field(default_factory=list)
    recomposition_events: list[dict[str, Any]] = field(default_factory=list)
    invalidated_lens_ids: tuple[str, ...] = ()
    fallback_used: bool = False
    translations: list[Translation] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "retrieval_mode": self.retrieval_mode,
            "bundle_proof": self.bundle_proof.to_dict() if self.bundle_proof is not None else None,
            "guard_history": [guard.to_dict() for guard in self.guard_history],
            "recomposition_events": list(self.recomposition_events),
            "invalidated_lens_ids": list(self.invalidated_lens_ids),
            "fallback_used": self.fallback_used,
            "translation_count": len(self.translations),
        }


class SolutionTranslator:
    """
    Stage 4 of the Genesis pipeline: Solution Translation.

    Translates foreign domain solutions into the target domain with concrete
    architectural detail. Runs with cognitive interference ACTIVE — the
    source domain's lens is injected mid-reasoning.

    Parameters
    ----------
    harness:
        DeepForge harness.  The harness SHOULD have cognitive interference
        enabled — this stage benefits most from it.
    top_n:
        Maximum number of candidates to translate (default 3).
    """

    def __init__(
        self,
        harness: DeepForgeHarness,
        top_n: int = 3,
        system: str | None = None,
        max_bundle_recompositions: int = 2,
        allow_bundle_fallback: bool = True,
    ) -> None:
        self._harness = harness
        self._top_n = top_n
        self._system_override = system
        self._max_bundle_recompositions = max(1, max_bundle_recompositions)
        self._allow_bundle_fallback = allow_bundle_fallback
        self._bundle_composer = BundleComposer(allow_singleton_fallback=allow_bundle_fallback)
        self._last_runtime: TranslationRuntimeResult | None = None

    @property
    def last_runtime(self) -> TranslationRuntimeResult | None:
        return self._last_runtime

    async def translate(
        self,
        scored_candidates: list[ScoredCandidate],
        structure: ProblemStructure,
        top_n: int | None = None,
        guidance: TranslationGuidance | None = None,
    ) -> list[Translation]:
        """
        Translate the top-N scored candidates into target-domain architectures.

        Parameters
        ----------
        scored_candidates:
            Sorted list of ``ScoredCandidate`` from Stage 3 (best first).
        structure:
            The ``ProblemStructure`` from Stage 1.
        top_n:
            Override the instance's top_n setting.

        Returns
        -------
        list[Translation]
            Translations sorted by source candidate's combined_score.
        """
        n = top_n if top_n is not None else self._top_n
        candidates = scored_candidates[:n]

        if not candidates:
            return []

        logger.info("Translating top %d candidates", len(candidates))
        t_start = time.monotonic()

        bundle_group = self._select_bundle_group(candidates)
        if bundle_group is not None:
            bundle_proof, bundle_members = bundle_group
            translations = await self._translate_bundle_group(
                bundle_proof,
                bundle_members,
                candidates,
                structure,
                guidance=guidance,
            )
            duration = time.monotonic() - t_start
            total_cost = sum(t.cost_usd for t in translations)
            logger.info(
                "Translation complete | count=%d duration=%.1fs cost=$%.4f mode=bundle",
                len(translations),
                duration,
                total_cost,
            )
            return translations

        tasks = [
            self._translate_candidate(candidate, structure, guidance=guidance)
            for candidate in candidates
        ]
        results = await gather_with_semaphore(
            tasks,
            ParallelConfig(
                max_concurrent=min(3, len(tasks)),
                timeout_per_task=_timeout_seconds(self._harness),
            ),
        )

        translations: list[Translation] = []
        for candidate, result in zip(candidates, results, strict=True):
            if not result.success:
                logger.warning(
                    "Translation failed for %s: %s",
                    candidate.source_domain,
                    result.error,
                )
                continue
            if result.value is not None:
                translations.append(result.value)

        # Sort by branch-aware rank when present, otherwise by combined score.
        translations.sort(
            key=lambda t: getattr(t.source_candidate, "branch_rank_score", t.combined_score),
            reverse=True,
        )

        duration = time.monotonic() - t_start
        total_cost = sum(t.cost_usd for t in translations)
        self._last_runtime = TranslationRuntimeResult(
            retrieval_mode="singleton",
            translations=list(translations),
        )
        logger.info(
            "Translation complete | count=%d duration=%.1fs cost=$%.4f",
            len(translations),
            duration,
            total_cost,
        )

        return translations

    def _select_bundle_group(
        self,
        candidates: list[ScoredCandidate],
    ) -> tuple[Any, list[ScoredCandidate]] | None:
        grouped: dict[str, list[ScoredCandidate]] = {}
        bundle_by_id: dict[str, Any] = {}
        for candidate in candidates:
            bundle = getattr(candidate, "bundle_proof", None)
            if bundle is None:
                continue
            bundle_id = str(getattr(bundle, "bundle_id", ""))
            grouped.setdefault(bundle_id, []).append(candidate)
            bundle_by_id[bundle_id] = bundle
        if not grouped:
            return None
        ranked_bundle_id = max(
            grouped,
            key=lambda bundle_id: (
                float(getattr(bundle_by_id[bundle_id], "proof_confidence", 0.0)),
                len(grouped[bundle_id]),
            ),
        )
        return bundle_by_id[ranked_bundle_id], grouped[ranked_bundle_id]

    async def _translate_bundle_group(
        self,
        bundle_proof: Any,
        bundle_candidates: list[ScoredCandidate],
        all_candidates: list[ScoredCandidate],
        structure: ProblemStructure,
        *,
        guidance: TranslationGuidance | None = None,
    ) -> list[Translation]:
        pending = {candidate.lens_id: candidate for candidate in bundle_candidates}
        runtime = TranslationRuntimeResult(retrieval_mode="bundle", bundle_proof=bundle_proof)
        invalidated: set[str] = set()

        available_lens_ids = tuple(pending.keys())
        missing_lens_ids = tuple(
            lens_id
            for lens_id in getattr(bundle_proof, "active_lens_ids", ())
            if lens_id not in set(available_lens_ids)
        )
        active_bundle = bundle_proof
        if missing_lens_ids:
            recomposition = self._bundle_composer.recompose(
                bundle_proof,
                structure,
                invalidated_lens_ids=missing_lens_ids,
                reason="bundle member missing before translation",
            )
            runtime.recomposition_events.append(recomposition.to_dict())
            active_bundle = recomposition.new_bundle
            invalidated.update(recomposition.invalidated_lens_ids)

        current_reference_state = build_reference_state(structure)
        if active_bundle is not None:
            continuous = (
                getattr(active_bundle, "reference_signature", "")
                == current_reference_state.reference_signature
                and getattr(active_bundle, "research_signature", "")
                == current_reference_state.research_signature
            )
            if not continuous:
                runtime.recomposition_events.append(
                    {
                        "original_bundle_id": getattr(active_bundle, "bundle_id", ""),
                        "invalidated_lens_ids": list(getattr(active_bundle, "active_lens_ids", ())),
                        "reason": "reference generation or research state changed after bundle proofing",
                        "new_bundle": None,
                        "fallback_required": True,
                    }
                )
                invalidated.update(getattr(active_bundle, "active_lens_ids", ()))
                active_bundle = None

        translations: list[Translation] = []
        recompositions = 0

        while True:
            if active_bundle is None:
                break
            order = [
                lens_id
                for lens_id in getattr(active_bundle, "translation_order", ())
                if lens_id in pending and lens_id not in invalidated
            ]
            if not order:
                break

            lens_id = order[0]
            candidate = pending.pop(lens_id)
            try:
                translation = await self._translate_candidate(
                    candidate,
                    structure,
                    bundle_proof=active_bundle,
                    previous_translation=translations[-1] if translations else None,
                    guidance=guidance,
                )
            except TranslationError as exc:
                invalidated.add(lens_id)
                runtime.recomposition_events.append(
                    {
                        "original_bundle_id": getattr(active_bundle, "bundle_id", ""),
                        "invalidated_lens_ids": [lens_id],
                        "reason": f"Translation error: {exc}",
                        "new_bundle": None,
                        "fallback_required": True,
                    }
                )
                active_bundle = None
                break
            guard = evaluate_handoff_guards(
                structure=structure,
                candidate=candidate,
                translation=translation,
                bundle_proof=active_bundle,
                previous_translation=translations[-1] if translations else None,
                current_reference_state=build_reference_state(
                    structure,
                    branch_genome=getattr(candidate, "branch_genome", None),
                ),
            )
            translation.guard_results.append(guard)
            translation.guard_failed = not guard.passed
            translation.recomposition_events = list(runtime.recomposition_events)
            runtime.guard_history.append(guard)
            if not guard.passed:
                invalidated.update(guard.invalidated_lens_ids)
                if recompositions >= self._max_bundle_recompositions:
                    runtime.recomposition_events.append(
                        {
                            "original_bundle_id": getattr(active_bundle, "bundle_id", ""),
                            "invalidated_lens_ids": list(guard.invalidated_lens_ids),
                            "reason": "max bundle recompositions reached",
                            "new_bundle": None,
                            "fallback_required": True,
                        }
                    )
                    active_bundle = None
                    break
                recomposition = self._bundle_composer.recompose(
                    active_bundle,
                    structure,
                    invalidated_lens_ids=guard.invalidated_lens_ids,
                    reason=guard.summary(),
                )
                runtime.recomposition_events.append(recomposition.to_dict())
                recompositions += 1
                active_bundle = recomposition.new_bundle
                if active_bundle is None:
                    break
                continue

            translations.append(translation)

        translated_lens_ids = {translation.lens_id for translation in translations}
        fallback_candidates = [
            candidate
            for candidate in all_candidates
            if candidate.lens_id not in invalidated and candidate.lens_id not in translated_lens_ids
        ]
        if (
            self._allow_bundle_fallback
            and (not translations or active_bundle is None)
            and fallback_candidates
        ):
            runtime.fallback_used = True
            for candidate in fallback_candidates[: self._top_n]:
                if candidate.lens_id in invalidated:
                    continue
                translation = await self._translate_candidate(
                    candidate,
                    structure,
                    force_singleton=True,
                    guidance=guidance,
                )
                translation.recomposition_events = list(runtime.recomposition_events)
                translations.append(translation)
                if len(translations) >= self._top_n:
                    break

        translations.sort(
            key=lambda t: getattr(t.source_candidate, "branch_rank_score", t.combined_score),
            reverse=True,
        )
        runtime.bundle_proof = active_bundle
        runtime.invalidated_lens_ids = tuple(sorted(invalidated))
        runtime.translations = list(translations)
        self._last_runtime = runtime
        return translations

    async def _translate_candidate(
        self,
        candidate: ScoredCandidate,
        structure: ProblemStructure,
        *,
        bundle_proof: Any | None = None,
        previous_translation: Translation | None = None,
        force_singleton: bool = False,
        guidance: TranslationGuidance | None = None,
    ) -> Translation:
        """Translate a single candidate with cognitive interference active."""
        t_start = time.monotonic()
        lens = candidate.lens_used

        # Build the interference lens from the candidate's source lens
        # ForgeLens is imported at module level for test patchability
        forge_lens = ForgeLens(
            name=lens.name,
            domain=lens.domain,
            axioms=lens.axioms,
            injection_prompt=lens.injection_prompt,
        )

        # Build a per-candidate harness config with interference active
        # HarnessConfig and DeepForgeHarness are module-level imports
        config = HarnessConfig(
            lenses=[forge_lens],
            use_interference=True,
            use_pruner=False,  # Pruner not needed for translation
            use_pressure=_pressure_enabled(self._harness),
            max_pressure_rounds=self._harness.config.max_pressure_rounds,
            injection_strategy=InjectionStrategy.FULL,
            max_tokens=self._harness.config.max_tokens,
            temperature=0.7,  # Higher temperature for creative translation
        )

        constraints_text = "\n".join(f"• {c}" for c in structure.constraints[:6])
        axioms_text = "\n".join(f"• {a}" for a in lens.axioms[:5])

        # Build banned baselines section if available
        banned = getattr(self, "_banned_baselines", None) or []
        if banned:
            banned_text = "\nBANNED BASELINES — these obvious approaches are NOT acceptable:\n"
            banned_text += "\n".join(f"- {b}" for b in banned[:5])
            banned_text += "\n"
        else:
            banned_text = ""

        branch_commitments_section = ""
        branch = getattr(candidate, "branch_genome", None)
        if branch is not None:
            commitment_lines = "\n".join(
                f"- [{commitment.kind.value}] {commitment.statement}"
                for commitment in branch.commitments[:8]
            )
            recovery_lines = (
                "\n".join(
                    (
                        f"- [{operator.kind.value}] trigger: {operator.trigger}; "
                        f"intervention: {operator.intervention}; preserve: {operator.preservation_goal}"
                    )
                    for operator in branch.recovery_operators[:4]
                )
                or "- none"
            )
            open_questions = (
                "\n".join(f"- {question}" for question in branch.open_questions[:4]) or "- none"
            )
            rejected_patterns = (
                "\n".join(f"- {pattern}" for pattern in branch.rejected_patterns[:4]) or "- none"
            )
            branch_commitments_section = (
                "\nPARTIAL BRANCH COMMITMENTS:\n"
                "Treat these as the currently accepted structural commitments for this branch.\n"
                "Preserve them where possible while resolving the open questions in a non-baseline way.\n"
                f"{commitment_lines}\n"
                "ACTIVE RECOVERY OPERATORS:\n"
                f"{recovery_lines}\n"
                "OPEN QUESTIONS TO RESOLVE:\n"
                f"{open_questions}\n"
                "RECENT REJECTION PRESSURE:\n"
                f"{rejected_patterns}\n"
                "You must preserve the recovery operators concretely and describe how the resulting architecture keeps future non-obvious options open rather than collapsing into the closest known pattern.\n"
            )

        active_bundle_proof = (
            None if force_singleton else (bundle_proof or getattr(candidate, "bundle_proof", None))
        )
        bundle_proof_section = self._bundle_proof_section(
            candidate,
            bundle_proof=active_bundle_proof,
        )
        handoff_section = self._handoff_section(
            previous_translation,
            structure=structure,
        )
        guidance_section = self._guidance_section(guidance)
        prompt = _TRANSLATE_PROMPT_TEMPLATE.format(
            original_problem=structure.original_problem,
            banned_baselines_section=banned_text,
            structure=structure.structure,
            mathematical_shape=structure.mathematical_shape,
            constraints=constraints_text or "• (none specified)",
            source_domain=candidate.source_domain,
            source_solution=candidate.source_solution,
            mechanism=candidate.mechanism,
            lens_axioms=axioms_text,
            fidelity=candidate.structural_fidelity,
            distance=candidate.domain_distance,
            guidance_section=guidance_section,
            branch_commitments_section=branch_commitments_section,
            bundle_proof_section=bundle_proof_section,
            handoff_section=handoff_section,
        )

        # Create a temporary harness with the interference lens active
        # DeepForgeHarness is module-level import (patchable in tests)
        interference_harness = DeepForgeHarness(
            adapter=self._harness.adapter,
            config=config,
        )

        translate_system = (
            self._system_override if self._system_override is not None else _TRANSLATE_SYSTEM
        )
        result = await interference_harness.forge(
            prompt,
            system=translate_system,
            max_tokens=config.max_tokens,
            temperature=0.7,
        )

        parsed_raw = result.output
        if config.use_pressure:
            parsed_raw = await self._deterministic_schema_pass(
                parsed_raw, system_override=translate_system
            )

        parsed = self.parse_translation(parsed_raw)
        translation = self._build_translation(
            parsed=parsed,
            candidate=candidate,
            structure=structure,
            trace=result.trace,
            started_at=t_start,
            bundle_proof=active_bundle_proof,
            force_singleton=force_singleton,
            fallback_name=f"{lens.name}-Inspired Solution",
        )

        logger.info(
            "Translated [%s] | mappings=%d limitations=%d cost=$%.4f",
            translation.invention_name,
            len(translation.mapping),
            len(translation.limitations),
            translation.cost_usd,
        )
        return translation

    async def reforge(
        self,
        *,
        prompt: str,
        structure: ProblemStructure,
        source_translation: Translation,
        system: str | None = None,
    ) -> Translation:
        """Run a guided reforge using the translator's base harness."""
        t_start = time.monotonic()
        result = await self._harness.forge(
            prompt,
            system=system,
            max_tokens=self._harness.config.max_tokens,
            temperature=0.7,
        )
        parsed_raw = result.output
        if _pressure_enabled(self._harness):
            parsed_raw = await self._deterministic_schema_pass(parsed_raw, system_override=system)

        parsed = self.parse_translation(parsed_raw)
        translation = self._build_translation(
            parsed=parsed,
            candidate=source_translation.source_candidate,
            structure=structure,
            trace=result.trace,
            started_at=t_start,
            bundle_proof=source_translation.bundle_proof,
            force_singleton=source_translation.selection_mode == "singleton_fallback",
            fallback_name=source_translation.invention_name or "Reforged invention",
        )
        translation.bundle_lineage = source_translation.bundle_lineage
        translation.selection_mode = source_translation.selection_mode
        translation.bundle_role = source_translation.bundle_role
        translation.reference_signature = source_translation.reference_signature
        translation.research_signature = source_translation.research_signature
        translation.branch_signature = source_translation.branch_signature
        translation.guard_results = list(source_translation.guard_results)
        translation.guard_failed = source_translation.guard_failed
        translation.recomposition_events = list(source_translation.recomposition_events)
        translation.pantheon_reforge_metadata = parsed.get("pantheon_reforge", {})
        return translation

    @staticmethod
    def _bundle_proof_section(
        candidate: ScoredCandidate,
        *,
        bundle_proof: Any | None,
    ) -> str:
        if bundle_proof is None:
            return ""
        conditions = getattr(bundle_proof, "conditional_requirements", {}).get(
            candidate.lens_id, ()
        )
        critical = (
            "yes"
            if candidate.lens_id in set(getattr(bundle_proof, "critical_lens_ids", ()))
            else "no"
        )
        return (
            "\nACTIVE LENS BUNDLE PROOF:\n"
            f"- bundle_id: {getattr(bundle_proof, 'bundle_id', '')}\n"
            f"- active_lenses: {', '.join(getattr(bundle_proof, 'active_lens_ids', ()))}\n"
            f"- derived_bundle_signature: {', '.join(getattr(getattr(bundle_proof, 'derived_card', None), 'mechanism_signature', [])[:8])}\n"
            f"- proof_confidence: {getattr(bundle_proof, 'proof_confidence', 0.0):.2f}\n"
            f"- current_lens_role: {getattr(candidate, 'bundle_role', '') or 'support'}\n"
            f"- critical_for_bundle: {critical}\n"
            f"- conditional_requirements_for_this_lens: {', '.join(conditions) or 'none'}\n"
            "- preserve compatibility with the active bundle instead of re-solving the full problem from scratch.\n"
        )

    @staticmethod
    def _handoff_section(
        previous_translation: Translation | None,
        *,
        structure: ProblemStructure,
    ) -> str:
        if previous_translation is None:
            return ""
        constraint_lines = (
            "\n".join(f"- {constraint}" for constraint in structure.constraints[:4]) or "- none"
        )
        return (
            "\nPREVIOUS BUNDLE HANDOFF CONTEXT:\n"
            f"- previous_invention: {previous_translation.invention_name}\n"
            f"- previous_key_insight: {previous_translation.key_insight}\n"
            f"- preserve_constraints:\n{constraint_lines}\n"
            "- reset the abstraction to target-domain language instead of carrying over source-domain vocabulary.\n"
            "- if the new architecture depends on the previous lens, make that dependency explicit rather than implicit.\n"
        )

    @staticmethod
    def _guidance_section(guidance: TranslationGuidance | None) -> str:
        if guidance is None or not guidance.has_content():
            return ""

        def _items(values: list[str]) -> str:
            return "\n".join(f"- {value}" for value in values[:6]) or "- none"

        return (
            "\nPIPELINE GUIDANCE (apply during first-pass invention, not as post-hoc commentary):\n"
            "ATHENA CANON:\n"
            f"- structural_form: {guidance.structural_form or 'n/a'}\n"
            f"- mandatory_constraints:\n{_items(guidance.mandatory_constraints)}\n"
            f"- anti_goals:\n{_items(guidance.anti_goals)}\n"
            f"- success_criteria:\n{_items(guidance.success_criteria)}\n"
            f"- false_framings_to_avoid:\n{_items(guidance.false_framings)}\n"
            "HERMES DOSSIER:\n"
            f"- repo_reality_summary: {guidance.reality_summary or 'n/a'}\n"
            f"- ecosystem_constraints:\n{_items(guidance.ecosystem_constraints)}\n"
            f"- user_operator_constraints:\n{_items(guidance.user_operator_constraints)}\n"
            f"- adoption_risks:\n{_items(guidance.adoption_risks)}\n"
            f"- implementation_leverage_points:\n{_items(guidance.implementation_leverage_points)}\n"
            "- preserve novelty while satisfying the canon and reality constraints from the first draft.\n"
        )

    def parse_translation(self, raw: str) -> dict[str, Any]:
        """Public wrapper for translation JSON parsing."""
        return self._parse_translation(raw)

    async def _deterministic_schema_pass(
        self, raw_forge_output: str, system_override: str | None = None
    ) -> str:
        """Run a deterministic two-pass extraction on raw forge output to ensure JSON schema adherence."""
        prompt = (
            "Extract the following raw invention into the required JSON schema.\n"
            "DO NOT alter the architecture, mechanism, or creative aspects.\n"
            "ONLY output valid JSON matching the translation schema.\n\n"
            f"<raw_output>\n{raw_forge_output}\n</raw_output>"
        )
        sys_prompt = system_override if system_override is not None else _TRANSLATE_SYSTEM
        result = await self._harness.adapter.generate(
            prompt,
            system=sys_prompt,
            max_tokens=self._harness.config.max_tokens,
            temperature=0.0,
        )
        return result.text

    def _build_translation(
        self,
        *,
        parsed: dict[str, Any],
        candidate: ScoredCandidate,
        structure: ProblemStructure,
        trace: ForgeTrace | None,
        started_at: float,
        bundle_proof: Any | None,
        force_singleton: bool,
        fallback_name: str,
    ) -> Translation:
        mappings: list[ElementMapping] = []
        for elem in parsed.get("mapping", {}).get("elements", []):
            if isinstance(elem, dict):
                mappings.append(
                    ElementMapping(
                        source_element=elem.get("source_element", ""),
                        target_element=elem.get("target_element", ""),
                        mechanism=elem.get("mechanism", ""),
                    )
                )

        arch = parsed.get("architecture", "")
        if isinstance(arch, dict):
            arch = json.dumps(arch, indent=2)
        elif not isinstance(arch, str):
            arch = str(arch) if arch else ""

        key_ins = parsed.get("key_insight", "")
        if not isinstance(key_ins, str):
            key_ins = str(key_ins) if key_ins else ""

        impl_notes = parsed.get("implementation_notes", "")
        if not isinstance(impl_notes, str):
            impl_notes = str(impl_notes) if impl_notes else ""

        math_proof = parsed.get("mathematical_proof", "")
        if not isinstance(math_proof, str):
            math_proof = str(math_proof) if math_proof else ""

        lims = parsed.get("limitations", [])
        if isinstance(lims, str):
            lims = [lims]
        elif not isinstance(lims, list):
            lims = [str(lims)] if lims else []

        recovery_commitments = parsed.get("recovery_commitments", [])
        if isinstance(recovery_commitments, str):
            recovery_commitments = [recovery_commitments]
        elif not isinstance(recovery_commitments, list):
            recovery_commitments = []
        recovery_commitments = [
            str(commitment) for commitment in recovery_commitments if commitment
        ]

        future_option_preservation = parsed.get("future_option_preservation", "")
        if not isinstance(future_option_preservation, str):
            future_option_preservation = (
                str(future_option_preservation) if future_option_preservation else ""
            )

        reference_state = build_reference_state(
            structure,
            branch_genome=getattr(candidate, "branch_genome", None),
        )
        trace_cost = getattr(trace, "total_cost_usd", 0.0) if trace is not None else 0.0

        return Translation(
            invention_name=parsed.get("invention_name", fallback_name),
            mapping=mappings,
            architecture=arch,
            mathematical_proof=math_proof,
            limitations=lims,
            implementation_notes=impl_notes,
            key_insight=key_ins,
            source_candidate=candidate,
            phase1_abstract_mechanism=parsed.get("phase1_abstract_mechanism", ""),
            phase2_target_architecture=parsed.get("phase2_target_architecture", ""),
            mechanism_is_decorative=bool(parsed.get("mechanism_is_decorative", False)),
            known_pattern_if_decorative=parsed.get("known_pattern_if_decorative", ""),
            mechanism_differs_from_baseline=parsed.get("mechanism_differs_from_baseline", ""),
            subtraction_test=parsed.get("subtraction_test", ""),
            baseline_comparison=parsed.get("baseline_comparison", ""),
            recovery_commitments=recovery_commitments,
            future_option_preservation=future_option_preservation,
            cost_usd=trace_cost,
            duration_seconds=time.monotonic() - started_at,
            trace=trace,
            bundle_proof=bundle_proof,
            bundle_lineage=None if force_singleton else getattr(candidate, "bundle_lineage", None),
            selection_mode="singleton_fallback"
            if force_singleton
            else str(getattr(candidate, "selection_mode", "singleton")),
            bundle_role="" if force_singleton else str(getattr(candidate, "bundle_role", "")),
            reference_signature=reference_state.reference_signature,
            research_signature=reference_state.research_signature,
            branch_signature=reference_state.branch_signature,
        )

    def _parse_translation(self, raw: str) -> dict[str, Any]:
        """Parse the translation JSON output.

        Raises ``TranslationError`` if the model output contains no
        parseable JSON — callers must handle this to avoid producing
        fake-looking successful translations from malformed output.
        """
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned, count=1)
            cleaned = re.sub(r"\n?```\s*$", "", cleaned)

        json_blob = extract_outermost_json_object(cleaned)
        if json_blob is None:
            raise TranslationError(
                f"No parseable JSON in model output (first 300 chars): {raw[:300]}"
            )

        data = loads_lenient(json_blob, default=None, label="translator")
        if data is None or not isinstance(data, dict):
            raise TranslationError(
                f"JSON parse failed on model output (first 300 chars): {raw[:300]}"
            )

        # Require critical fields — fail if the JSON parsed but is
        # substantively empty (no invention name AND no architecture)
        has_name = (
            bool(data.get("invention_name", "").strip())
            if isinstance(data.get("invention_name"), str)
            else bool(data.get("invention_name"))
        )
        has_arch = (
            bool(data.get("architecture", "").strip())
            if isinstance(data.get("architecture"), str)
            else bool(data.get("architecture"))
        )
        has_phase2 = (
            bool(data.get("phase2_target_architecture", "").strip())
            if isinstance(data.get("phase2_target_architecture"), str)
            else bool(data.get("phase2_target_architecture"))
        )
        if not has_name and not has_arch and not has_phase2:
            raise TranslationError(
                "Model returned JSON but with no substantive content "
                "(missing invention_name, architecture, and phase2_target_architecture)"
            )

        # Defaults for optional fields only — JSON DID parse successfully
        data.setdefault("invention_name", "Unnamed Invention")
        data.setdefault("architecture", "")
        data.setdefault("limitations", [])
        data.setdefault("key_insight", "")
        data.setdefault("implementation_notes", "")
        data.setdefault("mathematical_proof", "")
        data.setdefault("phase1_abstract_mechanism", "")
        data.setdefault("phase2_target_architecture", "")
        data.setdefault("mechanism_is_decorative", False)
        data.setdefault("known_pattern_if_decorative", "")
        data.setdefault("mechanism_differs_from_baseline", "")
        data.setdefault("subtraction_test", "")
        data.setdefault("baseline_comparison", "")
        data.setdefault("recovery_commitments", [])
        data.setdefault("future_option_preservation", "")

        # Use phase2 as architecture if architecture is missing/empty
        if not data.get("architecture") and data.get("phase2_target_architecture"):
            data["architecture"] = data["phase2_target_architecture"]

        if "mapping" not in data or not isinstance(data.get("mapping"), dict):
            data["mapping"] = {"elements": []}

        if isinstance(data.get("recovery_commitments"), str):
            data["recovery_commitments"] = [data["recovery_commitments"]]
        elif not isinstance(data.get("recovery_commitments"), list):
            data["recovery_commitments"] = []

        return data
