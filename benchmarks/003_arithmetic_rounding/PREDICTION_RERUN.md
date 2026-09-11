# Benchmark 003 — Arithmetic Rule Rerun Prediction

## Purpose

The first Benchmark 003 run established an extraction-layer boundary: Solidity extraction succeeded, but no arithmetic invariant rule fired. This rerun tests the arithmetic rule itself while leaving the downstream Hypothesis, Experiment, Evidence, and classifier schemas unchanged.

## Locked prediction

After adding only the arithmetic extraction rule and rerunning the same arithmetic fixture:

| Stage | Prediction |
|---|---|
| 1. Arithmetic rule fires and produces an `INV-ARITH-*` invariant | YES |
| 2. Existing Hypothesis schema carries the arithmetic hypothesis without field-mangling or new required fields | YES |
| 3. Existing Experiment schema generates an arithmetic assertion (`assertEq`/`assertLe`) rather than falling back to `vm.expectRevert` | YES |
| 4. Existing Evidence schema records numerical payload (`vulnerable_value`, `patched_value`, `delta`) rather than status-only evidence | YES |
| 5. Existing classifier uses the same differential causal rule and produces `confirmed` for the vulnerable/patched pair | YES |

## Falsification discipline

The first unexpected NO is the boundary of the current abstraction. `NOT_REACHED` is not a pass or failure for later stages.

No Hypothesis, Experiment, Evidence, or classifier schema changes are permitted before the rerun result is recorded and compared with this prediction.

## Scope

The only reasoning change permitted before the rerun is the arithmetic extraction rule required to expose the arithmetic invariant. The benchmark fixture, downstream schemas, experiment generator, evidence model, and classifier must not be pre-adjusted to make the prediction pass.
