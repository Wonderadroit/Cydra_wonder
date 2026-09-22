# Benchmark 041 — Post-Maturity Blind-to-Causal Discovery

This campaign extends the post-maturity question from capability coverage to a complete blind-to-causal evaluation.

The blind phase receives only the pinned historical source surface and the normal CYDRA class-neutral reasoning machinery. It receives no vulnerability class, target function, state surface, exploit sequence, patch, or historical answer.

Only after blind hypothesis selection does the evaluator reveal the historical causal control. The evaluator then checks whether the blind hypothesis binds the vulnerable computation and executes an independently authored differential PoC against vulnerable and patched controls.

The campaign is successful only if:
- blind selection reaches the security-relevant computation without a target-specific selector;
- the vulnerable execution demonstrates the invariant violation;
- the causal control passes;
- independent vulnerable and patched reproductions agree;
- the final result remains evidence-backed.

A green CI result without those observations is not considered success.

The blind and causal stages are intentionally separated so ground truth cannot influence hypothesis selection.
