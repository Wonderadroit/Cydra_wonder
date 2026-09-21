# Benchmark 026 — strict blind control-flow

This is an adversarial generalization test, not a new detector.

CYDRA receives only the pinned historical target source through its normal `investigate()` pipeline. The run supplies no vulnerability class, target function, state surface, reasoning-surface injection, custom planner, exploit sequence, or historical answer.

The target is the unfamiliar pinned Venus Prime implementation at revision `23f5db740d8a794ac563ac32195b675c53042bb4`. The historical control-flow defect is used only after blind selection to evaluate whether the selected hypothesis matches the demonstrated mechanism.

Success requires the normal class-neutral selector to choose a control-flow hypothesis, then requires:
- vulnerable target execution FAIL;
- isolated causal control PASS;
- canonical causal verification VERIFIED;
- independent vulnerable reproduction FAIL;
- independent patched reproduction PASS;
- finding gate READY.

If the selector chooses another hypothesis, the benchmark fails deliberately. That failure is evidence about CYDRA's research-loop selection/generalization and must not be repaired by adding benchmark-specific scoring or forcing this target's answer.

The Solidity maturity gate remains open regardless of this single campaign.
