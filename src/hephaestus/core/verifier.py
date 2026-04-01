"""
Stage 5: Novelty Verification.

Cross-model adversarial verification of each ``Translation``.

The verifier:
1. **Adversarial attack**: One model tries to invalidate the structural
   translation — finds logical flaws, structural incompatibilities, or
   prior art in the mapping.
2. **Prior art check**: Queries the ``PriorArtSearcher`` (if available)
   for existing patents/papers matching this specific cross-domain application.
3. **Structural validity assessment**: Evaluates whether the architecture is
   implementable and internally consistent.
4. **Implementation feasibility**: Checks whether the solution can be built
   with current technology.

Output: ``VerifiedInvention`` with novelty_score, adversarial notes, prior art
status, and feasibility rating.

Usage::

    verifier = NoveltyVerifier(attack_harness, defend_harness)
    inventions = await verifier.verify(translations, structure)
    for inv in inventions:
        print(f"{inv.invention_name}: novelty={inv.novelty_score:.2f} "
              f"feasibility={inv.feasibility_rating}")
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

from hephaestus.core.decomposer import ProblemStructure
from hephaestus.core.translator import Translation
from hephaestus.deepforge.harness import DeepForgeHarness, ForgeTrace

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

_ATTACK_SYSTEM = """\
You are an adversarial structural critic. Your job is to find weaknesses,
contradictions, and failure modes in a proposed cross-domain invention.

Be rigorous and honest. Attack the structural mapping aggressively.
Find: logical inconsistencies, elements that don't actually map, where the
analogy is superficial metaphor rather than genuine structural isomorphism,
implementation impossibilities, and overlooked constraints.

Output ONLY valid JSON:
{
  "attack_valid": <bool — true if you found significant invalidating flaws>,
  "fatal_flaws": ["<flaw that would make the invention non-viable>", ...],
  "structural_weaknesses": ["<weakness in the mapping that doesn't invalidate but degrades quality>", ...],
  "strongest_objection": "<your single best attack on this invention>",
  "novelty_risk": <float 0.0-1.0 — probability that prior art exists for this>,
  "verdict": "<NOVEL | QUESTIONABLE | DERIVATIVE | INVALID>"
}
"""

_ATTACK_PROMPT_TEMPLATE = """\
PROPOSED INVENTION:
Name: {invention_name}
Source domain: {source_domain}
Key insight: {key_insight}

STRUCTURAL MAPPING:
{mapping_text}

ARCHITECTURE:
{architecture}

LIMITATIONS (as stated by inventor):
{limitations}

TARGET PROBLEM:
{original_problem}

Attack this invention rigorously. Find every flaw.
Return JSON only.
"""

_VALIDITY_SYSTEM = """\
You are a structural validity and feasibility assessor. Evaluate whether a
proposed cross-domain invention is:
1. Structurally valid — the mapping holds under scrutiny
2. Implementable — can be built with current technology
3. Genuinely novel — not a restatement of known approaches

Consider the adversarial critique provided.

Output ONLY valid JSON:
{
  "structural_validity": <float 0.0-1.0>,
  "implementation_feasibility": <float 0.0-1.0>,
  "novelty_score": <float 0.0-1.0>,
  "feasibility_rating": "<HIGH | MEDIUM | LOW | THEORETICAL>",
  "validity_notes": "<explanation of structural validity assessment>",
  "feasibility_notes": "<what would be needed to implement this>",
  "novelty_notes": "<why this is or isn't genuinely novel>",
  "recommended_next_steps": ["<concrete step 1>", "<step 2>", ...]
}
"""

_VALIDITY_PROMPT_TEMPLATE = """\
PROPOSED INVENTION: {invention_name}
SOURCE: {source_domain} → {target_description}

ARCHITECTURE:
{architecture}

ADVERSARIAL CRITIQUE:
Verdict: {verdict}
Fatal flaws: {fatal_flaws}
Strongest objection: {strongest_objection}
Novelty risk: {novelty_risk:.2f}

STRUCTURAL LIMITATIONS (self-reported):
{limitations}

