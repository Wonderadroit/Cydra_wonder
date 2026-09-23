# CYDRA_wonder Agent Handoff

## Last known repository state
- Repository: `Wonderadroit/Cydra_wonder`
- Active branch: `research/arcadia-lending`
- Branch head at handoff: `453da4520d15b7e8db68082a2db7bc9958709e91`
- Latest commit message: `fix: model collection length guards without local state inventory`
- Maturity gate: CLOSED. Do not reopen it.
- Open PR count at the cleanup boundary was zero; work is intentionally continuing on the target-only research branch.

## What has already been completed
- Target adapter/intake for Foundry Solidity is generic and regression-tested.
- Execution-readiness modeling exists for constructor dependencies, roles/callers, runtime dependencies, state predicates, compiler constraints, and constructible state setup candidates.
- Solidity state predicate polarity exists (`must_hold`, `must_not_hold`, `unknown`).
- Compiler-resolved state effects/call edges were made contract-qualified and fail closed on unresolved/ambiguous calls.
- Foundry execution is bounded by explicit experiment and setup timeouts.
- Arcadia blind public-code research has completed successfully at least once, with uploaded artifact evidence; the final artifact must be inspected before interpreting results.
- A completed research run uploaded artifact ID `10738051082` with digest `sha256:f5df0e3181d5e1aabdbdcc80f2eccfe2e4fd09a6de5086e53dad986a84e9d44e`.
- The research workflow run associated with that artifact was `35832346299`; its research job completed successfully, including the frozen research step and artifact upload.
- A later generic execution-readiness change triggered another research run. At the last observed point, run `35832626013` had its research job still in progress while the two backtest jobs had completed successfully. Continue inspecting the current branch head and current Actions state rather than assuming that status is still current.

## Important earlier findings
- Initial Arcadia blind run produced no confirmed vulnerability. It produced candidate hypotheses but many reverted because the generated environment lacked required constructor/runtime/state prerequisites.
- All such reverts were treated as execution failures, not vulnerabilities.
- Arcadia constructor dependencies include ERC20 asset metadata and role/dependency addresses; generic harness generation was strengthened for typed constructor dependencies and deterministic role identities.
- Generic collection-state handling was recently strengthened so expressions such as `items.length > 0` and guarded collection predicates are modeled as state rather than local execution predicates.
- The next generic step is to make readiness setup actually reach the required state safely and deterministically, including transitive producer/data-flow prerequisites, without hard-coding Arcadia behavior.

## Immediate resume procedure
1. Read `PROJECT_BIBLE.md`, this file, and `AGENTS.md`.
2. Fetch `research/arcadia-lending` head and compare it with this recorded SHA.
3. Inspect all current check-runs for the head; identify the research workflow run and all backtest/regression runs.
4. If any required job is running, inspect its steps/logs periodically until it completes. Do not declare completion from an intermediate status.
5. Fetch the latest research workflow artifacts. Inspect the final artifact, not just the upload message.
6. Extract and inspect at minimum:
   - classification
   - hypotheses
   - experiments
   - execution
   - invariants
   - provenance
   - integrity/manifest
   - target checkout/intake
   - compilation evidence
7. Determine exactly which hypotheses were reached, which failed only because of setup, which are genuinely unmeasurable, and whether any finding has causal evidence. Do not import external audit findings before the blind result is frozen and recorded.
8. If execution readiness remains the blocker, diagnose the generic missing prerequisite. Prioritize:
   - transitive call/data-flow producer discovery;
   - role-aware setup;
   - state writer reachability;
   - constructor dependency materialization;
   - safe setup verification before the security call.
9. Implement only generic fixes, add focused regressions, run full pytest/static checks, and let GitHub Actions validate.
10. Rerun the target-only research after the generic fix.
11. Compare the new artifact with the prior artifact. The goal is not “more experiments”; the goal is more **meaningful, reachable, evidence-producing** experiments without false positives.
12. Only after the research artifact is genuinely complete should you update the Bible/handoff with the result and decide the next research target.

## Do not do
- Do not create Benchmark 051 merely to keep the benchmark sequence moving.
- Do not reopen the maturity gate.
- Do not patch Arcadia specifically.
- Do not claim a vulnerability from a revert, unauthorized error, or empty write set.
- Do not use historical audit reports or known contest findings to guide the blind first pass.
- Do not run live exploit transactions or manipulate live user funds/state.
- Do not stop after a single green job when other jobs/artifacts remain.

## End condition
The current milestone is complete only when:
- the latest generic changes pass regression;
- the final target-only research workflow is green;
- the final uploaded artifact is inspected and integrity/provenance are valid;
- reachable experiments produce actual evidence where prerequisites allow;
- no unsupported vulnerability is classified;
- remaining blockers are explicitly understood and recorded;
- the Bible and handoff describe the actual state.
