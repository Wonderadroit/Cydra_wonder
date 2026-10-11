# CYDRA Roadmap

This roadmap reflects the current product decision: finish one valuable, measurable capability before expanding scope.

## Active milestone — Web3 authorization specialist

**Scope:** missing or incorrect authorization on externally callable, state-changing Solidity/EVM operations.

### Gate A — Controlled correctness

- [x] Vulnerable local positive control is selected and reproduced.
- [x] Protected negative control is rejected.
- [x] Historical external positive control is reproduced and explicitly labeled non-novel.
- [x] Focused authorization regression workflow passes.

### Gate B — Evidence-preserving operation

- [x] Compiler-backed state-effect evidence is preserved.
- [x] No-hypothesis runs produce explicit structured dispositions.
- [x] Target source is pinned to immutable commits.
- [x] Local-only unfamiliar-target campaign is repeatable.

### Gate C — Transfer to unfamiliar targets

- [ ] The model identifies state-changing surfaces and candidate authorization boundaries with source provenance.
- [ ] CYDRA generates at least one falsifiable authorization hypothesis on an unfamiliar authorized target, or demonstrates adequate coverage for a defensible no-candidate result.
- [ ] A safe local experiment is executed; blocked prerequisites remain explicit.
- [ ] A candidate, if any, survives causal patch/replay and independent reproduction.
- [ ] A human verifies deployed asset, current scope, known-issue status, novelty, impact, and reporting rules.

**Current result:** two unfamiliar source revisions compiled and produced state-effect evidence, but both ended `BLOCKED / NO_SUPPORTED_HYPOTHESIS / NOT_READY`. Gate C remains open. No novel bounty finding is claimed.

## Definition of done

The specialist is complete only when its transfer gate is met without target-specific detector patches, unrelated vulnerability classes, or historical-answer leakage. All experiments must be executed or have an evidence-backed blocker. A green CI run alone does not close the gate.

## After this milestone

Only after Gate C closes should we decide—based on measured performance—whether to expand the authorization pattern coverage, improve the experiment planner, or begin a second vulnerability class.

## Permanent engineering rules

- Fix the first demonstrated blocker and replay the same frozen target.
- Every meaningful fix gets a regression and relevant campaign replay.
- Keep historical benchmarks as evaluation assets, not as production target-selection logic.
- Heavy batch/backtest campaigns remain manually dispatched unless a narrow change explicitly requires them.
- Preserve contradictory evidence, uncertainty, provenance, and human review.
