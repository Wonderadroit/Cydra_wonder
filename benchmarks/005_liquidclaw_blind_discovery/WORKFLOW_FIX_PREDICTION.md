# Benchmark 005 — workflow harness fix prediction

## Prediction

The Benchmark 005 workflow will now install `pytest` before the existing acceptance step. The benchmark will therefore complete the acceptance step and proceed to the frozen LiquidClaw analysis, assuming no unrelated harness failure occurs.

## Scope

This prediction concerns only workflow orchestration. It does not change any CYDRA extraction rule, planner, generator, Evidence schema, transport, classifier, target-specific hypothesis, or reasoning architecture.

## Locked before rerun

This prediction is committed separately from the earlier Benchmark 005 prediction-history correction and before the rerun.
