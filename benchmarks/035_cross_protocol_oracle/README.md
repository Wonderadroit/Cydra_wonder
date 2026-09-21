# Benchmark 035 — cross-protocol oracle/state composition

This benchmark tests a genuinely cross-protocol interaction shape inspired by the
June 2023 Sturdy Finance incident involving a Balancer-dependent price oracle.

The historical incident combined a lending protocol, an oracle, and Balancer pool
state: Sturdy consumed a BPT price derived from Balancer state while the pool was
inside an external-callback transition. Public incident analysis describes the
price changing from roughly 1.03 ETH to 3.01 ETH during the callback and the
lending protocol accepting a collateral decision on that transient value.

This benchmark is an isolated historical-style fixture, not a claim that this exact
fixture was deployed. Its purpose is to test the abstraction: a consumer protocol
trusts a view derived from another protocol's transient state, and a state-changing
decision becomes unsafe across that boundary.

## Blind boundary

CYDRA receives only the fixture source through the normal investigation pipeline.
The benchmark runner does not provide:

- the vulnerability class;
- the vulnerable function;
- the exploit sequence;
- the expected invariant;
- the historical answer;
- a specialized selector;
- a target-specific reasoning surface.

The runner permits CYDRA's existing class-neutral read-only/cross-contract reasoning
to form and select hypotheses. If the investigation exposes an orchestration gap,
the fix must remain generic.

## Causal test

The vulnerable path should allow an attacker callback from TransientPool.exitPool
to cause CollateralLending.disableSecondaryCollateral() to consume an inflated
oracle value. The post-callback pool state returns to the honest value, but the
secondary collateral has already been released.

The patched control rejects the oracle read while the external protocol is in its
transient state.

A READY result requires:

- blind hypothesis selection;
- vulnerable execution FAIL;
- patched causal control PASS;
- causal verification VERIFIED;
- independent vulnerable reproduction FAIL;
- independent patched reproduction PASS;
- finding gate READY.

## Historical context

The benchmark abstraction is based on public analyses of Sturdy Finance's 2023
exploit, including the documented dependency chain from Sturdy's oracle to
Balancer pool state and the resulting collateral-accounting consequence.

This historical context is documentation for benchmark provenance. It is not passed
to CYDRA as blind selection guidance.
