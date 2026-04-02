"""
Stage 1: Problem Decomposition.

Strips domain-specific language from a user's problem description and extracts
its abstract structural form — the mathematical shape that can be searched for
across knowledge domains.

The decomposer uses an Opus/GPT model via the DeepForge harness to produce a
structured ``ProblemStructure`` dataclass with:

- ``structure``: The abstract structural description (domain-neutral)
- ``constraints``: List of hard constraints the solution must satisfy
- ``mathematical_shape``: Formal characterisation (graph theory, dynamical
  systems, optimisation, etc.)
- ``original_problem``: The original user input, preserved verbatim
- ``native_domain``: Detected domain of the original problem (e.g., "distributed_systems")
- ``problem_maps_to``: Set of abstract problem type tags (e.g., {"trust", "optimization"})

Usage::

    from hephaestus.deepforge.harness import DeepForgeHarness, HarnessConfig
    from hephaestus.deepforge.adapters.anthropic import AnthropicAdapter
    from hephaestus.core.decomposer import ProblemDecomposer

    adapter = AnthropicAdapter("claude-opus-4-5")
    harness = DeepForgeHarness(adapter, HarnessConfig(use_interference=False,
                                                       use_pressure=False))
    decomposer = ProblemDecomposer(harness)
    structure = await decomposer.decompose("I need a load balancer for traffic spikes")
    print(structure.mathematical_shape)
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

from hephaestus.deepforge.harness import DeepForgeHarness, ForgeTrace

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt & output schema
# ---------------------------------------------------------------------------

_DECOMPOSE_SYSTEM = """\
You are a structural abstraction engine. Your task is to strip all
domain-specific language from a problem description and extract its pure
abstract form — the underlying mathematical/structural pattern that is
independent of the specific domain.

You must output ONLY valid JSON matching the schema below. Do not include any
explanation, preamble, or markdown fences.

Schema:
{
  "structure": "<abstract description of the problem's structural form, domain-neutral, 1-3 sentences>",
  "constraints": ["<constraint 1>", "<constraint 2>", ...],
  "mathematical_shape": "<formal characterisation: e.g., 'robust signal propagation in a graph with Byzantine fault tolerance', 'multi-agent resource allocation under adversarial conditions', etc.>",
  "native_domain": "<detected primary domain of the original problem, lowercase, e.g., 'distributed_systems', 'machine_learning', 'biology', 'finance'>",
  "problem_maps_to": ["<abstract problem type tag>", ...],
  "confidence": <float 0.0-1.0>
}

Guidelines for each field:
- structure: Describe WHAT the problem IS structurally, not WHAT it does. Use abstract language. Be PRECISE — "allocation under constraints" is too vague. "Partitioning a finite resource among N competing consumers with heterogeneous demand distributions, subject to a global ceiling and per-consumer fairness bounds, where consumers can adversarially misrepresent demand" is the right level of detail.
- constraints: Be exhaustive. Include both explicit and implicit constraints. Include quantitative bounds where the problem specifies them.
- mathematical_shape: Use SPECIFIC mathematical vocabulary. Not just "optimization" but "online convex optimization with bandit feedback and adversarial perturbation." The more precise the shape, the better the cross-domain search.
- native_domain: Single domain, lowercase, use underscores.
- problem_maps_to: Tags like ["trust", "optimization", "routing", "scheduling",
  "classification", "coordination", "filtering", "search", "allocation",
  "verification", "compression", "ranking", "prediction", "control"].
- confidence: Your confidence in this structural decomposition (0.0-1.0).
"""

_DECOMPOSE_PROMPT_TEMPLATE = """\
Problem to decompose:

{problem}

