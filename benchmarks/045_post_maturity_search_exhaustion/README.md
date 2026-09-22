# Benchmark 045 — Search Exhaustion

This post-maturity orchestration benchmark verifies that the evidence-driven research loop has an explicit, auditable terminal state when all executable hypotheses have been contradicted.

The benchmark supplies two bound candidates. Both execute and return `contradicted`. The configured investigation budget is five rounds, so a broken loop could repeat a rejected candidate or crash after the candidate queue is exhausted.

Acceptance requires:

- each candidate is selected at most once after contradiction;
- the loop terminates before consuming the remaining budget;
- `termination_reason` is `hypothesis_exhausted`;
- no exception is raised for normal candidate exhaustion;
- empty investigations still fail closed.

This is a control-plane hardening benchmark. It does not claim a vulnerability.
