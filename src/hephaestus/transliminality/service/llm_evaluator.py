"""LLM-backed evaluator for counterfactual dependence and non-ornamental use.

Consumes the integration_grading.py prompts to determine whether
cross-domain bridges are load-bearing or decorative.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from hephaestus.core.json_utils import loads_lenient
from hephaestus.transliminality.domain.enums import AnalogicalVerdict
from hephaestus.transliminality.domain.models import (
    AnalogicalMap,
    TransliminalityPack,
)
from hephaestus.transliminality.prompts.integration_grading import (
    COUNTERFACTUAL_SYSTEM,
    COUNTERFACTUAL_USER,
    NON_ORNAMENTAL_SYSTEM,
    NON_ORNAMENTAL_USER,
)

if TYPE_CHECKING:
    from hephaestus.deepforge.harness import DeepForgeHarness

logger = logging.getLogger(__name__)


class LLMIntegrationEvaluator:
    """Evaluates counterfactual dependence and non-ornamental use via LLM.

    Satisfies the ``LLMEvaluator`` protocol defined in
    ``service/integration_scorer.py``.
    """

    def __init__(
        self,
        harness: DeepForgeHarness,
        *,
        max_tokens: int = 2048,
        temperature: float = 0.2,
    ) -> None:
        self._harness = harness
        self._max_tokens = max_tokens
        self._temperature = temperature

    async def evaluate_counterfactual(
        self,
        pack: TransliminalityPack,
        maps: list[AnalogicalMap],
    ) -> float:
        """Score how much the invention depends on the cross-domain bridge."""
        valid_maps = [
            m for m in maps
            if m.verdict in (AnalogicalVerdict.VALID, AnalogicalVerdict.PARTIAL)
        ]
        if not valid_maps:
            return 0.0

        # Summarise bridges for the prompt
        bridge_lines = []
        for m in valid_maps[:3]:
            bridge_lines.append(
                f"- {m.shared_role}: {m.rationale}" if m.rationale else f"- {m.shared_role}"
            )
        bridge_desc = "\n".join(bridge_lines)

        # Summarise pack context as proxy for "invention generated with bridge"
        invention_lines = [e.text for e in pack.soft_context_entries[:5]]
        invention_text = "\n".join(invention_lines) if invention_lines else "(no soft context)"

        user_prompt = COUNTERFACTUAL_USER.format(
            bridge_description=bridge_desc,
            invention_with_bridge=invention_text,
        )

        try:
            result = await self._harness.forge(
                user_prompt,
                system=COUNTERFACTUAL_SYSTEM,
                max_tokens=self._max_tokens,
                temperature=self._temperature,
            )
            parsed = loads_lenient(result.output, default={}, label="counterfactual_eval")
            score = float(parsed.get("score", 0.0))
            logger.info(
                "counterfactual_eval  score=%.2f  mode=%s",
                score, parsed.get("collapse_mode", "unknown"),
            )
            return max(0.0, min(1.0, score))
        except Exception:
            logger.warning("LLM counterfactual evaluation failed, using 0.0")
            return 0.0

    async def evaluate_non_ornamental(
        self,
        pack: TransliminalityPack,
        maps: list[AnalogicalMap],
    ) -> float:
        """Score whether bridges do functional work vs decorating narrative."""
        valid_maps = [
            m for m in maps
            if m.verdict in (AnalogicalVerdict.VALID, AnalogicalVerdict.PARTIAL)
        ]
        if not valid_maps:
            return 0.0

        # Use the first valid map for evaluation
        amap = valid_maps[0]
        components_text = "\n".join(
            f"  - {cm.shared_role}: {cm.mapping_rationale}"
            for cm in amap.mapped_components
        ) or "(no mapped components)"

        solution_lines = [e.text for e in pack.soft_context_entries[:5]]
        solution_text = "\n".join(solution_lines) if solution_lines else "(no soft context)"

        user_prompt = NON_ORNAMENTAL_USER.format(
            shared_role=amap.shared_role,
            mapped_components=components_text,
            solution_text=solution_text,
        )

        try:
            result = await self._harness.forge(
                user_prompt,
                system=NON_ORNAMENTAL_SYSTEM,
                max_tokens=self._max_tokens,
                temperature=self._temperature,
            )
            parsed = loads_lenient(result.output, default={}, label="non_ornamental_eval")
            score = float(parsed.get("score", 0.0))
            logger.info(
                "non_ornamental_eval  score=%.2f  functional=%d  ornamental=%d",
                score,
                len(parsed.get("functional_elements", [])),
                len(parsed.get("ornamental_elements", [])),
            )
            return max(0.0, min(1.0, score))
        except Exception:
            logger.warning("LLM non-ornamental evaluation failed, using 0.0")
            return 0.0
