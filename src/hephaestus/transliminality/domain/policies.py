"""Strict vs soft channel policy enforcement.

The channel boundary is the most important governance rule in the
transliminality engine.  Speculative content must never poison strict
channels, and rejected content must never enter any positive channel.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum, auto

from hephaestus.transliminality.domain.enums import EpistemicState, TrustTier
from hephaestus.transliminality.domain.models import (
    AnalogicalMap,
    AnalogicalVerdict,
    KnowledgePackEntry,
    TransferOpportunity,
    TransliminalityConfig,
)


class Channel(StrEnum):
    """Output channel for a knowledge pack entry."""

    STRICT_BASELINE = auto()
    SOFT_CONTEXT = auto()
    STRICT_CONSTRAINT = auto()
    REJECTED = auto()


# Epistemic states that are never allowed in any positive channel
_ALWAYS_REJECTED: frozenset[EpistemicState] = frozenset({
    EpistemicState.REJECTED,
})

# Epistemic states eligible for strict channels
_STRICT_ELIGIBLE: frozenset[EpistemicState] = frozenset({
    EpistemicState.VERIFIED,
    EpistemicState.VALIDATED,
})

# Trust tiers eligible for strict channels
_STRICT_TRUST: frozenset[TrustTier] = frozenset({
    TrustTier.AUTHORITATIVE,
    TrustTier.INTERNAL_VERIFIED,
})

# Trust tiers banned from all channels
_BANNED_TRUST: frozenset[TrustTier] = frozenset({
    TrustTier.LOW_TRUST,
})


@dataclass(frozen=True)
class ChannelDecision:
    """Result of a channel policy evaluation."""

    channel: Channel
    reason: str


def classify_entry(
    entry: KnowledgePackEntry,
    config: TransliminalityConfig,
) -> ChannelDecision:
    """Determine which channel a knowledge pack entry belongs in.

    Returns STRICT_BASELINE, SOFT_CONTEXT, or REJECTED.  Never returns
    STRICT_CONSTRAINT — constraint channel entries are created separately
    via ``classify_map_for_constraint_channel()`` from analogy breaks.

    Rules (in order):
    1. Rejected or low-trust → REJECTED
    2. Contested → REJECTED
    3. Verified/validated + authoritative/internal-verified + high confidence → STRICT
    4. Hypothesis in soft channel if allowed → SOFT
    5. Exploratory → SOFT if meets soft threshold
    6. Everything else → REJECTED
    """
    # Rule 1: always-reject states and banned trust
    if entry.epistemic_state in _ALWAYS_REJECTED:
        return ChannelDecision(Channel.REJECTED, "rejected epistemic state")
    if entry.trust_tier in _BANNED_TRUST:
        return ChannelDecision(Channel.REJECTED, "low-trust tier")

    # Rule 2: contested content
    if entry.epistemic_state == EpistemicState.CONTESTED:
        return ChannelDecision(Channel.REJECTED, "contested content")

    # Rule 3: strict channel eligibility
    if (
        entry.epistemic_state in _STRICT_ELIGIBLE
        and entry.trust_tier in _STRICT_TRUST
        and entry.salience >= config.strict_channel_min_confidence
    ):
        return ChannelDecision(Channel.STRICT_BASELINE, "verified high-trust content")

    # Rule 4: hypothesis in soft channel
    if entry.epistemic_state == EpistemicState.HYPOTHESIS:
        if (
            config.allow_hypothesis_in_soft_channel
            and entry.salience >= config.soft_channel_min_confidence
        ):
            return ChannelDecision(Channel.SOFT_CONTEXT, "hypothesis above soft threshold")
        return ChannelDecision(Channel.REJECTED, "hypothesis below threshold or disallowed")

    # Rule 5: exploratory content → soft channel
    if entry.epistemic_state == EpistemicState.EXPLORATORY:
        if entry.salience >= config.soft_channel_min_confidence:
            return ChannelDecision(Channel.SOFT_CONTEXT, "exploratory above soft threshold")
        return ChannelDecision(Channel.REJECTED, "exploratory below soft threshold")

    # Rule 6: validated but not high-trust → soft channel
    if entry.epistemic_state in _STRICT_ELIGIBLE:
        if entry.salience >= config.soft_channel_min_confidence:
            return ChannelDecision(Channel.SOFT_CONTEXT, "validated but not high-trust")
        return ChannelDecision(Channel.REJECTED, "below soft threshold")

    return ChannelDecision(Channel.REJECTED, "no matching policy rule")


def classify_map_for_constraint_channel(
    amap: AnalogicalMap,
    config: TransliminalityConfig,
) -> ChannelDecision:
    """Determine if an analogical map's breaks should enter the strict constraint channel.

    Analogy breaks, broken constraints, and caveats feed the constraint
    channel so Pantheon can attack weak transfers.
    """
    if amap.verdict == AnalogicalVerdict.INVALID:
        return ChannelDecision(Channel.REJECTED, "invalid analogy — not injected")

    if (
        (amap.analogy_breaks or amap.broken_constraints)
        and amap.confidence >= config.soft_channel_min_confidence
    ):
        return ChannelDecision(
            Channel.STRICT_CONSTRAINT,
            "analogy has breaks/broken constraints worth flagging",
        )
    return ChannelDecision(Channel.REJECTED, "no constraint-worthy content")


def can_promote_to_strict(
    opportunity: TransferOpportunity,
    amap: AnalogicalMap,
    config: TransliminalityConfig,
) -> bool:
    """Check whether a transfer opportunity can be promoted to strict channels.

    Promotion requires:
    - underlying map is VALID (not PARTIAL/WEAK)
    - confidence meets strict threshold
    - no unresolved critical caveats
    - map has provenance refs (derivation chain exists)
    """
    if amap.verdict != AnalogicalVerdict.VALID:
        return False
    if opportunity.confidence < config.strict_channel_min_confidence:
        return False
    critical_caveats = [c for c in opportunity.caveats if c.severity >= 0.8]
    if critical_caveats:
        return False
    return bool(amap.provenance_refs)
