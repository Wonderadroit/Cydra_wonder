# CYDRA Agent Instructions

This repository is the durable state of the CYDRA research project. Do not rely on chat history as authoritative state.

## Authority

Read these in order before changing implementation:

1. PROJECT_BIBLE.md — mission, doctrine, architecture, milestones, non-negotiables.
2. docs/CYDRA_OPERATING_PROTOCOL.md — continuation, CI, blind-boundary, and human-review rules.
3. docs/AGENT_HANDOFF.md — current checkpoint and in-flight work.
4. ARCHITECTURE.md and DEVELOPMENT_PROTOCOL.md when changing architecture or validation strategy.
5. Open PRs, recent commits, and current GitHub Actions before starting duplicate work.

## Required development loop

inspect → diagnose → smallest generic repair → focused regression → affected benchmark → relevant CI → wait → merge → record durable state

Do not:
- add target-specific vulnerability detectors to solve a target execution failure;
- treat a revert, static warning, or generated hypothesis as a finding;
- leak historical benchmark answers into blind selection;
- merge while required validation is still running;
- create a new benchmark merely to manufacture progress;
- expand to another language ecosystem before the Solidity/EVM maturity boundary is genuinely satisfied.

## Current research boundary

CYDRA is an evidence-first reasoning/orchestration engine for authorized security research. The current production adapter is Solidity/EVM + Foundry.

The post-maturity gate is closed. Current work is execution-readiness on unfamiliar real code, followed by supervised authorized dogfood. Public-code research that is not explicitly authorized for a bounty program must remain local/public-source analysis only; do not contact or mutate live deployments.

## CI rule

GitHub Actions is the canonical reproducible execution environment. A large number of unrelated historical benchmark workflows may be triggered by repository changes; distinguish CI fan-out from the intended research workflow. Fix workflow isolation generically rather than interpreting unrelated failures as security evidence.

## Handoff rule

At every accepted milestone, update docs/AGENT_HANDOFF.md with:
- main commit;
- accepted capability;
- open PRs and purpose;
- active CI/campaign;
- last observed evidence;
- blockers;
- exact next boundary.

Another agent must be able to resume without asking the previous chat what happened.
