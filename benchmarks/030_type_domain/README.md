# Benchmark 030 — strict blind type-domain reachability

Target: Code4rena AI Arena, pinned historical FighterFarm.sol.

The blind boundary supplies only the pinned target source to the normal CYDRA pipeline. It does not supply the historical finding, function name, vulnerability label, or expected answer.

The generic reasoning surface asks whether an externally supplied narrow integer parameter is used as an identifier into a wider state domain. Execution must then distinguish an ABI reachability boundary from an ordinary missing-token revert.

Acceptance:
- blind selector independently chooses the type-domain hypothesis;
- vulnerable target rejects a boundary identifier at ABI decoding;
- patched control widens only tokenId and reaches the target function, producing the ordinary nonexistent-token failure instead;
- canonical causal verification is VERIFIED;
- independent vulnerable and patched reproductions preserve the same differential;
- finding gate is READY.

Historical Code4rena material is used only after blind selection for causal evaluation. It is not supplied to hypothesis generation.
