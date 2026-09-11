# Benchmark 003 — Pre-run Prediction

## Class

Arithmetic invariant — rounding / precision / truncation.

## Prediction

The existing CYDRA pipeline will handle the arithmetic benchmark without reasoning-engine or schema changes.

| Stage | Prediction |
|---|---|
| 1. Extraction rule fires on the arithmetic fixture | YES |
| 2. Existing Hypothesis schema represents the arithmetic hypothesis without changes | YES |
| 3. Existing Experiment schema represents the arithmetic test without changes | YES |
| 4. Existing Evidence schema records the executed arithmetic result without changes | YES |
| 5. Existing classifier confirms/rejects using the same differential rule | YES |

## Falsification rule

The first unexpected NO is the boundary of the current abstraction. No reasoning-engine or schema fix is permitted before the actual result is recorded and compared with this prediction.

## Experimental discipline

Prediction is committed before the Benchmark 003 fixture and runner are added. The benchmark must exercise the existing pipeline rather than bypassing it with a benchmark-specific reasoning path.
