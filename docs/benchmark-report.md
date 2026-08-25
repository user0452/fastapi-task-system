# Adaptive Learning Benchmark Report

- Benchmark: `adaptive-benchmark-v2-stage2`
- Runtime: `2026-08-25T05:00:46.807503+00:00`
- Fixed policy cases: `50`

## Policy metrics

| Strategy | Objective accuracy | Action accuracy | Prerequisite violations | Unnecessary practice |
| --- | ---: | ---: | ---: | ---: |
| Baseline A: lowest mastery | 70.00% | 70.00% | 10.00% | 10.00% |
| Baseline B: random/simple baseline | 36.00% | 64.00% | 8.00% | 46.00% |
| Baseline C: mastery + prerequisite | 80.00% | 70.00% | 0.00% | 10.00% |
| V2: full evidence policy | 100.00% | 100.00% | 0.00% | 0.00% |

## V2 diagnostic metrics

- Weakness detection: **100.00%**
- Misconception detection: **100.00%**
- Policy failures: **0**

## Coverage

- confidence: 5 fixed cases
- contradictory-evidence: 5 fixed cases
- goal-relevance: 5 fixed cases
- importance: 5 fixed cases
- misconception: 5 fixed cases
- prerequisite: 5 fixed cases
- spacing: 5 fixed cases
- uncertainty: 5 fixed cases
- unnecessary-practice: 5 fixed cases
- weakness: 5 fixed cases

## Question bank

- Fixed question-selection cases: **20**
- Retrieval match rate: **100.00%**
- Generation calls for high-quality real questions: **0**
- Invalid question rate: **0.00%**

## Grader and state

- Fixed grader cases: **20**, accuracy **100.00%**
- State sequence cases: **5**, pass rate **100.00%**
- Curriculum fixture cases: **10**, accuracy **100.00%**

## Ablations

| Ablation | Objective accuracy | Action accuracy | Prerequisite violations |
| --- | ---: | ---: | ---: |
| no_prerequisite | 90.00% | 100.00% | 10.00% |
| no_confidence | 70.00% | 90.00% | 0.00% |
| no_misconception | 100.00% | 90.00% | 0.00% |
| no_spacing | 90.00% | 90.00% | 0.00% |

## Limitations

- These are deterministic fixtures and do not represent a real student cohort.
- State sequence checks are simulation checks, not longitudinal outcomes.
- Provider-backed subjective grading and generated-question quality need a separate live-provider evaluation.

This report is a reproducible simulation benchmark, not evidence of a real-student learning effect.
