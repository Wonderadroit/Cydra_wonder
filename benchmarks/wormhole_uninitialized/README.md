# Benchmark 002 — Wormhole Uninitialized Lifecycle

Historical basis: Immunefi's Wormhole Uninitialized Proxy Bugfix Review (20 May 2022). The report describes an implementation left uninitialized after a prior bugfix; an attacker could call `initialize()` directly on the implementation and set a guardian set they controlled, enabling the later upgrade/destruction path.

CYDRA reconstructs only the lifecycle boundary needed for this milestone. It does not claim to reproduce the full Wormhole exploit chain.

## Acceptance

CYDRA must model `initialize`, derive `INV-INIT-001`, generate `H-INIT-initialize`, generate a Foundry lifecycle test, and confirm only when the vulnerable fixture fails the security assertion while the patched negative control passes.

Expected differential:

- vulnerable fixture: security test **FAILS** because the arbitrary caller becomes guardian
- patched fixture: security test **PASSES** because initialization is already claimed and the call safely reverts
- classifier: **CONFIRMED** only for vulnerable FAIL + patched PASS

## Architecture-generalization falsification criterion

The architecture-generalization claim is falsified if a new vulnerability class requires changes to the shared Hypothesis, Evidence, Experiment, causal-classification, or pipeline execution model merely to represent, execute, or causally verify that class. A class-specific invariant/extraction rule is allowed.

The claim is also falsified if an invariant extraction rule must make class-specific decisions that are hidden from the Hypothesis / Experiment / Evidence layer or must reach into pipeline internals to perform its work. The information flow must remain uniform: an extraction rule produces the documented shared schema, and the existing downstream reasoning path consumes it without secretly branching on vulnerability class.

## Negative-control protocol

Before introducing another invariant class, run a safe initialization target. The safe target may still expose an initializer structurally, but its deployed lifecycle state must prevent an arbitrary caller from claiming privileged state.

Protocol:

1. Run the negative control and record the result.
2. If CYDRA declines to confirm / the security test passes, the negative-control criterion passes.
3. If CYDRA confirms or the safe target violates the security assertion, **stop and record the failure without fixing CYDRA in the same session**.
4. Only after recording the failure decide whether the cause is a class-specific extraction issue (allowed) or a structural/information-flow failure (falsifies the architecture claim).

This negative control is deliberately separate from the vulnerable-vs-patched historical differential: it tests whether CYDRA declines to confirm when the lifecycle is actually safe.

Verification branch: this commit exists only to force the same negative-control workflow through the pull-request CI trigger so its execution can be inspected.
