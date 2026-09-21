# Benchmark 032 — strict blind callback state-order

Target: Code4rena Phi, pinned historical Cred.sol.

Blind boundary: CYDRA receives only the pinned target source. The reentrancy/callback class, vulnerable ordering, exploit sequence, and mitigation are withheld from hypothesis selection.

Generic capability under test: detect a security-critical state update that occurs after an externally observable value transfer, bind that topology to a public callable wrapper, and plan a reentrant experiment.

Acceptance:
- normal class-neutral pipeline generates the callback-state-order hypothesis;
- generic research loop reaches it after recording non-measurable alternatives;
- vulnerable execution FAILs the security expectation;
- patched causal control PASSes;
- causal verification is VERIFIED;
- independent vulnerable and patched reproductions preserve the differential;
- finding gate is READY.

Historical report material is evaluation/corroboration context only and is not supplied to selection.

Canonical validation is executed from main after the capability is integrated; the blind boundary remains unchanged.
