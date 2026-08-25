from datetime import datetime, timezone

from app.modules.adaptive.policy import confidence_components

NOW = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)


def _evidence(
    score: float,
    *,
    question_id: int,
    coverage_type: str = "direct",
    difficulty: str = "medium",
    source_type: str = "practice",
) -> dict[str, object]:
    return {
        "score": score,
        "question_id": question_id,
        "coverage_type": coverage_type,
        "difficulty": difficulty,
        "source_type": source_type,
        "grader_type": "deterministic-criterion-rubric",
        "created_at": NOW.isoformat(),
    }


def test_consistent_evidence_has_higher_confidence_than_contradictory_evidence():
    consistent = confidence_components(
        {"attempt_count": 2},
        [_evidence(1.0, question_id=1), _evidence(1.0, question_id=1)],
        current_score=1.0,
        current_difficulty="medium",
        current_question_id=1,
        current_coverage_type="direct",
        current_source_type="practice",
        now=NOW,
    )
    contradictory = confidence_components(
        {"attempt_count": 3},
        [_evidence(1.0, question_id=1), _evidence(0.0, question_id=1), _evidence(1.0, question_id=1)],
        current_score=0.0,
        current_difficulty="medium",
        current_question_id=1,
        current_coverage_type="direct",
        current_source_type="practice",
        now=NOW,
    )

    assert consistent["consistency"] > contradictory["consistency"]
    assert consistent["confidence"] > contradictory["confidence"]


def test_diverse_evidence_is_not_equivalent_to_repeating_one_easy_question():
    repeated = confidence_components(
        {"attempt_count": 4},
        [_evidence(1.0, question_id=1, difficulty="easy") for _ in range(4)],
        current_score=1.0,
        current_difficulty="easy",
        current_question_id=1,
        current_coverage_type="direct",
        current_source_type="practice",
        now=NOW,
    )
    diverse = confidence_components(
        {"attempt_count": 4},
        [
            _evidence(1.0, question_id=1, coverage_type="direct", difficulty="easy", source_type="diagnostic"),
            _evidence(1.0, question_id=2, coverage_type="scenario", difficulty="medium", source_type="practice"),
            _evidence(1.0, question_id=3, coverage_type="transfer", difficulty="hard", source_type="review"),
            _evidence(1.0, question_id=4, coverage_type="review", difficulty="medium", source_type="tutor_check"),
        ],
        current_score=1.0,
        current_difficulty="hard",
        current_question_id=5,
        current_coverage_type="transfer",
        current_source_type="assessment",
        now=NOW,
    )

    assert diverse["diversity"] > repeated["diversity"]
    assert diverse["confidence"] > repeated["confidence"]
