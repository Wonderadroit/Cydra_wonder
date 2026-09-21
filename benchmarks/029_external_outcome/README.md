# Benchmark 029 — strict blind external-call outcome integrity

This campaign tests whether CYDRA can derive and validate an external-call outcome invariant on an unfamiliar historical Solidity target through the normal blind pipeline.

## Blind boundary

The normal investigation receives only the pinned `Withdrawer.sol` source.

It does not receive the vulnerability class, target function, state surface, exploit sequence, historical answer, specialized reasoning-surface injection, or custom planner.

## Target

- repository: `code-423n4/2022-06-nested`
- revision: `b4a153c943d54755711a2f7b80cbbf3a5bb49d76`
- source: `contracts/Withdrawer.sol`

The historical report documents an unchecked `transferFrom()` return-value issue. Historical material is used only to define the post-selection causal control and evaluation boundary, never to select the hypothesis.

## Acceptance

Success requires blind selection of the external-outcome hypothesis, vulnerable execution FAIL, isolated causal control PASS, canonical causal verification VERIFIED, independent vulnerable FAIL, independent patched PASS, and finding gate READY.

The synthetic patch is a causal control, not a claim about the historical production remediation.

CI validation trigger: execute the benchmark on this revision.
