# Benchmark 025 — strict blind signature-reuse discovery

This benchmark reruns the unfamiliar Phi signature-reuse target through CYDRA's normal pipeline without manually injecting the signature-reuse reasoning surface or planner.

Blind context contains:
- no vulnerability class;
- no target function;
- no state surface;
- no reasoning-surface injection;
- no custom experiment planner.

The class-neutral selector must choose the signature-reuse hypothesis before the benchmark evaluates the historical differential.

Success requires real execution, vulnerable FAIL, patched PASS, canonical causal verification VERIFIED, independent vulnerable FAIL, independent patched PASS, and finding gate READY.
