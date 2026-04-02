from __future__ import annotations

from hephaestus.branchgenome import RejectionLedger, extract_structural_fingerprint


def test_ledger_records_and_scores_overlap(tmp_path) -> None:
    ledger = RejectionLedger(tmp_path / "branchgenome.jsonl")
    rejected = extract_structural_fingerprint(
        [
            "Retain successful response paths under later stress.",
            "Amplify prior winners instead of re-scoring from scratch.",
        ]
    )
    accepted = extract_structural_fingerprint(
        [
            "Use explicit decay windows to keep retained responses bounded.",
        ]
    )

    ledger.record(rejected, "decorative", "Collapsed into a queue-like baseline.")
    ledger.record(accepted, "accepted", "Survived translation and verification.")

    similar_to_rejected = extract_structural_fingerprint(
        ["Amplify prior winners under later stress with retained response paths."]
    )
    similar_to_accepted = extract_structural_fingerprint(
        ["Apply bounded decay windows to retained responses."]
    )

    assert ledger.overlap(similar_to_rejected) > 0.30
    assert ledger.overlap(similar_to_accepted) < ledger.overlap(similar_to_rejected)

    reloaded = RejectionLedger(tmp_path / "branchgenome.jsonl")
    assert reloaded.overlap(similar_to_rejected) == ledger.overlap(similar_to_rejected)
