# Adaptive Learning Benchmark Report

- Benchmark: `adaptive-benchmark-v1`
- Runtime: `2026-08-24T17:56:24.978647+00:00`
- Deterministic fixture cases: `5`

## Metrics

| 指标 | Baseline A：最低掌握度 | V2：前置关系 + Evidence Policy |
| --- | ---: | ---: |
| Next Objective Accuracy | 40.00% | 100.00% |
| Action Accuracy | 20.00% | 100.00% |
| Prerequisite Violation Rate | 40.00% | 0.00% |
| Unnecessary Practice Rate | 20.00% | 0.00% |
| Weakness Detection Rate | — | 100.00% |
| Misconception Detection Rate | — | 100.00% |

## Question Bank

- Objective-aligned selection match rate: **100.00%** (2 cases)
- Generation fallback rate: **0.00%**
- Invalid question rate in fixture: **0.00%**

## Calibration

- Brier score: **0.1467**
- Calibration gap: **0.1333**

## Case Results

| Case | Expected | V2 | Prerequisite violation | Unnecessary practice |
| --- | --- | --- | --- | --- |
| `prerequisite-first` | 1 / explain | 1 / explain | no | no |
| `misconception-repair` | 2 / misconception_repair | 2 / misconception_repair | no | no |
| `verify-low-confidence` | 1 / verify_mastery | 1 / verify_mastery | no | no |
| `spaced-review` | 1 / review | 1 / review | no | no |
| `stop-unnecessary-practice` | none / none | none / none | no | no |

## Limitations

- Fixtures are deterministic and do not represent a real student cohort.
- Calibration observations are frozen simulation observations, not longitudinal outcomes.
- Question generation fallback and subjective grading require separate provider-backed evaluation.

This report records a reproducible simulation benchmark; it is not evidence of a real-student learning effect.
