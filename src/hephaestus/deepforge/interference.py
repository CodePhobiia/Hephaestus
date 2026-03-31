"""
Cognitive Interference Engine.

The Interference Engine is the first mechanism DeepForge uses to force models
off their default reasoning paths.  It works by injecting "foreign axioms"
(a *lens*) at the start of the assistant's response — forcing the model to
continue its chain-of-thought from within an alien conceptual frame rather
than from the RLHF-grooved default.

Three injection strategies are supported:

``FULL``
    Inject the entire axiom set of the chosen lens.  Maximum disruption.

``SINGLE``
    Inject a single, carefully chosen axiom.  More surgical interference that
    tends to keep domain transfer coherent.

``PROGRESSIVE``
    Start with one axiom, add more on each re-try.  Escalating pressure.

The engine also supports *lens rotation* — cycling through a sequence of
lenses across multiple generation attempts.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

from hephaestus.deepforge.exceptions import ConfigurationError, InterferenceError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


class InjectionStrategy(Enum):
    """Strategy for injecting lens axioms into the assistant prefill."""

    FULL = auto()         # Inject all axioms at once
    SINGLE = auto()       # Inject one axiom (highest-priority or random)
    PROGRESSIVE = auto()  # Inject n axioms where n grows with each attempt


@dataclass
class Lens:
    """
    A cognitive lens — a set of axioms from a foreign knowledge domain.

    A lens is loaded from a YAML lens file or constructed directly.  The
    :attr:`axioms` are the conceptual primitives of the domain, and
    :attr:`injection_prompt` is the framing text that tells the model to
    adopt this domain's perspective.

    Attributes
    ----------
    name:
        Human-readable lens name, e.g. ``"Immune System"``.
    domain:
        Parent domain category, e.g. ``"biology"``.
    axioms:
        Ordered list of domain axioms.  Earlier entries take priority when
        using ``SINGLE`` strategy.
    injection_prompt:
        Optional framing text injected before the axioms.  Should orient the
        model towards the domain without locking it in too hard.
    structural_patterns:
        Optional list of structural pattern dicts (from YAML lens spec).
    metadata:
        Arbitrary extra data (e.g. distance vectors).
    """

    name: str
    domain: str
    axioms: list[str]
    injection_prompt: str = ""
    structural_patterns: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.axioms:
            raise ConfigurationError(f"Lens {self.name!r} has no axioms defined")


@dataclass
class InjectionResult:
    """
    The outcome of a single interference injection.

    Attributes
    ----------
    prefill:
        The assembled text to inject as the assistant prefill.
    axioms_used:
        The specific axioms included in this injection.
    lens_name:
        Name of the lens used.
    strategy:
        The :class:`InjectionStrategy` applied.
    attempt:
        Which generation attempt this injection is for (0-indexed).
    """

    prefill: str
    axioms_used: list[str]
    lens_name: str
    strategy: InjectionStrategy
    attempt: int


# ---------------------------------------------------------------------------
# Interference Engine
# ---------------------------------------------------------------------------


class CognitiveInterferenceEngine:
    """
    Inject foreign-domain axioms into LLM generation via assistant prefill.

    The engine takes a :class:`Lens` (or a list for rotation) and assembles
    the ``prefill`` text that is passed to the model adapter.  For Anthropic
    models, this is the true assistant prefix.  For OpenAI models, it becomes
    a simulated assistant message.

    Parameters
    ----------
    lenses:
        A single :class:`Lens` or an ordered sequence of lenses for rotation.
    strategy:
        :class:`InjectionStrategy` controlling how axioms are selected.
    max_axioms_per_injection:
        Upper bound on the number of axioms included in one injection
        (relevant for ``PROGRESSIVE`` and ``FULL`` strategies).
    randomise_axiom_order:
        If ``True``, shuffle axioms before injection to reduce ordering bias.
    seed:
        Optional random seed for reproducible lens rotation / axiom selection.
    """

    def __init__(
        self,
        lenses: Lens | list[Lens],
        *,
        strategy: InjectionStrategy = InjectionStrategy.FULL,
        max_axioms_per_injection: int = 5,
        randomise_axiom_order: bool = False,
        seed: int | None = None,
    ) -> None:
        self._lenses: list[Lens] = [lenses] if isinstance(lenses, Lens) else list(lenses)
        if not self._lenses:
            raise ConfigurationError("CognitiveInterferenceEngine requires at least one lens")

        self._strategy = strategy
        self._max_axioms = max_axioms_per_injection
        self._randomise = randomise_axiom_order
        self._rng = random.Random(seed)
        self._rotation_index = 0

        logger.debug(
            "CognitiveInterferenceEngine initialised | lenses=%d strategy=%s",
            len(self._lenses),
            strategy.name,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_injection(self, attempt: int = 0) -> InjectionResult:
        """
        Build the prefill text for a given generation attempt.

        The lens is selected via rotation when multiple lenses are provided;
        each successive call advances the rotation index.

        Parameters
        ----------
        attempt:
            Zero-indexed attempt number.  Used by ``PROGRESSIVE`` strategy to
            increase axiom count with each retry.

        Returns
        -------
        InjectionResult
        """
        lens = self._select_lens(attempt)
        axioms = self._select_axioms(lens, attempt)
        prefill = self._assemble_prefill(lens, axioms)

        result = InjectionResult(
            prefill=prefill,
            axioms_used=axioms,
            lens_name=lens.name,
            strategy=self._strategy,
            attempt=attempt,
        )
        logger.debug(
            "Built injection for attempt %d | lens=%s axioms=%d",
            attempt,
            lens.name,
            len(axioms),
        )
        return result

    def rotate_lens(self) -> None:
        """Advance to the next lens in the rotation sequence."""
        self._rotation_index = (self._rotation_index + 1) % len(self._lenses)

    def current_lens(self) -> Lens:
        """Return the currently active lens (without advancing rotation)."""
        return self._lenses[self._rotation_index]

    def add_lens(self, lens: Lens) -> None:
        """Dynamically append a lens to the rotation pool."""
        self._lenses.append(lens)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _select_lens(self, attempt: int) -> Lens:
        """
        Return the lens for *attempt*.

        Uses ``_rotation_index`` which is advanced by :meth:`rotate_lens`.
        If the caller is auto-rotating, the index cycles round-robin.
        """
        return self._lenses[self._rotation_index % len(self._lenses)]

    def _select_axioms(self, lens: Lens, attempt: int) -> list[str]:
        """
        Select axioms from *lens* according to the active strategy.

        ``FULL``
            All axioms (capped at :attr:`_max_axioms`).

        ``SINGLE``
            The first axiom (index 0) — considered highest priority.
            On even attempts uses index 0; odd attempts uses index 1 (if
            available) for more variety.

        ``PROGRESSIVE``
            ``attempt + 1`` axioms, capped at :attr:`_max_axioms`.
        """
        source = list(lens.axioms)
        if self._randomise:
            self._rng.shuffle(source)

        match self._strategy:
            case InjectionStrategy.FULL:
                selected = source[: self._max_axioms]

            case InjectionStrategy.SINGLE:
                if not source:
                    raise InterferenceError(f"Lens {lens.name!r} has no axioms")
                idx = attempt % len(source)
                selected = [source[idx]]

            case InjectionStrategy.PROGRESSIVE:
                n = min(attempt + 1, self._max_axioms, len(source))
                selected = source[:n]

            case _:  # pragma: no cover
                selected = source[: self._max_axioms]

        return selected

    @staticmethod
    def _assemble_prefill(lens: Lens, axioms: list[str]) -> str:
        """
        Assemble the assistant prefill text from a lens and chosen axioms.

        The resulting text is designed to land the model squarely inside the
        foreign domain's reasoning frame.  It starts with the lens's
        ``injection_prompt`` (if any) and then enumerates the axioms as
        explicit operating principles.
        """
        parts: list[str] = []

        if lens.injection_prompt:
            parts.append(lens.injection_prompt.strip())
            parts.append("")  # blank line

        parts.append(f"Operating from the {lens.domain} domain — {lens.name}:")
        for i, axiom in enumerate(axioms, 1):
            parts.append(f"  [{i}] {axiom}")

        parts.append("")
        parts.append("Continuing from this frame of reference:")

        return "\n".join(parts)


# ---------------------------------------------------------------------------
# Convenience factory
# ---------------------------------------------------------------------------


def make_lens(
    name: str,
    domain: str,
    axioms: list[str],
    injection_prompt: str = "",
) -> Lens:
    """
    Convenience constructor for building a :class:`Lens` from plain data.

    Parameters
    ----------
    name:
        Lens name.
    domain:
        Domain category.
    axioms:
        List of axiom strings.
    injection_prompt:
        Optional framing text.

    Returns
    -------
    Lens
    """
    return Lens(
        name=name,
        domain=domain,
        axioms=axioms,
        injection_prompt=injection_prompt,
    )
