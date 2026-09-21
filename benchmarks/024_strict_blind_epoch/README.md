# Benchmark 024 — strict blind epoch-boundary discovery

This benchmark strengthens the existing epoch-boundary accounting backtest by removing its injected reasoning surface and planner.

CYDRA receives only the pinned historical target source. The blind investigation supplies:
- no vulnerability class;
- no target function;
- no state surface;
- no reasoning-surface injection.

The pipeline must independently produce and the class-neutral selector must independently choose the epoch-accounting hypothesis. Only after blind selection does the harness evaluate the known historical target behavior.

Success requires:
- strict blind selection of the epoch-accounting hypothesis;
- real pinned Canto source and dependency graph executed with Foundry;
- vulnerable execution FAIL;
- patched control PASS;
- canonical causal verification VERIFIED;
- independent vulnerable reproduction FAIL;
- independent patched reproduction PASS;
- finding gate READY.

This benchmark exists to test whether an already-developed reasoning capability can be exposed through the normal blind pipeline rather than being manually injected by the benchmark harness.
