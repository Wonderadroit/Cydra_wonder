# Benchmark 020 — unfamiliar epoch-boundary accounting

This benchmark tests a class-neutral reasoning capability for piecewise state/accounting transitions.

CYDRA receives only the pinned historical target source. The historical finding, vulnerable expression, expected reward delta, and patched expression are not supplied to the blind reasoning surface.

Target:
- repository: https://github.com/code-423n4/2024-01-canto.git
- revision: 5e0d6f1f981993f83d0db862bcf1b2a49bb6ff50
- source: src/LendingLedger.sol
- blind entry point: update_market

The investigation surface derives an invariant from the target's own epoch partitioning and accounting topology. The executable experiment starts from an intentionally unaligned stored checkpoint, crosses an epoch boundary, and compares observed accumulated accounting with the piecewise configured schedule.

Success requires:
- one blind epoch-boundary hypothesis;
- real target repository and dependencies executed with Foundry;
- vulnerable execution FAIL;
- isolated patched control PASS;
- canonical causal verification VERIFIED;
- independent vulnerable reproduction FAIL;
- independent patched reproduction PASS;
- reproduction verification VERIFIED;
- finding gate READY.

The result is a finding about the pinned historical revision only. It is not a claim about the current Canto codebase.
