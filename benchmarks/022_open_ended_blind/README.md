# Benchmark 022 — open-ended blind Solidity discovery

This is the first CYDRA campaign whose selection boundary is deliberately class-hidden.

CYDRA receives only a pinned unfamiliar Solidity target. The benchmark does not pass a
vulnerability class, target function, state surface, exploit sequence, or historical
answer into the investigation call. CYDRA builds its normal system model, generates
available hypotheses, and uses a class-neutral next-hypothesis selector to choose the
highest-information candidate under the experiment budget.

Target: pinned historical Intuition repository revision 0a19e25, source surface
src/protocol/wallet/AtomWallet.sol. The benchmark harness knows the historical oracle
only for post-run evaluation and causal-control construction; that oracle is never
passed to investigate().

Success requires:
1. the blind selector chooses the signed-metadata hypothesis from the generated set;
2. the actual pinned repository and dependencies compile and execute;
3. vulnerable execution demonstrates that changing only unsigned authorization metadata changes the accepted validity window;
4. a minimal causal control binds that metadata into the digest and passes;
5. fresh vulnerable and patched clones reproduce the split;
6. the canonical causal chain verifies and the finding gate reaches READY.

The benchmark is bounded: it demonstrates one open-ended selection and one general
signed-metadata integrity capability. It does not claim arbitrary Solidity coverage.
