# Benchmark 043 — Post-Maturity Multi-Target Causal Discovery

This campaign tests the next boundary after Benchmark 042: whether CYDRA can perform blind-to-causal discovery across multiple unfamiliar real targets rather than proving the loop on one target only.

Targets are pinned independently:
- RabbitHole Quest Protocol: a broken minter authorization modifier.
- Debt DAO Line of Credit: revenue-claim configuration binding that can route a push-payment claim to the treasury instead of escrow.

The blind phase runs independently per target using the normal class-neutral runner. It receives no vulnerability class, target function, exploit sequence, patch, historical answer, or selector override. The evaluator checks only after blind selection whether the selected hypothesis semantically binds the historical computation.

Causal validation then uses independently authored controls:
- vulnerable target + invariant test must fail;
- patched target + same invariant test must pass;
- an independent vulnerable reproduction must fail;
- an independent patched reproduction must pass.

The campaign deliberately preserves misses and execution blockers instead of teaching the selector the historical answer. A target that is not selected correctly is a measured generalization failure, not silently converted into a pass.

Success requires every target in the campaign to reach an evidence-backed READY gate and the campaign to contain at least two distinct targets with reproducible causal findings.


Canonical validation rerun after generic execution/planning repairs merged to main (PRs #178 and #179).
