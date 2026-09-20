# Benchmark 019 — single-use signed authorization

This benchmark transfers CYDRA's signature reasoning from execution-domain binding to **authorization consumption** on a directly executable unfamiliar Solidity target.

Target:
- repository: https://github.com/code-423n4/2024-08-phi
- pinned ref: `2465e04364b759c721f1a0aebace69920411f8aa`
- source: `src/PhiFactory.sol`
- blind target: `signatureClaim`

Blind reasoning is source-derived and does not receive the historical finding. The new surface observes a signed state-changing entry point that records a per-authorization state marker through a helper, then asks whether the marker is checked before being written again.

The executable experiment runs the actual pinned Phi repository with its real dependency graph and existing claim setup. The test submits one valid signed claim twice. The security invariant requires the second submission to be rejected.

Causal control:
- vulnerable: original pinned source;
- patched: same target source with a minimal pre-state rejection using the target's existing `AddressAlreadyMinted` error.

Finding gate:
- vulnerable execution must FAIL the security invariant;
- patched execution must PASS;
- causal verification must be VERIFIED;
- independent vulnerable reproduction must FAIL;
- independent patched reproduction must PASS.

The benchmark is not complete until the machine-readable result records `finding_gate: READY`.
