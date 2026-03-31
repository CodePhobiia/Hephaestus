"""
Tests for the Cognitive Interference Engine.
"""

from __future__ import annotations

import pytest

from hephaestus.deepforge.exceptions import ConfigurationError, InterferenceError
from hephaestus.deepforge.interference import (
    CognitiveInterferenceEngine,
    InjectionStrategy,
    Lens,
    InjectionResult,
    make_lens,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def biology_lens() -> Lens:
    return Lens(
        name="Immune System",
        domain="biology",
        axioms=[
            "Trust is earned through molecular handshake, not declaration.",
            "Memory is distributed; no single cell holds the full picture.",
            "Response scales with threat severity.",
            "The system attacks self-similar threats preferentially.",
            "Recovery creates permanent readiness.",
        ],
        injection_prompt="You are reasoning as if this problem exists inside a biological immune system.",
    )


@pytest.fixture
def physics_lens() -> Lens:
    return Lens(
        name="Thermodynamics",
        domain="physics",
        axioms=[
            "Entropy always increases in isolated systems.",
            "Energy cannot be created or destroyed, only transformed.",
            "Work flows from high potential to low potential.",
        ],
    )


# ---------------------------------------------------------------------------
# Lens construction
# ---------------------------------------------------------------------------


class TestLens:
    def test_basic_construction(self, biology_lens: Lens) -> None:
        assert biology_lens.name == "Immune System"
        assert biology_lens.domain == "biology"
        assert len(biology_lens.axioms) == 5

    def test_empty_axioms_raises(self) -> None:
        with pytest.raises(ConfigurationError, match="no axioms"):
            Lens(name="Empty", domain="test", axioms=[])

    def test_make_lens_factory(self) -> None:
        lens = make_lens(
            name="Test",
            domain="test",
            axioms=["Axiom 1", "Axiom 2"],
            injection_prompt="Testing.",
        )
        assert lens.name == "Test"
        assert len(lens.axioms) == 2
        assert lens.injection_prompt == "Testing."


# ---------------------------------------------------------------------------
# CognitiveInterferenceEngine
# ---------------------------------------------------------------------------


class TestCognitiveInterferenceEngine:
    def test_single_lens_construction(self, biology_lens: Lens) -> None:
        engine = CognitiveInterferenceEngine(biology_lens)
        assert engine.current_lens().name == "Immune System"

    def test_multiple_lens_construction(self, biology_lens: Lens, physics_lens: Lens) -> None:
        engine = CognitiveInterferenceEngine([biology_lens, physics_lens])
        assert engine.current_lens().name == "Immune System"

    def test_empty_lenses_raises(self) -> None:
        with pytest.raises(ConfigurationError):
            CognitiveInterferenceEngine([])

    def test_build_injection_full_strategy(self, biology_lens: Lens) -> None:
        engine = CognitiveInterferenceEngine(
            biology_lens,
            strategy=InjectionStrategy.FULL,
            max_axioms_per_injection=5,
        )
        result = engine.build_injection(attempt=0)
        assert isinstance(result, InjectionResult)
        assert len(result.axioms_used) == 5
        assert result.strategy == InjectionStrategy.FULL
        assert result.lens_name == "Immune System"
        assert "biology" in result.prefill
        assert "Immune System" in result.prefill

    def test_build_injection_single_strategy(self, biology_lens: Lens) -> None:
        engine = CognitiveInterferenceEngine(biology_lens, strategy=InjectionStrategy.SINGLE)
        result0 = engine.build_injection(attempt=0)
        result1 = engine.build_injection(attempt=1)
        assert len(result0.axioms_used) == 1
        assert len(result1.axioms_used) == 1
        # attempt 0 picks index 0, attempt 1 picks index 1
        assert result0.axioms_used[0] == biology_lens.axioms[0]
        assert result1.axioms_used[0] == biology_lens.axioms[1]

    def test_build_injection_progressive_strategy(self, biology_lens: Lens) -> None:
        engine = CognitiveInterferenceEngine(
            biology_lens,
            strategy=InjectionStrategy.PROGRESSIVE,
            max_axioms_per_injection=3,
        )
        result0 = engine.build_injection(attempt=0)
        result1 = engine.build_injection(attempt=1)
        result2 = engine.build_injection(attempt=2)
        assert len(result0.axioms_used) == 1
        assert len(result1.axioms_used) == 2
        assert len(result2.axioms_used) == 3

    def test_progressive_caps_at_max(self, biology_lens: Lens) -> None:
        engine = CognitiveInterferenceEngine(
            biology_lens,
            strategy=InjectionStrategy.PROGRESSIVE,
            max_axioms_per_injection=2,
        )
        # Attempt 10 should still be capped at 2
        result = engine.build_injection(attempt=10)
        assert len(result.axioms_used) <= 2

    def test_full_strategy_caps_at_max(self, biology_lens: Lens) -> None:
        engine = CognitiveInterferenceEngine(
            biology_lens,
            strategy=InjectionStrategy.FULL,
            max_axioms_per_injection=3,
        )
        result = engine.build_injection(attempt=0)
        assert len(result.axioms_used) == 3  # 5 axioms, capped at 3

    def test_lens_rotation(self, biology_lens: Lens, physics_lens: Lens) -> None:
        engine = CognitiveInterferenceEngine([biology_lens, physics_lens])
        assert engine.current_lens().name == "Immune System"
        engine.rotate_lens()
        assert engine.current_lens().name == "Thermodynamics"
        engine.rotate_lens()
        # Should wrap around
        assert engine.current_lens().name == "Immune System"

    def test_add_lens_dynamically(self, biology_lens: Lens, physics_lens: Lens) -> None:
        engine = CognitiveInterferenceEngine(biology_lens)
        engine.add_lens(physics_lens)
        engine.rotate_lens()
        assert engine.current_lens().name == "Thermodynamics"

    def test_injection_prompt_included_in_prefill(self, biology_lens: Lens) -> None:
        engine = CognitiveInterferenceEngine(biology_lens, strategy=InjectionStrategy.FULL)
        result = engine.build_injection(attempt=0)
        assert biology_lens.injection_prompt in result.prefill

    def test_no_injection_prompt_still_works(self, physics_lens: Lens) -> None:
        # physics_lens has no injection_prompt
        engine = CognitiveInterferenceEngine(physics_lens, strategy=InjectionStrategy.FULL)
        result = engine.build_injection(attempt=0)
        assert len(result.axioms_used) >= 1
        assert "physics" in result.prefill

    def test_randomise_axiom_order(self, biology_lens: Lens) -> None:
        """With different seeds, axiom order should vary (not always the same)."""
        engine_a = CognitiveInterferenceEngine(
            biology_lens, strategy=InjectionStrategy.FULL, randomise_axiom_order=True, seed=1
        )
        engine_b = CognitiveInterferenceEngine(
            biology_lens, strategy=InjectionStrategy.FULL, randomise_axiom_order=True, seed=99
        )
        result_a = engine_a.build_injection(attempt=0)
        result_b = engine_b.build_injection(attempt=0)
        # Both should have all 5 axioms but potentially in different order
        assert set(result_a.axioms_used) == set(result_b.axioms_used)

    def test_single_strategy_wraps_index(self) -> None:
        """SINGLE strategy should not raise IndexError when attempt > len(axioms)."""
        lens = Lens(name="Small", domain="test", axioms=["A1", "A2"])
        engine = CognitiveInterferenceEngine(lens, strategy=InjectionStrategy.SINGLE)
        # attempt 5: 5 % 2 = 1, so axioms[1] = "A2"
        result = engine.build_injection(attempt=5)
        assert result.axioms_used[0] == "A2"
        assert len(result.axioms_used) == 1
        # attempt 4: 4 % 2 = 0, so axioms[0] = "A1"
        result2 = engine.build_injection(attempt=4)
        assert result2.axioms_used[0] == "A1"

    def test_assemble_prefill_contains_axioms(self, biology_lens: Lens) -> None:
        engine = CognitiveInterferenceEngine(biology_lens, strategy=InjectionStrategy.FULL)
        result = engine.build_injection(attempt=0)
        for axiom in result.axioms_used:
            assert axiom in result.prefill

    def test_prefill_has_continuation_marker(self, biology_lens: Lens) -> None:
        engine = CognitiveInterferenceEngine(biology_lens)
        result = engine.build_injection(attempt=0)
        assert "Continuing from this frame" in result.prefill
