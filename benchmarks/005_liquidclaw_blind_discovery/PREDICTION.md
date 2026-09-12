# Benchmark 005 — LiquidClaw blind discovery prediction

## Target

Protocol: LiquidClaw Finance

Repository: `Jc-asastu/liquidclaw-bsc`

Frozen commit: `58bed220236e8cdd8d279ef7259b3298a71aac0b`

## Frozen scope

Exactly eight contracts:

- `contracts/Pool.sol`
- `contracts/Router.sol`
- `contracts/factories/FactoryRegistry.sol`
- `contracts/VotingEscrow.sol`
- `contracts/Minter.sol`
- `contracts/RewardsDistributor.sol`
- `contracts/Voter.sol`
- `contracts/ProtocolGovernor.sol`

No interfaces, libraries, tests, deployment scripts, or other contracts are CYDRA model inputs.

## Target-lineage disclosure

The frozen target commit itself identifies LiquidClaw as a rewrite/redesign of Solidly built on the Aerodrome reference implementation. This is disclosed architectural lineage. It is not a security-history source and was not used to select a vulnerability.

## Researcher-prior disclosure

No prior review of these eight LiquidClaw contracts appears in the CYDRA workspace or current project conversation before this benchmark. No known target-specific security knowledge is being used. If prior target-specific security knowledge is later recalled, this benchmark is invalidated.

## Extraction prediction

### Initialization

The existing initialization extractor matches public/external functions named `initialize` or `init`.

Source-derived prediction:

| Contract | Expected initialization hypotheses |
|---|---:|
| Pool.sol | 1 |
| Router.sol | 0 |
| FactoryRegistry.sol | 0 |
| VotingEscrow.sol | 0 |
| Minter.sol | 1 |
| RewardsDistributor.sol | 0 |
| Voter.sol | 1 |
| ProtocolGovernor.sol | 0 |

Expected initialization total: **3**.

### Authorization

The existing authorization extractor requires at least one modifier-bearing administrative function and at least one unmodified administrative sibling in the same contract. Source inspection of the frozen eight-contract scope predicts that this condition is not met in any of the eight contracts.

Expected authorization hypotheses: **0**.

This is a structural extractor prediction, not a claim that the target has no access-controlled operations. Inline `msg.sender` checks are not the modifier signal used by the current extractor.

### Arithmetic

The existing arithmetic rule only recognizes the Benchmark 003 expression `(assets * SCALE + 996) / 997`.

Expected arithmetic hypotheses: **0**.

### Cached accounting

The existing cached-accounting rule only recognizes the Benchmark 004 `poolCached`/live-balance/burn pattern and exact vulnerable payout expression.

Expected cached-accounting hypotheses: **0**.

### Total predicted hypotheses

**3** total hypotheses from the four currently supported extraction classes, all predicted to be initialization hypotheses.

## Experiment prediction

For each of the three initialization hypotheses actually emitted, the existing initialization planner should produce one existing initialization experiment.

Expected initialization experiment count: **3**.

No new planner or target-specific adapter may be added before the blind result.

## Confirmation prediction

Confirmation requires executed evidence showing a reproducible security-relevant differential consistent with the hypothesis.

Source pattern alone is not confirmation.

Status-only execution is insufficient for a measurement-outcome claim.

## Outcome classes

- True Positive: confirmed and independently verified exploitable.
- True Negative: declined and independently non-exploitable.
- False Positive: confirmed but independently non-exploitable/non-security-relevant.
- False Negative: independently verified vulnerability within current supported rule coverage, but CYDRA did not confirm it.
- Rule Gap: vulnerability exists but its invariant is outside current rule coverage.
- Pipeline Gap: meaningful hypothesis cannot be represented/executed/classified by an existing pipeline layer.
- Extraction Gap: a pre-registered extractor expectation is not met, including the expected three initialization hypotheses.
- Scope Violation: CYDRA reasons over a contract outside the eight-path manifest.

## Independent verification pre-commitment

Initialization: Foundry deployment/local reproduction; unprivileged caller executes the initializer in the relevant pre-initialized state; claimed privileged/lifecycle state is checked directly.

Authorization: Foundry deployment/local reproduction; unprivileged caller invokes the claimed privileged function; state mutation is checked directly.

Arithmetic: Foundry PoC using frozen contracts/minimal mocks; claimed numerical differential is reproduced from runtime execution values.

Accounting: Foundry PoC using frozen contracts/minimal mocks; claimed accounting state transition and numerical consequence are reproduced from runtime execution values.

Null: manual review of every emitted invariant/hypothesis against the frozen source plus bounded Foundry reproduction attempts for confirmation-capable hypotheses. Target documentation may be used after the freeze; external security history remains sealed until after the freeze.

## Freeze

The complete CYDRA output will be frozen verbatim, timestamped in UTC, hashed with SHA-256, and preserved with the exact target and CYDRA commit identifiers before any external security oracle is consulted.

## Claim boundary

This benchmark tests one real LiquidClaw source snapshot. It does not establish general DeFi discovery capability.

**Prediction status: LOCKED BEFORE BLIND EXECUTION**
