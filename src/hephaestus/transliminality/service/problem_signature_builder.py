"""LLM-backed problem role signature extraction.

Follows the same pattern as ProblemDecomposer: DeepForgeHarness for LLM calls,
loads_lenient for JSON parsing, retry on parse failure.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from hephaestus.core.json_utils import loads_lenient
from hephaestus.forgebase.domain.values import EntityId
from hephaestus.forgebase.service.id_generator import IdGenerator
from hephaestus.transliminality.domain.models import (
    RoleSignature,
    TransliminalityConfig,
)
from hephaestus.transliminality.prompts.role_signature import (
    ROLE_SIGNATURE_SYSTEM,
    ROLE_SIGNATURE_USER,
    parse_role_signature,
)

if TYPE_CHECKING:
    from hephaestus.deepforge.harness import DeepForgeHarness

logger = logging.getLogger(__name__)


class SignatureBuilderError(Exception):
    """Raised when role signature extraction fails after all retries."""


class LLMProblemRoleSignatureBuilder:
    """Extract a RoleSignature from a problem description via LLM.

    Uses DeepForgeHarness with interference disabled — we want clean
    structural analysis, not divergent output.
    """

    def __init__(
        self,
        harness: DeepForgeHarness,
        id_generator: IdGenerator,
        *,
        max_retries: int = 3,
        max_tokens: int = 4096,
        temperature: float = 0.2,
    ) -> None:
        self._harness = harness
        self._id_gen = id_generator
        self._max_retries = max_retries
        self._max_tokens = max_tokens
        self._temperature = temperature

    async def build(
        self,
        problem: str,
        home_vault_ids: list[EntityId],
        branch_id: EntityId | None,
        config: TransliminalityConfig,
    ) -> RoleSignature:
        """Extract a structural role signature from the problem text."""
        user_prompt = ROLE_SIGNATURE_USER.format(problem=problem)
        t_start = time.monotonic()

        last_error: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                result = await self._harness.forge(
                    user_prompt,
                    system=ROLE_SIGNATURE_SYSTEM,
                    max_tokens=self._max_tokens,
                    temperature=self._temperature,
                )

                parsed = loads_lenient(
                    result.output,
                    default=None,
                    label="problem_role_signature",
                )

                if parsed is None:
                    msg = f"LLM returned unparseable output (attempt {attempt + 1})"
                    logger.warning(msg)
                    last_error = SignatureBuilderError(msg)
                    continue

                sig = parse_role_signature(
                    parsed,
                    problem=problem,
                    id_generator=self._id_gen,
                )

                if not sig.functional_roles:
                    msg = f"No functional roles extracted (attempt {attempt + 1})"
                    logger.warning(msg)
                    last_error = SignatureBuilderError(msg)
                    continue

                duration = time.monotonic() - t_start
                logger.info(
                    "role_signature extracted  roles=%d  constraints=%d  "
                    "failure_modes=%d  confidence=%.2f  duration=%.1fs",
                    len(sig.functional_roles),
                    len(sig.constraints),
                    len(sig.failure_modes),
                    sig.confidence,
                    duration,
                )
                return sig

            except Exception as exc:
                logger.warning(
                    "Signature extraction attempt %d failed: %s",
                    attempt + 1, exc,
                )
                last_error = exc

        raise SignatureBuilderError(
            f"Failed to extract role signature after {self._max_retries} attempts"
        ) from last_error
