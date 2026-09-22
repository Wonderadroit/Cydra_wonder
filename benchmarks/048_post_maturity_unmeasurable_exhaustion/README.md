# Benchmark 048 — unmeasurable hypothesis exhaustion

This post-maturity control verifies that an experiment which cannot produce executable evidence is not replayed indefinitely within the same research run.

Acceptance:
- when another executable hypothesis exists, an UNMEASURABLE candidate is skipped in favor of new information;
- when it is the only remaining candidate, selection reports hypothesis exhaustion rather than replaying the same non-renderable experiment;
- a new research run may retry after the execution environment materially changes.

This is generic execution-resilience hardening. It does not encode a vulnerability class or benchmark answer.
