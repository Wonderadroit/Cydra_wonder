# Benchmark 037 — strict-blind keeper zero-work incentive

This is a strict-blind holdout for a materially different incentive-liveness shape:
a reward-bearing modifier can pay the caller even when the function performs zero
qualifying work because an empty iterable input is accepted.

Historical provenance: Sherlock's 2023 Perennial V2 judging issue #50 reported that
KeeperFactory.settle could be called with four empty arrays. The keep modifier
could still pay the caller although the settlement loop executed zero iterations.
The report states that the attack could be repeated to drain keeper fees.

This benchmark uses an executable reduction of that security-relevant target shape.
It is intentionally not presented as the full Perennial deployment or as a claim
about the historical repository beyond the documented issue.

## Blind boundary

The blind investigation receives only Target.sol. It is not given:
- the historical issue;
- the name of the vulnerability class;
- the vulnerable condition;
- the exploit sequence;
- the expected invariant;
- the patch;
- a target-specific selector override.

The generic incentive reasoning surface must infer the reward-bearing path from
the modifier and the zero-work loop topology.

## Acceptance

READY requires:
1. blind selection of the generic incentive-liveness hypothesis;
2. vulnerable execution FAIL;
3. patched execution PASS;
4. canonical causal verification;
5. independent vulnerable FAIL;
6. independent patched PASS;
7. reproducible finding-gate READY.

This benchmark is a reasoning-capability regression, not a historical-answer oracle.
