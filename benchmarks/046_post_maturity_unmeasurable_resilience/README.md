# Benchmark 046 — Unmeasurable Execution Resilience

This post-maturity control verifies that an execution outcome of `UNMEASURABLE` is treated as an evidence boundary rather than as a confirmed finding or a permanent search dead-end.

The campaign presents two otherwise executable candidates. The first produces `UNMEASURABLE`; the second is then selected and produces `confirmed`.

Acceptance requires:

- the unmeasurable candidate is recorded;
- the loop moves to a different candidate when one is available;
- the unmeasurable outcome is never promoted to a finding;
- a subsequent confirmed observation may terminate normally;
- the termination reason records the actual stop condition.

This validates orchestration behavior, not a vulnerability claim.
