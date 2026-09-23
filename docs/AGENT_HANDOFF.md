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


## Recursive execution-readiness checkpoint
- Final documented branch head: `aa1f9616745820f3a13963202f8b89828ea0ac4a`
- Final Arcadia run: `35886648916`
- Final artifact ID: `10763072880`
- Final artifact digest: `sha256:4676fc8b356027c254a344421905e980a75c644bab62b8aa848f8f4a505e725a`
- Target: Arcadia lending-v2 commit `def3c94995773e2feb48b6d8a02dc603d96fd96c4`.
- 71 hypotheses planned; 27 reached execution (10 PASS, 17 FAIL); 44 state hypotheses were correctly blocked at generation by unresolved prerequisites. Final artifact was regenerated from the documented head and independently inspected.
- Causal evidence: 0. Confirmed findings: 0. No unsupported finding was produced.
- Artifact manifest: all 14 entries independently verified.
- Generic improvement: state setup is now recursively verified and ambiguous state prerequisites fail closed before Foundry materialization.
- Remaining blocker: resolve the caller-state chain `startLiquidation -> maxWithdraw(msg.sender) -> balanceOf(msg.sender) > 0` through generic compiler-backed producer/call-data-flow reasoning, including producer dependencies.
- Final Arcadia research job and Python baseline are green. Three broader post-maturity checks remain known external-target/campaign blockers (unsupported Rabbithole adapter; Debtdao clone/setup timeout; related target campaign baseline), not regressions from this change.
- Next capability: compiler-backed intra-contract call-edge propagation into transitive state-effect reasoning, followed by a target-only rerun and artifact comparison.


## Diagnosis-first doctrine checkpoint

The project doctrine now explicitly requires CYDRA to diagnose unfamiliar targets, errors, blockers, and unexpected behavior before patching symptoms. The target's intent, state, invariants, preconditions, dependencies, and enforcement mechanisms are treated as evidence-bearing structure. Generic fixes must repair the missing abstraction at the narrowest justified layer, with focused regression coverage. This formalizes the pattern already demonstrated by the adapter and execution-readiness work.

The canonical loop is:

**Observe → Diagnose → Understand Intent → Model → Identify Preconditions → Use Target Mechanisms → Experiment → Evidence → Update Model → Generalize**

The goal is not maximum execution count. The goal is increasingly accurate target understanding and meaningful, reachable, reproducible, causally informative experiments.


## Execution-readiness producer-solver checkpoint

The execution-readiness layer now resolves positive caller-state prerequisites from compiler-backed state writers instead of leaving them as opaque blockers. For a consumer whose execution value requires a positive maxWithdraw(msg.sender), CYDRA discovers compiler-backed transitions that write balanceOf, records those transitions with provenance, and feeds the discovered state dependency into the existing recursive state-setup planner. The planner remains fail-closed: a discovered writer is not treated as reachable merely because it writes the right state; its own caller, state, execution, and runtime prerequisites must still be solved.

The next frontier is therefore runtime/value-dependency construction for otherwise valid producer transitions. This must remain target-generic and diagnosis-first: determine which dependency the producer actually requires, identify whether the target itself provides a construction path, and only then generalize the smallest reusable resolver. Controlled-state/cheat-code experiments, if introduced, must remain explicitly diagnostic and must not be confused with ordinary protocol reachability evidence.