Assess structural validity, feasibility, and novelty. Return JSON only.
"""


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class AdversarialResult:
    """Result of the adversarial attack on a translation."""

    attack_valid: bool
    fatal_flaws: list[str]
    structural_weaknesses: list[str]
    strongest_objection: str
    novelty_risk: float  # 0.0 = definitely novel, 1.0 = almost certainly exists
    verdict: str  # NOVEL | QUESTIONABLE | DERIVATIVE | INVALID


@dataclass
class VerifiedInvention:
    """
    The output of Stage 5 for a single translation.

    Attributes
    ----------
    invention_name:
        Name of the invention (from Translation).
    translation:
        The source ``Translation`` object.
    novelty_score:
        Combined novelty score (0.0–1.0). Higher = more novel.
    structural_validity:
        Structural validity assessment (0.0–1.0).
    implementation_feasibility:
        Feasibility assessment (0.0–1.0).
    feasibility_rating:
        Human-readable tier: HIGH | MEDIUM | LOW | THEORETICAL.
    adversarial_result:
        Full adversarial critique.
    prior_art_status:
        Summary of prior art search ("NO_PRIOR_ART_FOUND",
        "POSSIBLE_PRIOR_ART", "SEARCH_UNAVAILABLE").
    prior_art_report:
        Full PriorArtReport if search was performed, else None.
    verification_notes:
        Combined human-readable verification summary.
    validity_notes:
        Structural validity explanation.
    feasibility_notes:
        Implementation notes from verifier.
    novelty_notes:
        Novelty explanation.
    recommended_next_steps:
        Practical next steps for implementation.
    verification_cost_usd:
        API cost for this verification.
    verification_duration_seconds:
        Wall-clock time.
    trace:
        DeepForge trace.
    """

    invention_name: str
    translation: Translation
    novelty_score: float
    structural_validity: float
    implementation_feasibility: float
    feasibility_rating: str
    adversarial_result: AdversarialResult
    prior_art_status: str = "SEARCH_UNAVAILABLE"
    prior_art_report: Any = None
    verification_notes: str = ""
    validity_notes: str = ""
    feasibility_notes: str = ""
    novelty_notes: str = ""
    load_bearing_passed: bool = True  # from load_bearing_check
    load_bearing_notes: str = ""
    mechanism_differs_from_baseline: str = ""  # from translation
    subtraction_test: str = ""  # from translation
    baseline_comparison: str = ""  # from translation
    recommended_next_steps: list[str] = field(default_factory=list)
    verification_cost_usd: float = 0.0
    verification_duration_seconds: float = 0.0
    trace: ForgeTrace | None = None

    @property
    def source_domain(self) -> str:
        return self.translation.source_domain

    @property
    def is_viable(self) -> bool:
        """True if not fatally flawed and feasibility is at least MEDIUM."""
        no_fatal = not self.adversarial_result.fatal_flaws
        ok_feasibility = self.feasibility_rating in ("HIGH", "MEDIUM")
        return no_fatal and ok_feasibility

    @property
    def verdict(self) -> str:
        return self.adversarial_result.verdict

    def summary(self) -> str:
        return (
            f"[{self.invention_name}] "
            f"novelty={self.novelty_score:.2f} "
            f"validity={self.structural_validity:.2f} "
            f"feasibility={self.feasibility_rating} "
            f"verdict={self.verdict} "
            f"prior_art={self.prior_art_status}"
        )


# ---------------------------------------------------------------------------
# Verifier
# ---------------------------------------------------------------------------


class VerificationError(Exception):
    """Raised when verification fails critically."""


class NoveltyVerifier:
    """
    Stage 5 of the Genesis pipeline: Novelty Verification.

    Uses cross-model adversarial verification to assess the validity,
    novelty, and feasibility of each translation.

    Parameters
    ----------
    attack_harness:
        DeepForge harness used for the adversarial attack step.
        Ideally a different model than the one that built the translation.
    defend_harness:
        DeepForge harness used for the structural validity/feasibility
        assessment step.  Can be the same as attack_harness.
    run_prior_art:
        Whether to run the prior art search (default True, but gracefully
        falls back if the searcher is unavailable).
    """

    def __init__(
        self,
        attack_harness: DeepForgeHarness,
        defend_harness: DeepForgeHarness | None = None,
        run_prior_art: bool = True,
        system: str | None = None,
    ) -> None:
        self._attack_harness = attack_harness
        self._defend_harness = defend_harness or attack_harness
        self._run_prior_art = run_prior_art
        self._system_override = system
        self._prior_art_searcher: Any = None

        if run_prior_art:
            self._init_prior_art_searcher()

    def _init_prior_art_searcher(self) -> None:
        """Lazily initialise the prior art searcher with graceful fallback."""
        try:
            from hephaestus.output.prior_art import PriorArtSearcher
            self._prior_art_searcher = PriorArtSearcher()
            logger.info("Prior art searcher initialised")
        except ImportError:
            logger.warning("Prior art searcher not available (missing dependencies)")
        except Exception as exc:
            logger.warning("Prior art searcher init failed: %s", exc)

    async def verify(
        self,
        translations: list[Translation],
        structure: ProblemStructure,
    ) -> list[VerifiedInvention]:
        """
        Verify all translations adversarially.

        Parameters
        ----------
        translations:
            ``Translation`` list from Stage 4.
        structure:
            The ``ProblemStructure`` from Stage 1.

        Returns
        -------
        list[VerifiedInvention]
            Sorted by novelty_score descending.
        """
        if not translations:
            return []

        logger.info("Verifying %d translations", len(translations))
        t_start = time.monotonic()

        import asyncio

        tasks = [
            self._verify_translation(t, structure)
            for t in translations
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        inventions: list[VerifiedInvention] = []
        for translation, result in zip(translations, results):
            if isinstance(result, Exception):
                logger.warning(
                    "Verification failed for %s: %s",
                    translation.invention_name,
                    result,
                )
                # Include with low scores rather than dropping entirely
                inventions.append(
                    self._make_fallback_verified(translation)
                )
            else:
                if result is not None:
                    inventions.append(result)

        # Sort by novelty_score descending
        inventions.sort(key=lambda v: v.novelty_score, reverse=True)

        duration = time.monotonic() - t_start
        total_cost = sum(v.verification_cost_usd for v in inventions)
        logger.info(
            "Verification complete | inventions=%d duration=%.1fs cost=$%.4f",
            len(inventions),
            duration,
            total_cost,
        )

        return inventions

    async def _verify_translation(
        self,
        translation: Translation,
        structure: ProblemStructure,
    ) -> VerifiedInvention:
        """Full verification pipeline for a single translation."""
        t_start = time.monotonic()
        total_cost = 0.0

        # Step 1: Adversarial attack
        attack_result, attack_cost = await self._adversarial_attack(translation, structure)
        total_cost += attack_cost

        # Step 2: Prior art check (concurrent with or after attack)
        prior_art_status = "SEARCH_UNAVAILABLE"
        prior_art_report = None

        if self._run_prior_art and self._prior_art_searcher is not None:
            try:
                query = (
                    f"{translation.key_insight} "
                    f"{translation.source_domain} "
                    f"{structure.native_domain}"
                )
                prior_art_report = await self._prior_art_searcher.search(
                    query=query,
                    invention_name=translation.invention_name,
                )
                prior_art_status = prior_art_report.novelty_status
                logger.debug(
                    "Prior art for %s: %s",
                    translation.invention_name,
                    prior_art_status,
                )
            except Exception as exc:
                logger.warning("Prior art search failed for %s: %s", translation.invention_name, exc)
                prior_art_status = "SEARCH_UNAVAILABLE"

        # Step 3: Structural validity + feasibility assessment
        validity, validity_cost = await self._assess_validity(
            translation, structure, attack_result
        )
        total_cost += validity_cost

        # Step 3.5: Load-bearing domain check
        load_bearing_passed = True
        load_bearing_notes = ""
        try:
            from hephaestus.core.load_bearing_check import check_load_bearing_domains
            lb_result = await check_load_bearing_domains(translation)
            load_bearing_passed = lb_result.passed
            load_bearing_notes = lb_result.summary()
            if not load_bearing_passed:
                logger.info(
                    "Load-bearing check FAILED for %s: %s",
                    translation.invention_name,
                    "; ".join(lb_result.reasons[:2]),
                )
        except Exception as exc:
            logger.warning("Load-bearing check skipped for %s: %s", translation.invention_name, exc)
            load_bearing_notes = f"Check skipped: {exc}"

        # Step 4: Compute final novelty score
        novelty_score = self._compute_novelty_score(
            attack_result=attack_result,
            structural_validity=validity.get("structural_validity", 0.5),
            prior_art_status=prior_art_status,
            domain_distance=translation.domain_distance,
        )

        # Step 4.5: Apply load-bearing penalty
        if not load_bearing_passed:
            novelty_score *= 0.5  # 50% penalty for decorative domain transfer
            logger.info(
                "Novelty score penalized (load-bearing failed): %.2f for %s",
                novelty_score, translation.invention_name,
            )

        # Combine verification notes
        notes_parts = [
            f"Adversarial verdict: {attack_result.verdict}",
            f"Prior art: {prior_art_status}",
            f"Feasibility: {validity.get('feasibility_rating', 'UNKNOWN')}",
            f"Load-bearing: {'PASS' if load_bearing_passed else 'FAIL'}",
        ]
        if attack_result.strongest_objection:
            notes_parts.append(f"Main challenge: {attack_result.strongest_objection}")

        return VerifiedInvention(
            invention_name=translation.invention_name,
            translation=translation,
            novelty_score=novelty_score,
            structural_validity=float(validity.get("structural_validity", 0.5)),
            implementation_feasibility=float(validity.get("implementation_feasibility", 0.5)),
            feasibility_rating=str(validity.get("feasibility_rating", "MEDIUM")),
            adversarial_result=attack_result,
            prior_art_status=prior_art_status,
            prior_art_report=prior_art_report,
            verification_notes="\n".join(notes_parts),
            validity_notes=str(validity.get("validity_notes", "")),
            feasibility_notes=str(validity.get("feasibility_notes", "")),
            novelty_notes=str(validity.get("novelty_notes", "")),
            load_bearing_passed=load_bearing_passed,
            load_bearing_notes=load_bearing_notes,
            mechanism_differs_from_baseline=translation.mechanism_differs_from_baseline,
            subtraction_test=translation.subtraction_test,
            baseline_comparison=translation.baseline_comparison,
            recommended_next_steps=list(validity.get("recommended_next_steps", [])),
            verification_cost_usd=total_cost,
            verification_duration_seconds=time.monotonic() - t_start,
        )

    async def _adversarial_attack(
        self,
        translation: Translation,
        structure: ProblemStructure,
    ) -> tuple[AdversarialResult, float]:
        """Run the adversarial attack model on the translation."""
        mapping_text = "\n".join(
            f"  {m.source_element} → {m.target_element}: {m.mechanism}"
            for m in translation.mapping[:8]
        )
        limitations_text = "\n".join(f"• {l}" for l in translation.limitations[:5])

        prompt = _ATTACK_PROMPT_TEMPLATE.format(
            invention_name=translation.invention_name,
            source_domain=translation.source_domain,
            key_insight=translation.key_insight,
            mapping_text=mapping_text or "  (no mapping provided)",
            architecture=translation.architecture[:1500],
            limitations=limitations_text or "• (none listed)",
            original_problem=structure.original_problem,
        )

        attack_system = self._system_override if self._system_override is not None else _ATTACK_SYSTEM
        result = await self._attack_harness.forge(
            prompt,
            system=attack_system,
            max_tokens=16000,
            temperature=0.4,
        )

        parsed = self._parse_attack(result.output)
        attack_result = AdversarialResult(
            attack_valid=bool(parsed.get("attack_valid", False)),
            fatal_flaws=list(parsed.get("fatal_flaws", [])),
            structural_weaknesses=list(parsed.get("structural_weaknesses", [])),
            strongest_objection=str(parsed.get("strongest_objection", "")),
            novelty_risk=float(parsed.get("novelty_risk", 0.3)),
            verdict=str(parsed.get("verdict", "QUESTIONABLE")),
        )

        return attack_result, result.trace.total_cost_usd

    async def _assess_validity(
        self,
        translation: Translation,
        structure: ProblemStructure,
        attack: AdversarialResult,
    ) -> tuple[dict[str, Any], float]:
        """Assess structural validity and feasibility post-attack."""
        limitations_text = "\n".join(f"• {l}" for l in translation.limitations[:5])
        fatal_flaws_text = "\n".join(f"• {f}" for f in attack.fatal_flaws[:3])

        target_desc = f"{structure.native_domain}: {structure.mathematical_shape[:80]}"

        prompt = _VALIDITY_PROMPT_TEMPLATE.format(
            invention_name=translation.invention_name,
            source_domain=translation.source_domain,
            target_description=target_desc,
            architecture=translation.architecture[:1500],
            verdict=attack.verdict,
            fatal_flaws=fatal_flaws_text or "• None identified",
            strongest_objection=attack.strongest_objection or "None",
            novelty_risk=attack.novelty_risk,
            limitations=limitations_text or "• (none stated)",
        )

        validity_system = self._system_override if self._system_override is not None else _VALIDITY_SYSTEM
        result = await self._defend_harness.forge(
            prompt,
            system=validity_system,
            max_tokens=16000,
            temperature=0.3,
        )

        parsed = self._parse_validity(result.output)
        return parsed, result.trace.total_cost_usd

    def _compute_novelty_score(
        self,
        attack_result: AdversarialResult,
        structural_validity: float,
        prior_art_status: str,
        domain_distance: float,
    ) -> float:
        """
        Compute the final novelty score from all verification components.

        Formula:
            novelty = validity × (1 - novelty_risk × 0.5) × prior_art_multiplier
            × distance_bonus
        """
        # Prior art multiplier
        prior_art_multipliers = {
            "NO_PRIOR_ART_FOUND": 1.0,
            "POSSIBLE_PRIOR_ART": 0.6,
            "SEARCH_UNAVAILABLE": 0.8,  # Benefit of doubt
            "PRIOR_ART_FOUND": 0.2,
        }
        prior_mult = prior_art_multipliers.get(prior_art_status, 0.8)

        # Novelty risk penalty from adversarial attack
        novelty_risk_penalty = 1.0 - (attack_result.novelty_risk * 0.5)

        # Fatal flaw penalty
        fatal_penalty = 0.5 if attack_result.attack_valid and attack_result.fatal_flaws else 1.0

        # Distance bonus (superlinear: more distant = more novel by default)
        distance_bonus = 0.7 + 0.3 * domain_distance

        raw = (
            structural_validity
            * novelty_risk_penalty
            * prior_mult
            * fatal_penalty
            * distance_bonus
        )

        import numpy as np
        return float(np.clip(raw, 0.0, 1.0))

    def _parse_attack(self, raw: str) -> dict[str, Any]:
        """Parse adversarial attack JSON."""
        return self._parse_json(raw, default={"attack_valid": False, "verdict": "QUESTIONABLE"})

    def _parse_validity(self, raw: str) -> dict[str, Any]:
        """Parse validity assessment JSON."""
        return self._parse_json(
            raw,
            default={
                "structural_validity": 0.5,
                "implementation_feasibility": 0.5,
                "feasibility_rating": "MEDIUM",
            },
        )

    @staticmethod
    def _parse_json(raw: str, default: dict[str, Any]) -> dict[str, Any]:
        """Generic JSON extraction with fallback to defaults."""
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned, count=1)
            cleaned = re.sub(r"\n?```\s*$", "", cleaned)

        json_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not json_match:
            logger.warning("No JSON found in verifier response, using defaults")
            return dict(default)

        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            return dict(default)

    def _make_fallback_verified(self, translation: Translation) -> VerifiedInvention:
        """Create a low-confidence VerifiedInvention when verification errors out."""
        fallback_attack = AdversarialResult(
            attack_valid=False,
            fatal_flaws=[],
            structural_weaknesses=["Verification process encountered errors"],
            strongest_objection="Verification incomplete",
            novelty_risk=0.5,
            verdict="QUESTIONABLE",
        )
        return VerifiedInvention(
            invention_name=translation.invention_name,
            translation=translation,
            novelty_score=0.3,
            structural_validity=0.5,
            implementation_feasibility=0.5,
            feasibility_rating="LOW",
            adversarial_result=fallback_attack,
            prior_art_status="SEARCH_UNAVAILABLE",
            verification_notes="Verification failed; fallback scores applied",
        )
