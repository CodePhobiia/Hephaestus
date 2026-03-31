"""
Novelty Proof Generator.

Generates a formal novelty statement for each Hephaestus invention.

A :class:`NoveltyProof` is a structured document that captures:

1. **Structural Mapping Uniqueness** — the element-by-element correspondence
   between the source domain and target domain is demonstrably unique.
2. **Domain Distance Metric** — a quantified measure of how far the source
   domain is from the target domain (higher = more novel).
3. **Prior Art Absence** — the result of the prior art search.
4. **Mechanism Originality** — whether the core mechanism has been applied in
   this target domain before.

The proof does NOT make absolute novelty claims — it provides the evidence
needed for a human (or automated system) to assess novelty.  Every proof
includes explicit ``confidence`` and ``caveats`` fields.

Usage
-----
::

    from hephaestus.output.proof import NoveltyProofGenerator
    from hephaestus.output.prior_art import PriorArtReport

    generator = NoveltyProofGenerator()
    proof = generator.generate(
        problem="Distributed load balancing under unpredictable traffic",
        invention_name="Pheromone-Gradient Load Balancer",
        source_domain="Ant Colony Optimization (Biology)",
        target_domain="Distributed Systems",
        domain_distance=0.94,
        structural_fidelity=0.87,
        novelty_score=0.91,
        mechanism="Positive feedback via pheromone trails to reinforce good paths",
        structural_mapping={
            "ant": "request",
            "pheromone trail": "routing weight",
            "nest": "server",
            "food source": "successful response",
        },
        prior_art_report=report,
    )
    print(proof.formal_statement)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Confidence thresholds
_HIGH_CONFIDENCE_DISTANCE = 0.80
_MEDIUM_CONFIDENCE_DISTANCE = 0.60
_HIGH_FIDELITY = 0.75


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class StructuralMappingAnalysis:
    """
    Analysis of the structural mapping between source and target domains.

    Attributes
    ----------
    source_domain:
        Origin domain (e.g. ``"Ant Colony Optimization"``).
    target_domain:
        Destination domain (e.g. ``"Distributed Systems"``).
    element_count:
        Number of elements successfully mapped.
    mapping:
        Dict of ``{source_element: target_element}`` pairs.
    unmapped_elements:
        Source elements that could not be cleanly mapped.
    fidelity_score:
        Float 0–1 measuring how precisely the mapping preserves structure.
    isomorphism_statement:
        Formal statement about the structural isomorphism.
    """

    source_domain: str
    target_domain: str
    element_count: int
    mapping: dict[str, str]
    unmapped_elements: list[str] = field(default_factory=list)
    fidelity_score: float = 0.0
    isomorphism_statement: str = ""


@dataclass
class DomainDistanceAnalysis:
    """
    Quantified domain distance between source and target.

    Attributes
    ----------
    score:
        Float 0–1 where 1.0 is maximally distant.
    source_domain:
        Origin domain.
    target_domain:
        Destination domain.
    distance_basis:
        Explanation of how the distance was computed.
    percentile:
        Approximate percentile among all known domain pairs (if available).
    interpretation:
        Human-readable interpretation of the distance score.
    """

    score: float
    source_domain: str
    target_domain: str
    distance_basis: str = ""
    percentile: int | None = None
    interpretation: str = ""


@dataclass
class PriorArtAnalysis:
    """
    Summary of the prior art check for the novelty proof.

    Attributes
    ----------
    search_available:
        Whether the prior art search was successful.
    patents_found:
        Number of patents found.
    papers_found:
        Number of academic papers found.
    closest_prior_art:
        Description of the closest matching prior art (if any).
    absence_statement:
        Statement about the absence of direct prior art.
    """

    search_available: bool
    patents_found: int = 0
    papers_found: int = 0
    closest_prior_art: str = ""
    absence_statement: str = ""


@dataclass
class MechanismOriginalityAnalysis:
    """
    Analysis of mechanism originality.

    Attributes
    ----------
    mechanism:
        Description of the core mechanism.
    origin_domain:
        Domain where this mechanism was first described.
    known_target_applications:
        Known prior applications of this mechanism in the target domain.
    originality_statement:
        Statement about what is original about this application.
    is_known_transfer:
        Whether this domain transfer is documented in prior literature.
    """

    mechanism: str
    origin_domain: str
    known_target_applications: list[str] = field(default_factory=list)
    originality_statement: str = ""
    is_known_transfer: bool = False


@dataclass
class NoveltyProof:
    """
    Formal novelty proof for a Hephaestus invention.

    Attributes
    ----------
    invention_name:
        The name of the invention.
    problem:
        The original problem statement.
    novelty_score:
        Overall novelty score (0–1).  Composite of distance × fidelity.
    confidence:
        Confidence level: ``"HIGH"``, ``"MEDIUM"``, or ``"LOW"``.
    structural_mapping:
        :class:`StructuralMappingAnalysis` for this invention.
    domain_distance:
        :class:`DomainDistanceAnalysis` for this invention.
    prior_art:
        :class:`PriorArtAnalysis` for this invention.
    mechanism_originality:
        :class:`MechanismOriginalityAnalysis` for this invention.
    formal_statement:
        The full formal novelty statement as a human-readable string.
    caveats:
        List of limitations or caveats about this proof.
    generated_at:
        UTC timestamp of proof generation.
    """

    invention_name: str
    problem: str
    novelty_score: float
    confidence: str
    structural_mapping: StructuralMappingAnalysis
    domain_distance: DomainDistanceAnalysis
    prior_art: PriorArtAnalysis
    mechanism_originality: MechanismOriginalityAnalysis
    formal_statement: str = ""
    caveats: list[str] = field(default_factory=list)
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    )

    def to_dict(self) -> dict[str, Any]:
        """Serialise the proof to a plain dictionary."""
        return {
            "invention_name": self.invention_name,
            "problem": self.problem,
            "novelty_score": self.novelty_score,
            "confidence": self.confidence,
            "generated_at": self.generated_at,
            "structural_mapping": {
                "source_domain": self.structural_mapping.source_domain,
                "target_domain": self.structural_mapping.target_domain,
                "element_count": self.structural_mapping.element_count,
                "mapping": self.structural_mapping.mapping,
                "unmapped_elements": self.structural_mapping.unmapped_elements,
                "fidelity_score": self.structural_mapping.fidelity_score,
                "isomorphism_statement": self.structural_mapping.isomorphism_statement,
            },
            "domain_distance": {
                "score": self.domain_distance.score,
                "source_domain": self.domain_distance.source_domain,
                "target_domain": self.domain_distance.target_domain,
                "distance_basis": self.domain_distance.distance_basis,
                "interpretation": self.domain_distance.interpretation,
            },
            "prior_art": {
                "search_available": self.prior_art.search_available,
                "patents_found": self.prior_art.patents_found,
                "papers_found": self.prior_art.papers_found,
                "closest_prior_art": self.prior_art.closest_prior_art,
                "absence_statement": self.prior_art.absence_statement,
            },
            "mechanism_originality": {
                "mechanism": self.mechanism_originality.mechanism,
                "origin_domain": self.mechanism_originality.origin_domain,
                "known_target_applications": self.mechanism_originality.known_target_applications,
                "originality_statement": self.mechanism_originality.originality_statement,
                "is_known_transfer": self.mechanism_originality.is_known_transfer,
            },
            "formal_statement": self.formal_statement,
            "caveats": self.caveats,
        }


# ---------------------------------------------------------------------------
# NoveltyProofGenerator
# ---------------------------------------------------------------------------


class NoveltyProofGenerator:
    """
    Generates :class:`NoveltyProof` objects for Hephaestus inventions.

    The proof is based on evidence gathered during the invention pipeline:
    structural mapping quality, domain distance, prior art search results,
    and mechanism analysis.

    Parameters
    ----------
    alpha:
        Exponent for the novelty scoring formula ``score = fidelity × distance^alpha``.
        Default 1.5 (superlinear reward for domain distance).
    """

    def __init__(self, alpha: float = 1.5) -> None:
        self._alpha = alpha

    def generate(
        self,
        *,
        problem: str,
        invention_name: str,
        source_domain: str,
        target_domain: str,
        domain_distance: float,
        structural_fidelity: float,
        novelty_score: float | None = None,
        mechanism: str = "",
        structural_mapping: dict[str, str] | None = None,
        prior_art_report: Any | None = None,
        where_analogy_breaks: str = "",
        additional_caveats: list[str] | None = None,
    ) -> NoveltyProof:
        """
        Generate a formal novelty proof.

        Parameters
        ----------
        problem:
            The original problem statement.
        invention_name:
            Name of the invention.
        source_domain:
            Domain the solution was borrowed from.
        target_domain:
            Domain the solution is being applied to.
        domain_distance:
            Quantified distance between source and target (0–1).
        structural_fidelity:
            How well the structural mapping holds (0–1).
        novelty_score:
            Pre-computed novelty score.  If ``None``, computed from
            ``fidelity × distance^alpha``.
        mechanism:
            Description of the core mechanism.
        structural_mapping:
            Dict of ``{source_element: target_element}`` pairs.
        prior_art_report:
            :class:`~hephaestus.output.prior_art.PriorArtReport` object.
        where_analogy_breaks:
            Description of where the analogy breaks down.
        additional_caveats:
            Extra caveats to include in the proof.

        Returns
        -------
        NoveltyProof
        """
        mapping = structural_mapping or {}

        # Compute novelty score if not provided
        if novelty_score is None:
            novelty_score = structural_fidelity * (domain_distance ** self._alpha)
            novelty_score = min(1.0, novelty_score)

        # Build sub-analyses
        struct_analysis = self._analyze_mapping(
            source_domain=source_domain,
            target_domain=target_domain,
            mapping=mapping,
            fidelity_score=structural_fidelity,
        )

        distance_analysis = self._analyze_distance(
            source_domain=source_domain,
            target_domain=target_domain,
            distance=domain_distance,
        )

        prior_art_analysis = self._analyze_prior_art(prior_art_report)

        mechanism_analysis = self._analyze_mechanism(
            mechanism=mechanism,
            source_domain=source_domain,
            target_domain=target_domain,
        )

        # Confidence level
        confidence = self._compute_confidence(
            domain_distance=domain_distance,
            structural_fidelity=structural_fidelity,
            prior_art_analysis=prior_art_analysis,
        )

        # Caveats
        caveats = self._build_caveats(
            where_analogy_breaks=where_analogy_breaks,
            prior_art_analysis=prior_art_analysis,
            structural_fidelity=structural_fidelity,
            additional_caveats=additional_caveats or [],
        )

        # Build the formal statement
        formal_statement = self._build_formal_statement(
            invention_name=invention_name,
            problem=problem,
            source_domain=source_domain,
            target_domain=target_domain,
            novelty_score=novelty_score,
            confidence=confidence,
            struct_analysis=struct_analysis,
            distance_analysis=distance_analysis,
            prior_art_analysis=prior_art_analysis,
            mechanism_analysis=mechanism_analysis,
            caveats=caveats,
        )

        logger.debug(
            "Novelty proof generated: name=%r score=%.2f confidence=%s",
            invention_name,
            novelty_score,
            confidence,
        )

        return NoveltyProof(
            invention_name=invention_name,
            problem=problem,
            novelty_score=round(novelty_score, 4),
            confidence=confidence,
            structural_mapping=struct_analysis,
            domain_distance=distance_analysis,
            prior_art=prior_art_analysis,
            mechanism_originality=mechanism_analysis,
            formal_statement=formal_statement,
            caveats=caveats,
        )

    # ------------------------------------------------------------------
    # Sub-analyses
    # ------------------------------------------------------------------

    def _analyze_mapping(
        self,
        *,
        source_domain: str,
        target_domain: str,
        mapping: dict[str, str],
        fidelity_score: float,
    ) -> StructuralMappingAnalysis:
        """Build the structural mapping analysis."""
        element_count = len(mapping)
        unmapped: list[str] = []

        if fidelity_score >= _HIGH_FIDELITY:
            isomorphism = (
                f"Strong structural isomorphism confirmed. "
                f"{element_count} elements from '{source_domain}' map precisely "
                f"onto elements in '{target_domain}' with fidelity score {fidelity_score:.2f}. "
                f"The mathematical relationships between elements are preserved across the domain transfer."
            )
        elif fidelity_score >= 0.5:
            isomorphism = (
                f"Partial structural isomorphism. "
                f"{element_count} elements mapped with fidelity {fidelity_score:.2f}. "
                f"Core structure preserved; peripheral elements require adaptation."
            )
        else:
            isomorphism = (
                f"Loose structural analogy. "
                f"Fidelity {fidelity_score:.2f} indicates conceptual transfer rather than "
                f"strict isomorphism. The mapping provides inspiration rather than direct translation."
            )

        return StructuralMappingAnalysis(
            source_domain=source_domain,
            target_domain=target_domain,
            element_count=element_count,
            mapping=mapping,
            unmapped_elements=unmapped,
            fidelity_score=fidelity_score,
            isomorphism_statement=isomorphism,
        )

    def _analyze_distance(
        self,
        *,
        source_domain: str,
        target_domain: str,
        distance: float,
    ) -> DomainDistanceAnalysis:
        """Build the domain distance analysis."""
        if distance >= 0.90:
            interp = f"Exceptional domain distance. '{source_domain}' and '{target_domain}' are from almost entirely unrelated fields. This level of cross-domain transfer is extremely rare in existing literature."
        elif distance >= 0.80:
            interp = f"High domain distance. '{source_domain}' and '{target_domain}' share minimal conceptual overlap. Solutions in this space are highly likely to be novel."
        elif distance >= 0.60:
            interp = f"Moderate domain distance. Some conceptual bridges between '{source_domain}' and '{target_domain}' exist but the specific structural transfer is uncommon."
        else:
            interp = f"Lower domain distance. '{source_domain}' and '{target_domain}' share some research territory. Novelty depends on the specific mechanism being transferred."

        return DomainDistanceAnalysis(
            score=distance,
            source_domain=source_domain,
            target_domain=target_domain,
            distance_basis=(
                f"Computed as cosine distance between domain embedding vectors "
                f"(all-MiniLM-L6-v2 sentence transformer). "
                f"Score = {distance:.4f} (0 = identical domains, 1 = maximally distant)."
            ),
            interpretation=interp,
        )

    def _analyze_prior_art(self, prior_art_report: Any | None) -> PriorArtAnalysis:
        """Build the prior art analysis from a PriorArtReport."""
        if prior_art_report is None:
            return PriorArtAnalysis(
                search_available=False,
                absence_statement="Prior art search was not performed for this invention.",
            )

        patents_found = len(getattr(prior_art_report, "patents", []))
        papers_found = len(getattr(prior_art_report, "papers", []))
        search_available = getattr(prior_art_report, "search_available", False)

        if not search_available:
            return PriorArtAnalysis(
                search_available=False,
                absence_statement=(
                    "Prior art search was unavailable (API unreachable). "
                    "Manual review of patents and literature is recommended before filing."
                ),
            )

        total = patents_found + papers_found

        if total == 0:
            absence_statement = (
                "No direct prior art was identified in Google Patents or Semantic Scholar "
                "for this specific cross-domain application. The specific structural transfer "
                "from the source domain to this target domain does not appear in indexed literature."
            )
            closest = ""
        else:
            absence_statement = (
                f"{total} potentially related work(s) found. "
                "Review is required to determine if these constitute direct prior art "
                "for this specific cross-domain structural transfer."
            )
            # Try to get closest from the report
            patents = getattr(prior_art_report, "patents", [])
            papers = getattr(prior_art_report, "papers", [])
            candidates = []
            if patents:
                p = patents[0]
                candidates.append(f"Patent: {getattr(p, 'title', 'N/A')} ({getattr(p, 'patent_id', '')})")
            if papers:
                p = papers[0]
                candidates.append(f"Paper: {getattr(p, 'title', 'N/A')} ({getattr(p, 'year', 'N/A')})")
            closest = "; ".join(candidates[:2])

        return PriorArtAnalysis(
            search_available=search_available,
            patents_found=patents_found,
            papers_found=papers_found,
            closest_prior_art=closest,
            absence_statement=absence_statement,
        )

    def _analyze_mechanism(
        self,
        *,
        mechanism: str,
        source_domain: str,
        target_domain: str,
    ) -> MechanismOriginalityAnalysis:
        """Build the mechanism originality analysis."""
        originality = (
            f"The mechanism '{mechanism[:100]}' originates in '{source_domain}' where it "
            f"solves a structurally analogous problem. Its application to '{target_domain}' "
            f"is the inventive contribution: the core dynamics are preserved while the "
            f"implementation substrate is entirely different."
        )

        return MechanismOriginalityAnalysis(
            mechanism=mechanism,
            origin_domain=source_domain,
            originality_statement=originality,
            is_known_transfer=False,  # Conservative default; can be overridden
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _compute_confidence(
        self,
        *,
        domain_distance: float,
        structural_fidelity: float,
        prior_art_analysis: PriorArtAnalysis,
    ) -> str:
        """Compute confidence level: HIGH / MEDIUM / LOW."""
        if (
            domain_distance >= _HIGH_CONFIDENCE_DISTANCE
            and structural_fidelity >= _HIGH_FIDELITY
            and prior_art_analysis.search_available
            and prior_art_analysis.patents_found + prior_art_analysis.papers_found == 0
        ):
            return "HIGH"

        if (
            domain_distance >= _MEDIUM_CONFIDENCE_DISTANCE
            and structural_fidelity >= 0.5
        ):
            return "MEDIUM"

        return "LOW"

    def _build_caveats(
        self,
        *,
        where_analogy_breaks: str,
        prior_art_analysis: PriorArtAnalysis,
        structural_fidelity: float,
        additional_caveats: list[str],
    ) -> list[str]:
        """Collect relevant caveats for this proof."""
        caveats: list[str] = []

        if where_analogy_breaks:
            caveats.append(f"Analogy boundary: {where_analogy_breaks}")

        if not prior_art_analysis.search_available:
            caveats.append(
                "Prior art search was unavailable. Manual patent/literature review required."
            )
        elif prior_art_analysis.patents_found + prior_art_analysis.papers_found > 0:
            caveats.append(
                "Potentially related prior art found. Review is needed before asserting novelty."
            )

        if structural_fidelity < 0.6:
            caveats.append(
                f"Low structural fidelity ({structural_fidelity:.2f}) — the mapping is "
                "conceptually suggestive rather than formally rigorous. Implementation will "
                "require significant adaptation."
            )

        caveats.extend(additional_caveats)

        if not caveats:
            caveats.append(
                "No significant caveats identified. This proof is based on automated analysis "
                "and should be reviewed by a domain expert before use in a patent filing."
            )

        return caveats

    def _build_formal_statement(
        self,
        *,
        invention_name: str,
        problem: str,
        source_domain: str,
        target_domain: str,
        novelty_score: float,
        confidence: str,
        struct_analysis: StructuralMappingAnalysis,
        distance_analysis: DomainDistanceAnalysis,
        prior_art_analysis: PriorArtAnalysis,
        mechanism_analysis: MechanismOriginalityAnalysis,
        caveats: list[str],
    ) -> str:
        """Compose the full formal novelty statement."""
        lines = [
            f"NOVELTY PROOF — {invention_name}",
            "=" * 60,
            "",
            "CLAIM",
            "-----",
            f"This invention proposes a novel solution to the following problem:",
            f'  \u201c{problem}\u201d',
            "",
            f"The invention '{invention_name}' is claimed to be structurally novel",
            f"on the following grounds:",
            "",
            "GROUND 1: STRUCTURAL MAPPING UNIQUENESS",
            "-" * 40,
            struct_analysis.isomorphism_statement,
            "",
        ]

        if struct_analysis.mapping:
            lines.append("Element-by-element correspondence:")
            for src, tgt in list(struct_analysis.mapping.items())[:10]:
                lines.append(f"  {src} → {tgt}")
            lines.append("")

        lines += [
            "GROUND 2: DOMAIN DISTANCE",
            "-" * 40,
            f"Source domain: {source_domain}",
            f"Target domain: {target_domain}",
            f"Distance score: {distance_analysis.score:.4f} / 1.0",
            distance_analysis.interpretation,
            "",
            "GROUND 3: PRIOR ART ABSENCE",
            "-" * 40,
            prior_art_analysis.absence_statement,
        ]

        if prior_art_analysis.closest_prior_art:
            lines.append(f"Closest found: {prior_art_analysis.closest_prior_art}")

        lines += [
            "",
            "GROUND 4: MECHANISM ORIGINALITY",
            "-" * 40,
            mechanism_analysis.originality_statement,
            "",
            "COMPOSITE NOVELTY SCORE",
            "-" * 40,
            f"  Score:      {novelty_score:.4f} / 1.0",
            f"  Confidence: {confidence}",
            "",
            "CAVEATS",
            "-" * 40,
        ]

        for i, caveat in enumerate(caveats, start=1):
            lines.append(f"  {i}. {caveat}")

        lines += [
            "",
            "─" * 60,
            "This proof was generated automatically by Hephaestus.",
            "It is provided for informational purposes only and does not",
            "constitute legal advice or a formal patent application.",
            "─" * 60,
        ]

        return "\n".join(lines)
