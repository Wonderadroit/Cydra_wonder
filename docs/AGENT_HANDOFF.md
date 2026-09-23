# CYDRA Agent Handoff — Supervised Arcadia Dogfood

## Current branch
`research/arcadia-lending`

## Current target
`arcadia-finance/lending-v2`, frozen target commit:
`def3c94995773e2feb48b6d8a02dc603d96fd96c4`

## Latest completed research
GitHub Actions run: `35834281565`
Result: success
Artifact: `cydra-arcadia-lending-public-code`
Artifact ID: `10739020912`
Artifact SHA-256: `db3cf3f2cee0259d3ab46018987c8b2410d34a45129605c543abfeb23caac940`

The artifact contains the complete frozen evidence set, including target intake, compiler evidence, hypotheses, experiments, execution results, classification, integrity data, and execution-readiness data.

## Research result
- No confirmed vulnerability.
- `H-AUTH-startLiquidation` was extracted and executed.
- The generated unauthorized call reverted; unauthorized mutation was not demonstrated.
- Classification remained `NOT_REACHED` because blind public-code research has no patched counterpart.
- Other requested classes produced no executable candidates under current blind rules.
- Readiness correctly identified `tranches.length > 0` and `addTranche` as the relevant setup path.
- `addTranche` is now marked `unresolved`, not constructible, because its modeled runtime dependencies are unresolved.

## Important architectural conclusion
The first real-target campaign validates that target intake, compiler extraction, hypothesis planning, bounded execution, and readiness evidence work together. The remaining blocker is generic dependency-aware fixture construction.

Do not solve this by adding Arcadia-specific exceptions.

## Next milestone
Build a generic dependency-aware prerequisite fixture layer:

1. resolve the runtime dependency/interface requirements of an unresolved setup transition;
2. identify the minimum externally observable methods required by that transition;
3. generate deterministic minimal stubs only when their semantics are explicit;
4. bind the stub into the prerequisite transition;
5. execute the transition;
6. verify the required state/value changed;
7. only then execute the security hypothesis;
8. preserve unresolved status if any dependency cannot be safely modeled.

Do not classify a reverted prerequisite setup call as a vulnerability.

## Required workflow
Read `PROJECT_BIBLE.md` first.
Use GitHub Actions as the canonical execution environment.
Run full regression before/after changes.
Run the supervised Arcadia research workflow after generic fixture changes.
Inspect the final artifact, not merely workflow success.
Keep the blind boundary intact: historical findings and external audit answers must not be injected before the independent run is frozen.

Doctrine: **LLMs propose. Tools test. Evidence decides.**


## Latest generic readiness repair
The readiness layer now resolves declared Solidity call receivers through the target import graph and excludes calls resolved to `library` declarations from runtime-dependency blockers. This prevents deterministic internal/library operations such as SafeCast-style and error-library calls from being mistaken for externally constructible runtime dependencies. Actual interface/state receivers remain runtime requirements. The change is covered by a regression test and full PR validation; the three unrelated post-maturity batch failures remain target/campaign-specific and are not caused by this repair.

The next Arcadia rerun must verify whether `addTranche` moves from unresolved to constructible. If it does, the generated setup must execute and verify `tranches.length > 0` before retrying `H-AUTH-startLiquidation`. If setup still fails, preserve the blocker and continue generic dependency analysis; do not add an Arcadia-specific mock.


## Current supervised-dogfood continuation — execution-readiness refinement

- Frozen Arcadia target remains `arcadia-finance/lending-v2` at `def3c94995773e2feb48b6d8a02dc603d96fd96c4`.
- The completed public-code artifact demonstrated 1 authorization hypothesis executed and reverted, 23 state hypotheses executed in the earlier rerun, and no confirmed vulnerability. The key remaining capability boundary is dependency-rich prerequisite construction.
- New generic work on `research/arcadia-lending` now models single-statement revert-guard polarity, ERC-4626 `maxWithdraw(msg.sender)` positive-balance prerequisites, and distinct deterministic role identities for fixture addresses (including tranche addresses). These are target-agnostic.
- PR #207 is a draft validation PR only; it must not be merged until its complete CI fan-out is inspected. Main remains the maturity baseline.
- The latest validation fan-out is intentionally being monitored. Any failing job must be diagnosed from its actual log and repaired generically before the validation milestone is considered green.
- Do not add Arcadia-specific exploit logic, mocks, or hard-coded answers. The next legitimate boundary is generic dependency-aware fixture construction and verification.

## Latest continuation — compiler state import closure

- Current branch: research/arcadia-lending.
- Latest CYDRA commit before this handoff update: 471623053b3dda426c984a124a4c42ff2fa58b26; subsequent docs-only commit: 427bac4e6e36eb309e5f3932b19b9875196719c7.
- Latest Arcadia research run: 35854583623; artifact 10747426250; SHA-256 914478d4965476455f24dd817232c61c438b5accd8f0d51651e2ac1d37415667.
- Research completed successfully: 1 authorization + 23 state hypotheses executed; no confirmed vulnerability. Execution artifact contained 24 experiments: 5 PASS / 19 FAIL.
- H-AUTH-startLiquidation still reverts because the positive caller-state prerequisite behind maxWithdraw(msg.sender) is not constructed. addTranche is identified as constructible for the separate tranches.length > 0 prerequisite.
- Generic repair: compiler_state.py now consumes compiler-backed state effects from all build-info source ASTs through extract_state_effects_from_all_sources; target-scoped extraction remains available. Regression added for imported-source state effects.
- PR #207 validation fan-out finished with 71 checks: 68 success, 3 baseline failures (benchmark, negative-controls, post-maturity batch). Their logs were inspected; they are unrelated to this repair. PR remains draft and unmerged.
- Next implementation boundary: generic dependency-aware caller-state construction and verification for resolved value producers. Do not add Arcadia-specific mocks, storage-slot writes, exploit sequences, or historical-answer logic to the blind path.

## Resume protocol
1. Inspect PR #207 and current branch head.
2. Inspect latest Arcadia research artifact before changing the planner.
3. Keep the blind target frozen at arcadia-finance/lending-v2@def3c94995773e2feb48b6d8a02dc603d96fd96c4.
4. Use compiler evidence to resolve the minimum state-producing transition for balanceOf(msg.sender) > 0 without assuming target-specific storage layout.
5. Construct only deterministic interface-complete stubs whose required semantics are explicit.
6. Verify prerequisite state/value before the security experiment.
7. Re-run full regression and supervised Arcadia research; inspect the artifact, not just workflow success.
8. Preserve fail-closed behavior and do not promote execution failure to a finding.

Doctrine: LLMs propose. Tools test. Evidence decides.