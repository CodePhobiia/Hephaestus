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
from hephaestus.lenses.cells import build_reference_state

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

IMPORTANT DISTINCTION for novelty_risk:
- The question is NOT "does the source-domain concept exist in academic literature?"
  (Of course it does — that's where we found it.)
- The question IS "has someone ALREADY applied this specific mechanism to THIS
  specific target domain problem?" If the Kuramoto model exists but nobody has
  used it for rate limiting, novelty_risk should be LOW.
- Prior art means: someone already built THIS combination, not that the parts
  exist separately.

Output ONLY valid JSON:
{
  "attack_valid": <bool — true if you found significant STRUCTURAL flaws>,
  "fatal_flaws": ["<flaw that would make the invention structurally non-viable>", ...],
  "structural_weaknesses": ["<genuine weakness in the mechanism, not just 'this is hard'>", ...],
  "strongest_objection": "<your single best STRUCTURAL attack>",
  "novelty_risk": <float 0.0-1.0 — probability that THIS SPECIFIC COMBINATION already exists as prior art>,
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
You are a structural validity, feasibility, and GENUINE NOVELTY assessor.

Evaluate whether a proposed cross-domain invention is:
1. Structurally valid — the mapping holds under scrutiny
2. Implementable — can be built with current technology
3. Genuinely novel — not a restatement of known approaches IN THE TARGET DOMAIN

CRITICAL NOVELTY TESTS (apply all three):

TEST 1 - Domain Vocabulary Removal: Describe the invention's mechanism using
ONLY target-domain language. If the description is coherent and describes a
known pattern, the novelty is LOW. If removing source-domain vocabulary makes
the mechanism incoherent or impossible to describe, the novelty is HIGH.

TEST 2 - Baseline Comparison: What is the simplest conventional solution a
senior engineer would build? Compare the invention to this baseline. If they
use the same core mechanism, novelty is LOW regardless of naming.

TEST 3 - Mechanism Surprise: Would a PRACTITIONER in the target domain be
SURPRISED by this mechanism? Not "has this concept been published anywhere"
but "would a working engineer building this system reach for this approach?"
If the concept exists in academic literature but has never been practically
applied to this problem class, it IS surprising.
Rate SURPRISING if the mechanism brings a genuinely different computational
approach, even if the abstract concept exists in other fields.

Output ONLY valid JSON:
{
  "structural_validity": <float 0.0-1.0>,
  "implementation_feasibility": <float 0.0-1.0>,
  "novelty_score": <float 0.0-1.0>,
  "feasibility_rating": "<HIGH | MEDIUM | LOW | THEORETICAL>",
  "validity_notes": "<explanation of structural validity assessment>",
  "feasibility_notes": "<what would be needed to implement this>",
  "novelty_notes": "<why this is or isn't genuinely novel>",
  "domain_removal_test": "<describe the mechanism without source-domain words — is it still coherent and known?>",
  "baseline_mechanism": "<what would a senior engineer build conventionally?>",
  "mechanism_surprise_rating": "<SURPRISING | INTERESTING | CONVENTIONAL | OBVIOUS>",
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
    grounding_report:
        Perplexity-grounded external annex: related work, adjacent fields,
        and practitioner references.
    implementation_risk_review:
        Perplexity-grounded implementation / operational risk review.
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
    grounding_report: Any = None
    implementation_risk_review: Any = None
    verification_notes: str = ""
    validity_notes: str = ""
    feasibility_notes: str = ""
    novelty_notes: str = ""
    load_bearing_passed: bool = True  # from load_bearing_check
    load_bearing_notes: str = ""
    mechanism_differs_from_baseline: str = ""  # from translation
    subtraction_test: str = ""  # from translation
    baseline_comparison: str = ""  # from translation
    bundle_acceptance_status: str = "singleton"
    guard_failures: list[str] = field(default_factory=list)
    lineage_stale: bool = False
    orchestration_mode: str = "singleton"
    recomposition_events: list[dict[str, Any]] = field(default_factory=list)
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
        use_perplexity_research: bool = True,
        perplexity_model: str | None = None,
        system: str | None = None,
    ) -> None:
        self._attack_harness = attack_harness
        self._defend_harness = defend_harness or attack_harness
        self._run_prior_art = run_prior_art
        self._use_perplexity_research = use_perplexity_research
        self._perplexity_model = perplexity_model
        self._system_override = system
        self._prior_art_searcher: Any = None
        self._perplexity_client: Any = None

        if run_prior_art:
            self._init_prior_art_searcher()
        self._init_perplexity_client()

    def _init_prior_art_searcher(self) -> None:
        """Lazily initialise the prior art searcher with graceful fallback."""
        try:
            from hephaestus.output.prior_art import PriorArtSearcher
            self._prior_art_searcher = PriorArtSearcher(
                use_perplexity_review=self._use_perplexity_research,
                perplexity_model=self._perplexity_model,
            )
            logger.info("Prior art searcher initialised")
        except ImportError:
            logger.warning("Prior art searcher not available (missing dependencies)")
        except Exception as exc:
            logger.warning("Prior art searcher init failed: %s", exc)

    def _init_perplexity_client(self) -> None:
        """Initialise the Perplexity research client if configured."""
        try:
            from hephaestus.research.perplexity import PerplexityClient
            client = PerplexityClient(
                enabled=self._use_perplexity_research,
                model=self._perplexity_model,
            )
            if client.available():
                self._perplexity_client = client
        except Exception as exc:
            logger.warning("Perplexity research client init failed: %s", exc)

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
        grounding_report = None
        implementation_risk_review = None

        import asyncio

        research_tasks: list[Any] = []
        task_names: list[str] = []

        if self._run_prior_art and self._prior_art_searcher is not None:
            research_tasks.append(
                self._prior_art_searcher.search(
                    query=(
                        f"{translation.key_insight} "
                        f"{translation.source_domain} "
                        f"{structure.native_domain}"
                    ),
                    invention_name=translation.invention_name,
                )
            )
            task_names.append("prior_art")

        if self._perplexity_client is not None:
            research_tasks.extend([
                self._perplexity_client.ground_invention_report(
                    problem=structure.original_problem,
                    invention_name=translation.invention_name,
                    source_domain=translation.source_domain,
                    key_insight=translation.key_insight,
                    architecture=translation.architecture,
                ),
                self._perplexity_client.review_implementation_risks(
                    problem=structure.original_problem,
                    invention_name=translation.invention_name,
                    architecture=translation.architecture,
                    key_insight=translation.key_insight,
                ),
            ])
            task_names.extend(["grounding", "risk_review"])

        if research_tasks:
            try:
                research_results = await asyncio.gather(*research_tasks, return_exceptions=True)
                for name, result in zip(task_names, research_results):
                    if isinstance(result, Exception):
                        logger.warning("%s research failed for %s: %s", name, translation.invention_name, result)
                        continue
                    if name == "prior_art":
                        prior_art_report = result
                        prior_art_status = prior_art_report.novelty_status
                        logger.debug(
                            "Prior art for %s: %s",
                            translation.invention_name,
                            prior_art_status,
                        )
                    elif name == "grounding":
                        grounding_report = result
                    elif name == "risk_review":
                        implementation_risk_review = result
            except Exception as exc:
                logger.warning("Research annex failed for %s: %s", translation.invention_name, exc)
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

        # Step 3.6: Structural novelty score (model-free)
        from hephaestus.core.structural_novelty import compute_structural_novelty
        source_words = translation.source_domain.lower().replace("—", " ").replace("-", " ").split()
        structural_novelty = compute_structural_novelty(
            problem=structure.original_problem,
            architecture=translation.architecture,
            key_insight=translation.key_insight,
            phase1_abstract=getattr(translation, "phase1_abstract_mechanism", ""),
            source_domain_words=source_words,
        )
        logger.info(
            "Structural novelty for %s: composite=%.2f (%s) | "
            "vocab_div=%.2f concept_den=%.2f spec=%.2f self_contain=%.2f",
            translation.invention_name,
            structural_novelty.composite,
            structural_novelty.label,
            structural_novelty.vocabulary_divergence,
            structural_novelty.concept_density,
            structural_novelty.specificity,
            structural_novelty.self_containment,
        )

        # Step 3.7: Quality gate assessment (rule-based, not model-based)
        from hephaestus.core.quality_gate import assess_invention_quality
        quality = assess_invention_quality(
            architecture=translation.architecture,
            key_insight=translation.key_insight,
            mechanism_differs_from_baseline=translation.mechanism_differs_from_baseline,
            subtraction_test=translation.subtraction_test,
            baseline_comparison=translation.baseline_comparison,
        )
        reference_state = build_reference_state(
            structure,
            branch_genome=getattr(getattr(translation, "source_candidate", None), "branch_genome", None),
        )
        guard_failures = [
            check.detail
            for guard in getattr(translation, "guard_results", [])
            for check in getattr(guard, "checks", [])
            if not getattr(check, "passed", True)
        ]
        lineage = getattr(translation, "bundle_lineage", None)
        lineage_stale = bool(lineage is not None and hasattr(lineage, "is_continuous") and not lineage.is_continuous(reference_state))
        orchestration_mode = str(getattr(translation, "selection_mode", "bundle" if getattr(translation, "bundle_proof", None) else "singleton"))
        bundle_acceptance_status = "bundle_accepted" if getattr(translation, "bundle_proof", None) is not None else "singleton"
        if guard_failures:
            bundle_acceptance_status = "bundle_recomposed" if getattr(translation, "recomposition_events", []) else "bundle_guarded"
        if lineage_stale:
            bundle_acceptance_status = "bundle_invalidated"

        # Step 4: Compute final novelty score
        novelty_score = self._compute_novelty_score(
            attack_result=attack_result,
            structural_validity=validity.get("structural_validity", 0.5),
            prior_art_status=prior_art_status,
            domain_distance=translation.domain_distance,
            mechanism_surprise=str(validity.get("mechanism_surprise_rating", "")),
            quality_gate=quality,
            structural_novelty_composite=structural_novelty.composite,
        )

        # Step 4.5: Apply quality penalties
        if not load_bearing_passed:
            novelty_score *= 0.5  # 50% penalty for decorative domain transfer

        # Self-reported decorative transfer penalty
        if getattr(translation, "mechanism_is_decorative", False):
            novelty_score *= 0.3  # 70% penalty — model itself says it's decorative
            logger.info(
                "Novelty score penalized (self-reported decorative): %.2f for %s. "
                "Known pattern: %s",
                novelty_score, translation.invention_name,
                getattr(translation, "known_pattern_if_decorative", "unknown"),
            )
            logger.info(
                "Novelty score penalized (load-bearing failed): %.2f for %s",
                novelty_score, translation.invention_name,
            )

        if guard_failures:
            novelty_score *= 0.75
        if lineage_stale:
            novelty_score *= 0.60

        # Combine verification notes
        notes_parts = [
            f"Adversarial verdict: {attack_result.verdict}",
            f"Prior art: {prior_art_status}",
            f"Feasibility: {validity.get('feasibility_rating', 'UNKNOWN')}",
            f"Load-bearing: {'PASS' if load_bearing_passed else 'FAIL'}",
        ]
        if guard_failures:
            notes_parts.append(f"Guard failures: {' | '.join(guard_failures[:3])}")
        if lineage_stale:
            notes_parts.append("Lineage continuity failed against current reference state.")
        if grounding_report is not None and getattr(grounding_report, "summary", ""):
            notes_parts.append(f"Grounding: {grounding_report.summary}")
        if implementation_risk_review is not None and getattr(implementation_risk_review, "summary", ""):
            notes_parts.append(f"Risk review: {implementation_risk_review.summary}")
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
            grounding_report=grounding_report,
            implementation_risk_review=implementation_risk_review,
            verification_notes="\n".join(notes_parts),
            validity_notes=str(validity.get("validity_notes", "")),
            feasibility_notes=str(validity.get("feasibility_notes", "")),
            novelty_notes=str(validity.get("novelty_notes", "")),
            load_bearing_passed=load_bearing_passed,
            load_bearing_notes=load_bearing_notes,
            mechanism_differs_from_baseline=translation.mechanism_differs_from_baseline,
            subtraction_test=translation.subtraction_test,
            baseline_comparison=translation.baseline_comparison,
            bundle_acceptance_status=bundle_acceptance_status,
            guard_failures=guard_failures,
            lineage_stale=lineage_stale,
            orchestration_mode=orchestration_mode,
            recomposition_events=list(getattr(translation, "recomposition_events", []) or []),
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
        mechanism_surprise: str = "",
        quality_gate: Any = None,
        structural_novelty_composite: float = 0.5,
    ) -> float:
        """
        Compute the final novelty score from all verification components.

        The score now incorporates concrete novelty tests:
        - Adversarial novelty risk
        - Prior art status
        - Domain distance (but capped — distance alone doesn't make it novel)
        - Mechanism surprise rating (from the 3-test assessment)
        - Fatal flaw penalty
        """
        # Prior art multiplier
        prior_art_multipliers = {
            "NO_PRIOR_ART_FOUND": 1.0,
            "POSSIBLE_PRIOR_ART": 0.7,
            "SEARCH_UNAVAILABLE": 1.0,  # Don't penalize when search is down
            "PRIOR_ART_FOUND": 0.3,
        }
        prior_mult = prior_art_multipliers.get(prior_art_status, 0.8)

        # Novelty risk penalty from adversarial attack
        novelty_risk_penalty = 1.0 - (attack_result.novelty_risk * 0.5)

        # Fatal flaw penalty — graduated by count and quality gate agreement
        # The attacker tends to find "fatal flaws" in almost everything.
        # Graduate the penalty: 1 flaw = mild, 3+ = severe
        # But if quality gate passed cleanly, discount the attacker's aggression
        n_fatal = len(attack_result.fatal_flaws) if attack_result.attack_valid else 0
        if n_fatal == 0:
            fatal_penalty = 1.0
        elif n_fatal == 1:
            fatal_penalty = 0.85
        elif n_fatal == 2:
            fatal_penalty = 0.7
        else:
            fatal_penalty = 0.55
        # If quality gate passed cleanly, halve the fatal penalty effect
        if quality_gate is not None and quality_gate.passed and quality_gate.decorative_signal_count == 0:
            fatal_penalty = 1.0 - (1.0 - fatal_penalty) * 0.5

        # Distance bonus — CAPPED. Distance helps but doesn't dominate.
        # A far domain with an obvious mechanism should NOT score high.
        distance_bonus = 0.8 + 0.2 * min(domain_distance, 1.0)

        # Mechanism surprise multiplier — model's self-assessment
        # NOTE: Models systematically rate their own output as CONVENTIONAL
        # because they just generated it and it feels familiar to them.
        # We reduce this signal's weight to avoid self-referential bias.
        surprise_multipliers = {
            "SURPRISING": 1.15,   # Modest boost — if even the model is surprised, that's meaningful
            "INTERESTING": 1.0,   # Neutral
            "CONVENTIONAL": 0.85, # Mild penalty — model bias makes this unreliable
            "OBVIOUS": 0.5,       # Significant penalty — only when model is very confident
        }
        surprise_mult = surprise_multipliers.get(
            mechanism_surprise.upper(), 0.9  # default: slight benefit of doubt
        )

        # Quality gate bonus — rule-based signal that counterbalances
        # over-conservative model self-assessment
        quality_bonus = 1.0
        if quality_gate is not None:
            if quality_gate.passed and quality_gate.decorative_signal_count == 0:
                # Clean quality gate pass = significant boost
                quality_bonus = 1.3
            elif quality_gate.passed:
                quality_bonus = 1.1
            elif not quality_gate.passed:
                quality_bonus = 0.5  # gate failed = hard penalty

        # Structural novelty (model-free) — the most reliable novelty signal
        # because it doesn't suffer from self-referential conservatism.
        # Higher weight than model-based surprise assessment.
        structural_novelty_mult = 0.6 + 0.8 * structural_novelty_composite  # 0.6 to 1.4

        raw = (
            structural_validity
            * novelty_risk_penalty
            * prior_mult
            * fatal_penalty
            * distance_bonus
            * surprise_mult
            * quality_bonus
            * structural_novelty_mult
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
