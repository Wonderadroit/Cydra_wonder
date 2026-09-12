# Benchmark 004 — Real-target prediction

## Target

A minimal protocol-level reconstruction of the historical Yield Protocol Strategy accounting vulnerability documented publicly by Immunefi: an unsolicited pool-token donation can inflate the live token balance while leaving the protocol's cached accounting unchanged; redemption must therefore use the cached book value rather than the live balance.

The reconstruction is intentionally not copied production source. It models the protocol interaction required for the historical finding:

1. a pool token with transferable balances;
2. a strategy with cached pool-token accounting and share supply;
3. mint/burn accounting;
4. an attacker donation directly to the strategy;
5. vulnerable redemption using live balance versus patched redemption using cached accounting.

## Pre-run hypothesis

CYDRA will process this target through the same evidence-first pipeline and derive a reproducible accounting invariant from the reconstructed protocol behavior, generate a causal experiment, execute that experiment against vulnerable and patched controls, and classify the historical vulnerability as **confirmed**.

The important prediction is not merely that a known PoC will pass. The prediction is that the engine can cross the system-model → invariant → hypothesis → experiment → execution → causal-classification chain for a real historical protocol failure without importing the historical finding as the answer.

## Expected invariant

The protocol's share-redemption amount must be based on the cached book value that represents accounted-for pool tokens, not on an attacker-inflatable live ERC20 balance.

Equivalent causal violation:

`direct donation changes live balance` AND `cached accounting remains unchanged` AND `redemption payout increases because live balance is used`.

## Expected experiment

Create an initial strategy position, perform an unsolicited pool-token donation directly to the strategy, then redeem shares. Compare the vulnerable implementation with the patched implementation.

Expected differential:

- vulnerable: donation increases the redeemable payout beyond the cached pro-rata amount;
- patched: donation does not increase the payout attributable to the redeemed shares.

## Required evidence

The experiment must preserve execution-produced measurements sufficient to establish the causal differential, at minimum:

- cached accounting before redemption;
- live balance after donation;
- vulnerable payout;
- patched payout;
- a reference pro-rata payout or equivalent differential measurement.

The finding must not be classified from test status alone.

## Falsification boundaries

1. **Extraction failure:** CYDRA cannot identify the accounting inconsistency from the reconstructed protocol without a benchmark-specific oracle → prediction falsified at extraction.
2. **Hypothesis/schema failure:** the existing Hypothesis schema cannot represent the accounting hypothesis → falsified at schema.
3. **Planner failure:** no information-gain experiment can be represented using the existing Experiment schema → falsified at planning.
4. **Generator failure:** the generated experiment cannot exercise donation → redemption causality on both controls → falsified at generation/execution.
5. **Evidence failure:** execution cannot preserve the measurements needed to distinguish live-balance inflation from cached accounting → falsified at evidence.
6. **Classifier failure:** classification depends only on PASS/FAIL status, or confirms without the numerical/protocol differential → falsified at causal classification.
7. **Negative control failure:** a safe/patched control that preserves the accounting invariant is classified as confirmed → falsified.
8. **UNMEASURABLE:** compilation, dependency, or harness failure prevents reaching the stated boundary; record UNMEASURABLE rather than inventing a result.

## Anti-cheating constraints

- Do not paste the historical vulnerability answer into the classifier.
- Do not classify from the benchmark name, known finding, or expected result.
- Do not compute the exploit outcome independently in Python and call that execution evidence.
- The vulnerable/patched differential must originate from executed Solidity.
- The reconstructed fixture must be minimal but protocol-level: donation is an external token action and redemption is a state transition, not a single arithmetic function.
- If a class-specific rule is required, it must encode the observable system invariant, not the historical report's final classification.

## Scope of claim

A confirmation establishes that CYDRA can carry one real historical protocol-level accounting failure through the complete reasoning and causal-verification path. It does not establish general accounting vulnerability coverage, arbitrary DeFi exploit discovery, or general smart-contract security completeness.
