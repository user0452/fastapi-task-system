from app.evaluation.adaptive import benchmark_passes, run_benchmark


def test_adaptive_benchmark_is_reproducible_and_passes_acceptance_checks():
    result = run_benchmark()

    assert benchmark_passes(result)
    assert result["fixture_cases"] == 50
    assert result["v2"]["next_objective_accuracy"] == 1.0
    assert result["baseline_a_lowest_mastery"]["prerequisite_violation_rate"] > 0