Extract the abstract structural form. Remember: strip all domain language,
identify the mathematical shape, list all constraints, and return pure JSON.
"""


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class ProblemStructure:
    """
    The abstract structural form of a user's problem.

    This is the output of Stage 1 (Decompose) and the input to Stage 2 (Search).

    Attributes
    ----------
    original_problem:
        The original natural language problem as submitted by the user.
    structure:
        Abstract structural description of the problem, domain-neutral.
    constraints:
        List of hard constraints the solution must satisfy.
    mathematical_shape:
        Formal characterisation of the problem structure (graph theory,
        dynamical systems, optimisation, etc.).
    native_domain:
        Detected domain of the original problem (e.g., "distributed_systems").
    problem_maps_to:
        Set of abstract problem-type tags used for lens selection.
    confidence:
        Model confidence in this decomposition (0.0–1.0).
    cost_usd:
        Estimated API cost in USD for this decomposition.
    duration_seconds:
        Wall-clock time taken for this decomposition.
    trace:
        Full DeepForge trace for debugging.
    baseline_dossier:
        Optional state-of-the-art / baseline reconnaissance attached after
        decomposition and used to avoid reinventing conventional patterns.
    """

    original_problem: str
    structure: str
    constraints: list[str]
    mathematical_shape: str
    native_domain: str
    problem_maps_to: set[str] = field(default_factory=set)
    confidence: float = 1.0
    cost_usd: float = 0.0
    duration_seconds: float = 0.0
    trace: ForgeTrace | None = None
    baseline_dossier: Any | None = None

    def __post_init__(self) -> None:
        # Ensure problem_maps_to is a set
        if isinstance(self.problem_maps_to, list):
            self.problem_maps_to = set(self.problem_maps_to)

    def to_search_description(self) -> str:
        """
        Build a concise domain-neutral description for embedding/lens selection.
        Combines structure and mathematical_shape for richer signal.
        """
        return f"{self.structure}. {self.mathematical_shape}"

    def summary(self) -> str:
        """Human-readable one-line summary."""
        return (
            f"[{self.native_domain}] {self.mathematical_shape}"
            f" | constraints={len(self.constraints)}"
            f" | confidence={self.confidence:.2f}"
        )


# ---------------------------------------------------------------------------
# Decomposer
# ---------------------------------------------------------------------------


class DecompositionError(Exception):
    """Raised when problem decomposition fails after all retries."""

    def __init__(self, reason: str, raw_output: str = "") -> None:
        super().__init__(reason)
        self.reason = reason
        self.raw_output = raw_output


class ProblemDecomposer:
    """
    Stage 1 of the Genesis pipeline: Problem Decomposition.

    Uses a DeepForge harness to extract the abstract structural form from a
    natural language problem description.

    Parameters
    ----------
    harness:
        A configured ``DeepForgeHarness`` instance.  For decomposition,
        cognitive interference should typically be disabled (we want clean
        structural analysis, not creative distortion at this stage).
    max_retries:
        Number of JSON parse retry attempts if the model returns malformed output.
    """

    def __init__(
        self,
        harness: DeepForgeHarness,
        max_retries: int = 3,
    ) -> None:
        self._harness = harness
        self._max_retries = max_retries

    async def decompose(
        self,
        problem: str,
        system: str | None = None,
    ) -> ProblemStructure:
        """
        Decompose a natural language problem into its abstract structural form.

        Parameters
        ----------
        problem:
            The user's natural language problem description.
        system:
            Optional system prompt override (e.g. V2 master prompt).
            Falls back to the default decomposition system prompt.

        Returns
        -------
        ProblemStructure

        Raises
        ------
        DecompositionError
            If decomposition fails after all retries.
        """
        problem = problem.strip()
        if not problem:
            raise DecompositionError("Empty problem description provided")

        logger.info("Decomposing problem (%d chars)", len(problem))
        t_start = time.monotonic()

        prompt = _DECOMPOSE_PROMPT_TEMPLATE.format(problem=problem)
        system_prompt = system if system is not None else _DECOMPOSE_SYSTEM
        last_error = ""
        last_output = ""

        for attempt in range(self._max_retries):
            try:
                result = await self._harness.forge(
                    prompt,
                    system=system_prompt,
                    max_tokens=16000,
                    temperature=0.3,  # Low temperature for consistent structured output
                )
                last_output = result.output

                parsed = self._parse_output(last_output)
                structure = ProblemStructure(
                    original_problem=problem,
                    structure=parsed["structure"],
                    constraints=parsed.get("constraints", []),
                    mathematical_shape=parsed["mathematical_shape"],
                    native_domain=parsed.get("native_domain", "unknown"),
                    problem_maps_to=set(parsed.get("problem_maps_to", [])),
                    confidence=float(parsed.get("confidence", 0.8)),
                    cost_usd=result.trace.total_cost_usd,
                    duration_seconds=time.monotonic() - t_start,
                    trace=result.trace,
                )

                logger.info(
                    "Decomposition complete | domain=%s shape=%r constraints=%d cost=$%.4f",
                    structure.native_domain,
                    structure.mathematical_shape[:60],
                    len(structure.constraints),
                    structure.cost_usd,
                )
                return structure

            except (DecompositionError, KeyError, ValueError, json.JSONDecodeError) as exc:
                last_error = str(exc)
                logger.warning(
                    "Decomposition attempt %d/%d failed: %s",
                    attempt + 1,
                    self._max_retries,
                    last_error,
                )
                if attempt < self._max_retries - 1:
                    continue

        raise DecompositionError(
            f"Decomposition failed after {self._max_retries} attempts: {last_error}",
            raw_output=last_output,
        )

    def _parse_output(self, raw: str) -> dict[str, Any]:
        """
        Parse and validate the model's JSON output.

        Handles models that wrap JSON in markdown code fences.

        Parameters
        ----------
        raw:
            Raw text output from the model.

        Returns
        -------
        dict
            Validated decomposition dict.

        Raises
        ------
        DecompositionError
            If JSON is missing required fields or cannot be parsed.
        """
        # Strip markdown fences if present
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            # Remove opening fence (```json or ```)
            cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned, count=1)
            # Remove closing fence
            cleaned = re.sub(r"\n?```\s*$", "", cleaned)

        # Attempt to extract JSON object from the text
        json_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not json_match:
            raise DecompositionError(
                "No JSON object found in model output",
                raw_output=raw,
            )

        try:
            data = json.loads(json_match.group())
        except json.JSONDecodeError as exc:
            raise DecompositionError(
                f"JSON parse error: {exc}",
                raw_output=raw,
            ) from exc

        # Validate required fields
        required = {"structure", "mathematical_shape"}
        missing = required - data.keys()
        if missing:
            raise DecompositionError(
                f"Decomposition output missing required fields: {missing}",
                raw_output=raw,
            )

        # Normalise lists
        if "constraints" not in data or not isinstance(data["constraints"], list):
            data["constraints"] = []
        if "problem_maps_to" not in data or not isinstance(data["problem_maps_to"], list):
            data["problem_maps_to"] = []

        # Normalise domain
        if "native_domain" not in data or not data["native_domain"]:
            data["native_domain"] = "general"

        return data
