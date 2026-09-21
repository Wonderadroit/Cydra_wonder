# Benchmark 028 — strict blind epoch-boundary accounting

This campaign tests whether the normal CYDRA pipeline can independently select and causally validate a historical epoch-boundary accounting defect on an unfamiliar pinned Solidity target.

## Blind boundary

The benchmark does not supply:
- vulnerability class;
- target function;
- state surface;
- specialized reasoning-surface injection;
- custom experiment planner;
- exploit sequence;
- historical answer.

The only target-specific input to the normal investigate() call is the pinned LendingLedger.sol source.

## Target

- Repository: code-423n4/2024-01-canto
- Revision: 5e0d6f1f981993f83d0db862bcf1b2a49bb6ff50
- File: src/LendingLedger.sol

The historical Code4rena report documents an update_market() epoch-boundary calculation defect in this revision. The benchmark harness uses that historical record only for the post-selection causal control and evaluation, never to select the hypothesis.

## Required result

A valid success requires:
1. normal blind selection chooses the epoch-boundary hypothesis;
2. pinned vulnerable execution FAILS the accounting assertion;
3. isolated causal control PASSES;
4. canonical causal verification is VERIFIED;
5. independent vulnerable reproduction FAILS;
6. independent patched reproduction PASSES;
7. finding gate is READY.

This is a historical reproduction/backtest, not a claim of a newly discovered production vulnerability.