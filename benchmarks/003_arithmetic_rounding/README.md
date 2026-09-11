# Benchmark 003 — Arithmetic Rounding

This is a deliberately minimal third-class fixture for CYDRA.

The invariant is numerical rather than control-flow based:

> A mint quote must not exceed the exact floor of `assets * SCALE / 997`.

The vulnerable fixture rounds upward; the patched control rounds downward. Solidity integer division truncates toward zero, so the differential is directly measurable in execution. citeturn3search1

## Experimental rule

The fixture is not allowed to add an arithmetic-specific reasoning rule. The first run must use the existing `investigate()` pipeline unchanged. If extraction does not produce an arithmetic hypothesis, that is the recorded boundary of the current abstraction.

## Intended differential

For `assets = 1`, the exact floor is `1`, while the vulnerable ceiling implementation returns `2`.

The standalone Foundry test in `foundry/test/ArithmeticRounding.t.sol` proves that the fixture itself has the intended vulnerable/patched differential. Benchmark 003 then asks whether CYDRA can discover and represent that experiment through its existing reasoning pipeline.
