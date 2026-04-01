"""
Crutch Filter — suppress overused AI-typical words at generation time.

Two mechanisms, one per provider family:

- **OpenAI**: ``logit_bias`` dict mapping crutch-word token IDs to ``-100``
  (hard ban).  Uses ``tiktoken`` for token-ID lookup.
- **Claude**: negative-constraint string injected into the system prompt
  (Anthropic has no logit_bias knob).

Usage::

    from hephaestus.deepforge.crutch_filter import CrutchFilter

    cf = CrutchFilter()

    # For OpenAI adapter — pass to generate(logit_bias=...)
    bias = cf.get_logit_bias_for_openai(encoding_name="o200k_base")

    # For Claude adapter — prepend to system prompt
    constraint = cf.get_negative_constraint_for_claude()
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# The canonical crutch-word list (200+)
# ---------------------------------------------------------------------------

CRUTCH_WORDS: list[str] = [
    # --- Tier 1: the worst offenders ---
    "delve",
    "tapestry",
    "crucial",
    "multifaceted",
    "testament",
    "landscape",
    "paradigm",
    "synergy",
    "holistic",
    "nuanced",
    "leverage",
    "robust",
    "comprehensive",
    "innovative",
    "cutting-edge",
    "groundbreaking",
    "transformative",
    "seamless",
    "streamline",
    "empower",
    "foster",
    "cultivate",
    "bolster",
    "underscore",
    "underpin",
    "spearhead",
    "cornerstone",
    "linchpin",
    "bedrock",
    "catalyst",
    "pivotal",
    "paramount",
    "instrumental",
    "indispensable",
    "imperative",
    "quintessential",
    "epitomize",
    "embody",
    "encapsulate",
    "encompasses",
    "interplay",
    "intricate",
    "intricacies",
    "navigate",
    "navigating",
    "realm",
    "realm of",
    "sphere",
    "arena",
    "domain",
    "facet",
    "dimension",
    "spectrum",
    "myriad",
    "plethora",
    "myriad of",
    "plethora of",
    "array of",
    "wealth of",
    "gamut",
    "breadth",
    # --- Tier 2: filler amplifiers ---
    "notably",
    "importantly",
    "significantly",
    "fundamentally",
    "inherently",
    "intrinsically",
    "ostensibly",
    "arguably",
    "undeniably",
    "undoubtedly",
    "unequivocally",
    "profoundly",
    "remarkably",
    "exceedingly",
    "tremendously",
    "substantially",
    "exponentially",
    "dramatically",
    "drastically",
    "meteoric",
    # --- Tier 3: corporate-speak ---
    "stakeholder",
    "stakeholders",
    "ecosystem",
    "value proposition",
    "actionable",
    "scalable",
    "best practices",
    "thought leadership",
    "synergize",
    "operationalize",
    "incentivize",
    "monetize",
    "optimize",
    "maximize",
    "amplify",
    "accelerate",
    "facilitate",
    "orchestrate",
    "spearheading",
    "championing",
    "pioneering",
    "trailblazing",
    "game-changer",
    "game-changing",
    "paradigm shift",
    "paradigm-shifting",
    "disruptive",
    "disruption",
    "bleeding-edge",
    "state-of-the-art",
    "next-generation",
    "world-class",
    "best-in-class",
    "mission-critical",
    "end-to-end",
    "turnkey",
    "out-of-the-box",
    "plug-and-play",
    "future-proof",
    "forward-thinking",
    # --- Tier 4: hedging and weasel words ---
    "it's worth noting",
    "it is worth noting",
    "it bears mentioning",
    "needless to say",
    "it goes without saying",
    "as we all know",
    "it should be noted",
    "one might argue",
    "it could be argued",
    "in a nutshell",
    "at the end of the day",
    "when all is said and done",
    "the fact of the matter",
    "by and large",
    "for all intents and purposes",
    "in no uncertain terms",
    "without a doubt",
    # --- Tier 5: AI purple prose ---
    "tapestry of",
    "rich tapestry",
    "vibrant tapestry",
    "intricate tapestry",
    "dance of",
    "delicate dance",
    "intricate dance",
    "symphony of",
    "canvas of",
    "mosaic of",
    "kaleidoscope of",
    "labyrinth of",
    "crucible of",
    "nexus of",
    "confluence of",
    "convergence of",
    "intersection of",
    "crossroads of",
    "fulcrum of",
    "epicenter of",
    "vanguard of",
    "forefront of",
    "frontier of",
    "harbinger of",
    "beacon of",
    "bastion of",
    # --- Tier 6: more filler adjectives/adverbs ---
    "meticulous",
    "meticulously",
    "painstaking",
    "painstakingly",
    "rigorous",
    "rigorously",
    "exhaustive",
    "exhaustively",
    "thorough",
    "thoroughly",
    "compelling",
    "captivating",
    "riveting",
    "thought-provoking",
    "awe-inspiring",
    "breathtaking",
    "staggering",
    "unprecedented",
    "unparalleled",
    "unmatched",
    "unrivaled",
    "unsurpassed",
    "invaluable",
    "indispensable",
    "irreplaceable",
    "immeasurable",
    "incalculable",
    "innumerable",
    "resonate",
    "resonates",
    "resonating",
    "underscore",
    "underscores",
    "underscoring",
    "illuminate",
    "illuminates",
    "illuminating",
    "elucidate",
    "elucidates",
    "elucidating",
    "juxtapose",
    "juxtaposition",
    "dichotomy",
    "duality",
    "enigma",
    "conundrum",
    "quandary",
    "paradox",
    "oxymoron",
    "zeitgeist",
    "ethos",
    "milieu",
    # --- Tier 7: transition bloat ---
    "moreover",
    "furthermore",
    "additionally",
    "consequently",
    "subsequently",
    "henceforth",
    "thereby",
    "thereof",
    "therein",
    "wherein",
    "whereby",
    "notwithstanding",
    "nevertheless",
    "nonetheless",
    "inasmuch",
    "insofar",
    "vis-a-vis",
    # --- Tier 8: V2 spec banned words (Section 4 Rule 5) ---
    "novel",
    "unique",
    "revolutionary",
    "reimagine",
    "revolutionize",
    "utilize",
    "harness",
    "unlock",
    "unpack",
    "powerful",
    # --- Tier 9: V2 spec banned phrases (Section 4 Rule 5) ---
    "at its core",
    "in other words",
    "interestingly",
    "to put it simply",
    "the beauty of this approach",
    "this is where it gets interesting",
    "what makes this unique",
    "the key insight",
    "perhaps most importantly",
    "one could argue",
    "it remains to be seen",
    "in today's world",
    "in an era of",
    "when we think about",
    "the challenge lies in",
    "at the intersection of",
    "bridge the gap",
    "deep dive",
    "step back and consider",
    "the elephant in the room",
    "food for thought",
    "take a closer look",
]


class CrutchFilter:
    """
    Suppresses overused AI-typical words at generation time.

    Provides two output modes — one per provider family:

    - :meth:`get_logit_bias_for_openai` returns a ``logit_bias`` dict
      (token-ID → ``-100``) suitable for the OpenAI completions API.
    - :meth:`get_negative_constraint_for_claude` returns a negative-
      constraint string for injection into the Claude system prompt.
    """

    def __init__(self, extra_words: list[str] | None = None) -> None:
        self.words = list(CRUTCH_WORDS)
        if extra_words:
            self.words.extend(extra_words)

    # ------------------------------------------------------------------
    # OpenAI: logit_bias via tiktoken
    # ------------------------------------------------------------------

    def get_logit_bias_for_openai(
        self,
        encoding_name: str = "o200k_base",
        bias_value: int = -100,
    ) -> dict[int, int]:
        """
        Return a ``logit_bias`` dict mapping crutch-word token IDs to
        *bias_value* (default ``-100``, i.e. hard ban).

        Uses ``tiktoken`` for token-ID resolution.  Multi-token words
        have each constituent token biased.

        Parameters
        ----------
        encoding_name:
            The tiktoken encoding to use (default ``o200k_base`` for
            GPT-4o / o3 / o4-mini).
        bias_value:
            Logit bias value.  ``-100`` = hard ban.
        """
        import tiktoken

        enc = tiktoken.get_encoding(encoding_name)
        bias: dict[int, int] = {}

        for word in self.words:
            token_ids = enc.encode(word, disallowed_special=())
            for tid in token_ids:
                bias[tid] = bias_value

        logger.debug(
            "CrutchFilter: %d crutch words -> %d unique biased tokens (encoding=%s)",
            len(self.words),
            len(bias),
            encoding_name,
        )
        return bias

    # ------------------------------------------------------------------
    # Claude: negative constraint string for system prompt
    # ------------------------------------------------------------------

    def get_negative_constraint_for_claude(self) -> str:
        """
        Return a negative-constraint string for injection into the
        Claude system prompt.

        Since Anthropic has no logit_bias parameter, we instruct the
        model via explicit constraint language.
        """
        # Group into chunks for readability
        word_list = ", ".join(f'"{w}"' for w in self.words)

        return (
            "[NEGATIVE CONSTRAINT — HARD BAN]\n"
            "You MUST NOT use any of the following words or phrases in your "
            "response. If you catch yourself about to write one, replace it "
            "with a concrete, specific term instead. Violations make your "
            "output worthless.\n\n"
            f"BANNED: {word_list}\n\n"
            "Use plain, direct language. Prefer concrete nouns and active "
            "verbs over abstract filler."
        )


# ---------------------------------------------------------------------------
# Module-level convenience functions
# ---------------------------------------------------------------------------


def get_logit_bias_for_openai(
    encoding_name: str = "o200k_base",
    bias_value: int = -100,
) -> dict[int, int]:
    """Convenience wrapper around :meth:`CrutchFilter.get_logit_bias_for_openai`."""
    return CrutchFilter().get_logit_bias_for_openai(encoding_name, bias_value)


def get_negative_constraint_for_claude() -> str:
    """Convenience wrapper around :meth:`CrutchFilter.get_negative_constraint_for_claude`."""
    return CrutchFilter().get_negative_constraint_for_claude()
