# CYDRA Agent Contract

## Active assignment

The current objective is to complete the **Web3 authorization specialist** before expanding to other vulnerability classes.

The specialist scope is missing or incorrect authorization on externally callable, state-changing Solidity/EVM operations. Reuse the existing source model, authorization reasoning, Foundry experiment path, causal verification, and evidence gate.

The success condition is not "CI is green" or "another benchmark passes." It is a supported hypothesis on an unfamiliar, explicitly authorized and immutable target, followed by a safe experiment, causal verification, and independent reproduction—or a defensible no-candidate result after adequate coverage.

## Current known state

- Focused positive/negative controls and the historical external positive control pass.
- The historical Decent `setRouter` case is a known public issue, not novelty evidence.
- Two unfamiliar source revisions compiled and yielded semantic state-effect evidence, but both returned `BLOCKED / NO_SUPPORTED_HYPOTHESIS / NOT_READY`.
- No novel, independently reproduced bounty finding has been established.

The next engineering task is to diagnose why the authorization model/hypothesis selector produces no supported hypothesis on these targets. Start from the recorded campaign artifact and logs. Do not add a new vulnerability class, new benchmark matrix, or broad abstraction before identifying the first demonstrated blocker.

## Required procedure

1. Read this contract and `docs/WEB3_AUTHORIZATION_SPECIALIST.md`; consult `PROJECT_BIBLE.md` and `DEVELOPMENT_PROTOCOL.md` for governing principles.
2. Inspect `main`, recent commits, open PRs, and relevant workflow status before starting duplicate work.
3. Freeze an explicitly authorized target to an immutable source revision and record the exact scope and allowed environment.
4. Reproduce the current blocker from its artifact/log.
5. Implement the smallest generic repair that addresses that blocker.
6. Add a focused regression that fails before the repair and passes after it.
7. Run focused authorization controls, the relevant target replay, and the main regression.
8. Wait for all required jobs to finish before reporting results.
9. Merge only when the checks required by the change pass; never merge on unknown or failing results.

## Canonical validation paths

- Main regression: `.github/workflows/cydra-main-regression-smoke.yml`
- Focused controls: `.github/workflows/web3-authorization-specialist.yml`
- Unfamiliar-target gate: `.github/workflows/web3-unfamiliar-authorization-gate.yml`

These campaigns are distinct: the focused controls validate the detector/harness; the unfamiliar-target gate measures transfer. A successful workflow does not imply a finding.

The Hinkal live-contest workflow and Web2 regression assets remain historical/manual capabilities. They are not the active specialization gate and must not silently displace it.

## Hard stops

Do not:
- infer authorization from public source availability;
- send production state-changing transactions as part of the unfamiliar-target gate;
- hard-code target-specific function names, selectors, addresses, or expected answers into detection logic;
- call historical vulnerabilities novel;
- treat compilation/setup failure or an unexecuted experiment as evidence of security;
- expand the vulnerability-class scope to make a result look better;
- add architecture without a demonstrated blocker;
- mark a blocked target as a clean no-candidate result;
- declare success while required jobs are queued or running.

## Handoff required at every checkpoint

Record:
- CYDRA commit SHA;
- target program/scope URL and immutable target SHA;
- workflow/run and artifact links;
- current disposition and exact blocker;
- generic repair and regression added;
- focused tests and target replay results;
- next unresolved blocker.
