# Benchmark 040 — Post-Maturity Unfamiliar-Target Batch

This campaign is the first batch experiment after the closed CYDRA maturity gate.

It asks a different question from the maturity gate: whether the mature system can investigate a population of unfamiliar historical Solidity targets using its normal class-neutral hypothesis machinery.

The batch is discovery-first. It does not inject a vulnerability class, target function, state surface, exploit sequence, historical answer, or target-specific reasoning surface. The requested capability classes are the existing mature executable surfaces, not knowledge of the target's expected defect.

Ground truth is not supplied to the blind jobs. Any historical findings are used only after the blind run for evaluation.

The campaign records per-target extraction, hypotheses, experiments, execution, evidence, capability gaps, and throughput. A measured execution is not a confirmed vulnerability. Confirmed findings require the existing causal and reproducibility gates.

The six targets are pinned to immutable repository commits and were not part of the maturity closure matrix.

The campaign deliberately does not add contest-selection logic. Deployment selection remains a later phase.

## End condition

The campaign is complete when every target produces a structured artifact or an explicit, diagnosed failure artifact, and the aggregate report distinguishes:
- successful discovery/execution;
- no candidate extracted;
- capability gaps;
- execution failures;
- unmeasurable hypotheses;
- proposed observations;
- any later independently verified findings.

A green CI status alone is not considered the result.
