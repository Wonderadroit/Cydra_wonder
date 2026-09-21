# Benchmark 034 — generic research-loop holdout

This campaign adds no vulnerability detector or target-specific reasoning surface.

Blind context supplies only the pinned Blackhole target source. It does not supply the vulnerability class, target function, state surface, exploit sequence, or historical answer.

The campaign exercises the merged generic select -> execute -> observe -> reselect loop. A candidate that cannot be safely rendered by the existing benchmark harness is recorded as UNMEASURABLE and fed back to the generic selector.

Success requires the loop to reach the existing guard hypothesis and then preserve the existing causal differential, independent reproduction, and finding gate.

This is a regression/generalization test of the reasoning loop, not a claim of a newly discovered production vulnerability.