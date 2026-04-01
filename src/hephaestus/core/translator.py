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
from hephaestus.core.scorer import ScoredCandidate
from hephaestus.deepforge.harness import DeepForgeHarness, ForgeTrace, HarnessConfig
from hephaestus.deepforge.interference import InjectionStrategy, Lens
from hephaestus.deepforge.interference import Lens as ForgeLens

logger = logging.getLogger(__name__)


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

PHASE 2 — MECHANISM APPLICATION (target domain only, NO source domain language):
Now take the abstract mechanism from Phase 1 and build a concrete architecture
in the target domain. Do NOT reference the source domain at all. If you cannot
describe a novel architecture without mentioning the source domain, the transfer
is decorative and you must set mechanism_is_decorative to true.

CRITICAL SELF-TEST: After writing the architecture, ask: "Is this mechanism
already known in the target domain under a different name?" If yes, your
transfer added no value. Set mechanism_is_decorative to true and explain
what known pattern it collapses to.

You must output ONLY valid JSON matching this schema:
{
  "invention_name": "<short name — should describe the MECHANISM, not the source domain>",
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
  "baseline_comparison": "<Simplest conventional solution vs this invention's structural advantage>"
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
    cost_usd: float = 0.0
    duration_seconds: float = 0.0
    trace: ForgeTrace | None = None

    @property
    def source_domain(self) -> str:
        return self.source_candidate.source_domain

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


# ---------------------------------------------------------------------------
# Translator
# ---------------------------------------------------------------------------


class TranslationError(Exception):
    """Raised when translation fails for a candidate."""


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
    ) -> None:
        self._harness = harness
        self._top_n = top_n
        self._system_override = system

    async def translate(
        self,
        scored_candidates: list[ScoredCandidate],
        structure: ProblemStructure,
        top_n: int | None = None,
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

        import asyncio

        tasks = [
            self._translate_candidate(candidate, structure)
            for candidate in candidates
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        translations: list[Translation] = []
        for candidate, result in zip(candidates, results):
            if isinstance(result, Exception):
                logger.warning(
                    "Translation failed for %s: %s",
                    candidate.source_domain,
                    result,
                )
                continue
            if result is not None:
                translations.append(result)

        # Sort by combined score of source candidate
        translations.sort(key=lambda t: t.combined_score, reverse=True)

        duration = time.monotonic() - t_start
        total_cost = sum(t.cost_usd for t in translations)
        logger.info(
            "Translation complete | count=%d duration=%.1fs cost=$%.4f",
            len(translations),
            duration,
            total_cost,
        )

        return translations

    async def _translate_candidate(
        self,
        candidate: ScoredCandidate,
        structure: ProblemStructure,
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
            use_pruner=False,   # Pruner not needed for translation
            use_pressure=False, # Pressure not needed — interference is active
            injection_strategy=InjectionStrategy.FULL,
            max_tokens=16000,
            temperature=0.7,    # Higher temperature for creative translation
        )

        constraints_text = "\n".join(f"• {c}" for c in structure.constraints[:6])
        axioms_text = "\n".join(f"• {a}" for a in lens.axioms[:5])

        # Build banned baselines section if available
        banned = getattr(self, '_banned_baselines', None) or []
        if banned:
            banned_text = "\nBANNED BASELINES — these obvious approaches are NOT acceptable:\n"
            banned_text += "\n".join(f"- {b}" for b in banned[:5])
            banned_text += "\n"
        else:
            banned_text = ""

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
        )

        # Create a temporary harness with the interference lens active
        # DeepForgeHarness is module-level import (patchable in tests)
        interference_harness = DeepForgeHarness(
            adapter=self._harness.adapter,
            config=config,
        )

        translate_system = self._system_override if self._system_override is not None else _TRANSLATE_SYSTEM
        result = await interference_harness.forge(
            prompt,
            system=translate_system,
            max_tokens=16000,
            temperature=0.7,
        )

        parsed = self._parse_translation(result.output)

        # Build element mappings
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

        # Ensure all fields are strings (V2 prompt may cause dict returns)
        arch = parsed.get("architecture", "")
        if isinstance(arch, dict):
            import json as _json
            arch = _json.dumps(arch, indent=2)
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

        translation = Translation(
            invention_name=parsed.get("invention_name", f"{lens.name}-Inspired Solution"),
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
            cost_usd=result.trace.total_cost_usd,
            duration_seconds=time.monotonic() - t_start,
            trace=result.trace,
        )

        logger.info(
            "Translated [%s] | mappings=%d limitations=%d cost=$%.4f",
            translation.invention_name,
            len(translation.mapping),
            len(translation.limitations),
            translation.cost_usd,
        )
        return translation

    def _parse_translation(self, raw: str) -> dict[str, Any]:
        """Parse the translation JSON output."""
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned, count=1)
            cleaned = re.sub(r"\n?```\s*$", "", cleaned)

        json_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not json_match:
            raise TranslationError(f"No JSON in translation output: {raw[:300]}")

        try:
            data = json.loads(json_match.group())
        except json.JSONDecodeError as exc:
            raise TranslationError(f"JSON parse error in translation: {exc}") from exc

        # Ensure required fields exist with defaults
        data.setdefault("invention_name", "Cross-Domain Invention")
        data.setdefault("architecture", "Architecture generation failed")
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

        # Use phase2 as architecture if architecture is missing/empty
        if not data.get("architecture") and data.get("phase2_target_architecture"):
            data["architecture"] = data["phase2_target_architecture"]

        if "mapping" not in data or not isinstance(data.get("mapping"), dict):
            data["mapping"] = {"elements": []}

        return data
