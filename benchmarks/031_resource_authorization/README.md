# Benchmark 031 — strict blind resource authorization

Target: Code4rena Revert Lend, pinned historical V3Utils.sol.

Blind boundary: CYDRA receives only the pinned target source. The historical H-04 answer, vulnerable function, exploit sequence, and mitigation are withheld from hypothesis generation and selection.

Generic capability under test: resource-bound authorization. CYDRA asks whether an externally callable operation over an identified resource binds the caller to the resource owner or explicit delegate before mutating or withdrawing that resource.

Acceptance:
- the normal class-neutral pipeline generates the resource-authorization hypothesis;
- the generic research loop reaches it after recording non-measurable alternatives rather than being given the target function;
- vulnerable execution FAILs the security expectation;
- patched causal control PASSes;
- causal verification is VERIFIED;
- independent vulnerable and patched reproductions preserve the differential;
- finding gate is READY.

Historical report material is used only for post-selection causal control and reproduction.
