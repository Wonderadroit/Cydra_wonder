# Benchmark 003 — Prediction 5A: Measurement Production

## Prediction

The arithmetic Foundry-generation/execution path can expose the numerical measurements required by `H-ARITH-quoteMint` as structured execution data without:

- parsing generated Solidity source text;
- parsing human-readable Foundry assertion/output text; or
- reimplementing the arithmetic invariant in Python.

The source of truth must be the executed Solidity program. The generated test must compute the measurements during execution and emit them through an explicit machine-readable execution mechanism. The Python execution layer may capture and decode that execution-produced data, but it must not independently calculate the measurements.

## Required structured shape

The execution result must expose a structured `measurements` field. For Benchmark 003 the expected values are:

```json
{
  "observed": 2,
  "reference": 1,
  "patched": 1,
  "delta": 1
}
```

`observed` is the vulnerable target's executed output, `reference` is the executed reference value, `patched` is the patched target's executed output, and `delta` is the vulnerable observation minus the reference.

## Interpretation boundaries

| Result | Interpretation |
|---|---|
| Measurements are emitted by executed Solidity and decoded into structured execution data | Prediction 5A confirmed |
| Measurements are recovered by parsing generated Solidity source | Falsified: Interface A is faked by source-text extraction |
| Measurements are recovered from human-readable Foundry output/assertion text | Falsified: output-format coupling rather than a measurement interface |
| Measurements are independently computed in Python | Falsified: reimplementation is not execution measurement |
| Only pass/fail/status crosses the execution boundary | Falsified: Interface A remains absent |
| Structured measurements exist but contain incorrect values | Falsified: measurement production is semantically incorrect |
| Arithmetic-specific execution result type is required instead of a generic measurement field | Falsified: the proposed generic execution interface did not generalize |

## Boundary

This prediction tests Interface A only. The Evidence schema and classifier remain untouched. A successful result proves measurement production/preservation at the execution boundary, not evidence-schema generalization or classification.
