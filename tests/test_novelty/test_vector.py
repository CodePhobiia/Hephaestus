from __future__ import annotations

from hephaestus.novelty import NoveltyVector


def test_novelty_vector_scores_reward_distance_and_viability() -> None:
    vector = NoveltyVector(
        banality_similarity=0.12,
        prior_art_similarity=0.18,
        branch_family_distance=0.72,
        source_domain_distance=0.81,
        mechanism_distance=0.77,
        evaluator_gain=0.69,
        subtraction_delta=0.74,
        critic_disagreement=0.41,
    )

    assert 0.0 <= vector.creativity_score() <= 1.0
    assert 0.0 <= vector.load_bearing_score() <= 1.0
    assert vector.load_bearing_score() >= 0.5
