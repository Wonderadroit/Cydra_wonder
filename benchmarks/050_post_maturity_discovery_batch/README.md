# Benchmark 050 — post-maturity discovery batch campaign

This campaign composes the already-demonstrated unfamiliar-target and causal-validation campaigns into one ordered run:

1. Benchmark 040 — six-target post-maturity unfamiliar-target batch.
2. Benchmark 043 — two-target blind-to-causal discovery with independent reproduction.
3. Benchmark 044 — the corresponding patched negative controls.

No benchmark answer is injected into the blind stages. Existing benchmark semantics remain unchanged.

The campaign fails closed on the first blocked constituent campaign and preserves bounded stdout/stderr for diagnosis.

This is a validation campaign, not a new vulnerability detector.
