"""FusionAnalyzer ABC -- structural analogy analysis contract.

Dedicated contract for cross-domain fusion, separate from CompilerBackend
and LintAnalyzer.  Different reasoning task, different prompts, different
temperature.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from hephaestus.forgebase.domain.models import BackendCallRecord
from hephaestus.forgebase.extraction.models import DomainContextPack
from hephaestus.forgebase.fusion.models import (
    AnalogicalMap,
    BridgeCandidate,
    TransferOpportunity,
)


class FusionAnalyzer(ABC):
    """Structural analogy analysis -- dedicated contract for cross-domain fusion.

    Separate from CompilerBackend and LintAnalyzer.  Different reasoning task,
    different prompts, different temperature.
    """

    @abstractmethod
    async def analyze_candidates(
        self,
        candidates: list[BridgeCandidate],
        left_context: DomainContextPack,
        right_context: DomainContextPack,
        problem: str | None = None,
    ) -> tuple[list[AnalogicalMap], list[TransferOpportunity], BackendCallRecord]:
        """Analyze bridge candidates for structural analogies.

        Must produce:
        - AnalogicalMaps with STRONG/WEAK/NO/INVALID verdicts
        - TransferOpportunities for validated analogies
        - Explicit negative results (NO_ANALOGY, INVALID)

        Problem affects: relevance ranking, transfer direction preference.
        """
