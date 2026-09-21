# Benchmark 036 — incentive-state divergence

This strict-blind holdout tests a strategic incentive failure: permissionless work can be manufactured at negligible cost while a later permissionless action pays the caller a protocol-funded reward.

Public Perennial judging records document related keeper-incentive failures where permissionless request creation could be repeated without paying the intended settlement/keeper cost, allowing callers to capture incentives and potentially drain an incentive pool. This fixture isolates that mechanism rather than reproducing the historical repository.

The blind runner supplies only the Solidity fixture to the normal investigation pipeline. It does not provide the mechanism name, target function, exploit sequence, expected invariant, historical answer, or selector override.

The vulnerable fixture lets an attacker call requestWork() for free and then commitWork() to receive 1 ETH. The patched control requires a 2 ETH value-bearing request before work becomes payout-eligible.

READY requires blind selection, vulnerable FAIL, patched PASS, causal verification, independent vulnerable FAIL, independent patched PASS, and the finding gate READY.
