# Benchmark 002 — Wormhole Uninitialized Implementation

Historical basis: Immunefi's Wormhole Uninitialized Proxy Bugfix Review (20 May 2022). The report describes an implementation left uninitialized after a prior bugfix; an attacker could call `initialize()` directly on the implementation and set a guardian set they controlled, enabling the later upgrade/destruction path.

CYDRA reconstructs only the lifecycle boundary needed for this milestone. It does not claim to reproduce the full Wormhole exploit chain.

Acceptance: model `initialize`, derive `INV-INIT-001`, generate `H-INIT-initialize`, generate a Foundry lifecycle test, and confirm only when the vulnerable fixture fails the security assertion while the patched negative control passes.
