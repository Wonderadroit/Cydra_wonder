# Arcadia Lending V2 — CYDRA public-code blind research intake

This is a public-code research experiment, not a HackenProof submission or live-program dogfood run.

Target snapshot:
- Repository: https://github.com/arcadia-finance/lending-v2
- Pinned source commit: def3c94995773e2feb48b6d8a02dc603d96fd96c
- Primary source: src/LendingPool.sol
- Historical program reference: HackenProof Arcadia Finance Smart Contracts. This reference is provenance only; it does not establish eligibility or authorization.

Research boundary:
- CYDRA analyzes the frozen public source locally in GitHub Actions.
- No HackenProof submission is made by this workflow.
- No live Arcadia deployment is contacted for exploitation.
- No live funds, user state, or external deployment state is mutated.
- Results are research candidates only until independently reviewed and, if applicable in a future authorized program, validated against that program's current rules and environment.
- The human researcher remains responsible for any later authorization, scope, validation, and submission.

CYDRA boundary:
- The existing blind runner is reused without target-specific detectors.
- The initial pass is blind with respect to historical audit findings and public vulnerability reports.
- CYDRA receives the frozen source and its normal compiler/structural evidence, not the historical answers.
- A measured execution is evidence about a hypothesis, not automatically a vulnerability.
- A finding requires the Project Bible's causal verification and reproducibility requirements.

Scope hygiene:
- The frozen target is src/LendingPool.sol at the exact commit above.
- The runner may inspect imported source required to model that target.
- Tests, mocks, scripts, deployment tooling, and unrelated third-party code are not research targets.
- The explicitly excluded SpotToMarginMigrator.sol is not a target of this experiment.

Blindness rule:
- Do not provide historical audit reports, known issue lists, public PoCs, or contest findings to CYDRA before this first blind run completes.
- Historical material may be used afterward for independent comparison and novelty assessment.

Reproducibility:
- The target commit is frozen.
- CI artifacts record the target ref, CYDRA commit, environment, hypotheses, experiments, executions, evidence, and classification.
- If the source commit or research boundary changes materially, create a new intake snapshot rather than silently moving this one.
