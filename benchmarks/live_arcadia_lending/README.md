# Arcadia Lending V2 — supervised CYDRA dogfood intake

This is a live-program research intake, not a benchmark.

Target snapshot:
- Repository: https://github.com/arcadia-finance/lending-v2
- Pinned source commit: def3c94995773e2feb48b6d8a02dc603d96fd96c
- Primary source: src/LendingPool.sol

Program boundary:
- HackenProof Arcadia Finance Smart Contracts.
- The program lists accounts-v2, lending-v2, and asset-managers as in scope.
- Only Arcadia-developed code belonging to deployed contracts is in scope.
- Tests, mocks, scripts, deployment tooling, and third-party dependencies/imports are out of scope.
- SpotToMarginMigrator.sol is explicitly out of scope.

CYDRA boundary:
- This pilot uses the existing blind runner without target-specific detectors.
- The first pass is source/system-model + deterministic local experiment generation/execution.
- No live-chain exploit or external-state mutation is performed by this workflow.
- A result is not a finding unless the program's live-state requirements, impact requirements, reproducible PoC, and scope are independently satisfied.

Authorization gate:
- The workflow requires an explicit manual confirmation before execution.
- The human researcher remains responsible for program eligibility, authorization, scope, and final submission.

The target commit is frozen for reproducibility. If the program target or deployed version changes, create a new intake snapshot rather than silently moving this one.
