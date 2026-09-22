# Benchmark 047 — post-maturity duplicate-finding resilience

This benchmark verifies that repeated emission of the exact same evidence-backed finding is idempotent, while a conflicting finding reusing an existing finding identity remains fail-closed.

The control is generic: it does not name a vulnerability class, target, selector, historical answer, or severity ranking.

Acceptance:
- exact duplicate finding ID + identical finding object: retained once;
- same finding ID + different content: rejected explicitly;
- no duplicate report is created;
- the existing multi-finding behavior remains intact.

This is orchestration/data-integrity hardening, not a vulnerability claim.
