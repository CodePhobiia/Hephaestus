"""
Phase 0: Burn-Off — generates obvious/cliche baselines.

Fires the problem at a cheap/fast model (claude-haiku-4-5) at low temperature
to surface the most predictable, conventional solutions.  These become negative
constraints injected into Stage 1 (decompose) and Stage 4 (translate) to force
the pipeline away from obvious territory.

Usage::

    from hephaestus.core.burn_off import BurnOff

    burn_off = BurnOff(harness)
    baselines = await burn_off.generate_baselines("I need a load balancer")
    # ['Round-robin DNS', 'Nginx reverse proxy', ...]
"""

from __future__ import annotations

import json
import logging
import re

from hephaestus.core.json_utils import loads_lenient
from hephaestus.deepforge.harness import DeepForgeHarness

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_BURNOFF_SYSTEM = """\
You are a conventional solution generator. Your job is to produce the 5 most
obvious, standard, well-known, and cliche solutions to a given problem.

Think like a textbook. Think like a first-year graduate student. Think like
someone who has never had an original thought.

Output ONLY valid JSON:
{
  "baselines": [
    "<obvious solution 1>",
    "<obvious solution 2>",
    "<obvious solution 3>",
    "<obvious solution 4>",
    "<obvious solution 5>"
  ]
}
"""

_BURNOFF_PROMPT = """\
Problem: {problem}

Generate the 5 most obvious, conventional, textbook solutions to this problem.
These should be the solutions that ANYONE with domain knowledge would suggest
first. Name each solution concisely (one sentence each).

Return JSON only.
"""


# ---------------------------------------------------------------------------
# BurnOff
# ---------------------------------------------------------------------------


class BurnOff:
    """
    Phase 0: generates obvious/cliche baselines to use as negative constraints.

    Parameters
    ----------
    harness:
        A ``DeepForgeHarness`` configured with a cheap/fast model
        (e.g., claude-haiku-4-5 via ClaudeMaxAdapter).
    """

    def __init__(self, harness: DeepForgeHarness) -> None:
        self._harness = harness

    async def generate_baselines(self, problem: str) -> list[str]:
        """
        Generate 5 obvious/cliche solutions for the given problem.

        Parameters
        ----------
        problem:
            The natural-language problem description.

        Returns
        -------
        list[str]
            Up to 5 obvious solutions.  Returns empty list on failure.
        """
        prompt = _BURNOFF_PROMPT.format(problem=problem)

        try:
            result = await self._harness.forge(
                prompt,
                system=_BURNOFF_SYSTEM,
                max_tokens=800,
                temperature=0.2,
            )
            baselines = self._parse_output(result.output)
            logger.info("Burn-off generated %d baselines", len(baselines))
            return baselines
        except Exception as exc:
            logger.warning("Burn-off failed: %s", exc)
            return []

    @staticmethod
    def _parse_output(raw: str) -> list[str]:
        """Parse the burn-off JSON output."""
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned, count=1)
            cleaned = re.sub(r"\n?```\s*$", "", cleaned)

        json_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not json_match:
            return []

        try:
            data = loads_lenient(json_match.group(), default={}, label="burn_off")
            baselines = data.get("baselines", [])
            if isinstance(baselines, list):
                return [str(b) for b in baselines[:5]]
            return []
        except json.JSONDecodeError:
            return []
