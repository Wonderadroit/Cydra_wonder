# Benchmark 021 — unfamiliar control-flow/progress failure

This benchmark tests a materially different Solidity reasoning capability: recognizing a
termination invariant in a gas-optimized loop and validating a reachable continue branch
that bypasses the loop's progress update.

Target:
- repository: code-423n4/2023-09-venus
- pinned revision: 23f5db740d8a794ac563ac32195b675c53042bb4
- source: contracts/Tokens/Prime/Prime.sol
- blind entry point: updateScores

The blind run receives only the pinned target source. The historical report is not used
to choose the function or expected outcome. The reasoning surface derives the invariant
from the loop topology, then the planner asks for a two-element execution in which the
first element satisfies the continue condition and the second still needs processing.

Causal validation:
1. vulnerable target execution must fail because the loop cannot advance;
2. a minimal patched control increments the loop counter before continue and must pass;
3. fresh independent vulnerable and patched clones must reproduce the same split;
4. the canonical causal chain and finding gate must reach READY.

The benchmark uses real target code and dependencies. Test doubles are limited to
environmental dependencies required to initialize the target; the vulnerable control
itself is the pinned target implementation.
