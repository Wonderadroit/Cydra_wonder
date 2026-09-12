# Benchmark 005 — LiquidClaw blind real-target discovery

## Integrity status

This is the fresh Benchmark 005 after the discarded Gavel target-selection attempt.

The Gavel attempt is not part of this benchmark because target-specific security-history searching occurred before execution. It is classified separately as `TARGET-SELECTION / RESEARCHER-CONTAMINATION`.

This benchmark uses a new target and a new frozen snapshot.

## Pre-run firewall

Before CYDRA execution is frozen:

- no vulnerability searches for LiquidClaw;
- no searches combining LiquidClaw with exploit, vulnerability, hack, bug, bounty, incident, or equivalent security-history terms;
- no Immunefi, audit, exploit-database, bug-fix-review, or historical disclosure consultation;
- no target-specific security rule or hypothesis may be added;
- no CYDRA architecture change may be made to obtain a positive result;
- only structural source/repository information may be used for selection and mechanical preparation.

The external security oracle is sealed until the CYDRA output is frozen, timestamped, and hashed.

## Target

Protocol: LiquidClaw Finance

Repository: `Jc-asastu/liquidclaw-bsc`

Frozen commit: `58bed220236e8cdd8d279ef7259b3298a71aac0b`

The frozen commit identifies the project as a ve(3,3) AMM deployed on BSC mainnet and Base L2 and explicitly discloses its architectural lineage: a rewrite/redesign of Solidly built on the Aerodrome reference implementation. This lineage is structural provenance, not a security-history finding, and is disclosed here so general architecture familiarity is not mistaken for target-specific discovery.

## Researcher-prior disclosure

No prior review of these eight LiquidClaw contracts appears in the CYDRA workspace or the current project conversation before this benchmark.

This disclosure cannot prove what may have been seen outside the project workspace. No known target-specific security knowledge is being used in this run. If such prior knowledge is later recalled, this benchmark must be invalidated rather than retroactively interpreted.

## Frozen scope

Exactly these eight contracts are in scope:

1. `contracts/Pool.sol`
2. `contracts/Router.sol`
3. `contracts/factories/FactoryRegistry.sol`
4. `contracts/VotingEscrow.sol`
5. `contracts/Minter.sol`
6. `contracts/RewardsDistributor.sol`
7. `contracts/Voter.sol`
8. `contracts/ProtocolGovernor.sol`

Interfaces, libraries, deployment scripts, tests, and all other contracts are excluded from the CYDRA model input.

All eight declared paths exist at the frozen commit. The target repository's Foundry configuration declares `contracts` as the Solidity source directory and the frozen Solidity sources use pragma 0.8.19. A local `forge` executable and outbound GitHub access are unavailable in this preparation environment, so a local compile could not be performed here. The frozen commit contains the target's own CI workflow, but no workflow run is attached to this initial commit. Therefore compile/model-parse success must be observed by the blind run and recorded as execution evidence rather than assumed here.

## Source-derived extraction prediction

The current CYDRA extraction rules are read-only and unchanged for this benchmark.

### Initialization

The initialization extractor matches public/external functions named exactly `initialize` or `init`.

Mechanical source inspection of the eight frozen contracts found exactly three matching entry points:

- `Pool.sol`: `initialize`
- `Minter.sol`: `initialize`
- `Voter.sol`: `initialize`

The other five in-scope contracts contain no matching public/external initializer.

Predicted initialization hypotheses: **3**.

### Authorization

The current authorization extractor requires both:

1. at least one administrative function named with the existing `set/add/remove/update/accept` prefix family carrying a Solidity modifier; and
2. at least one administrative sibling in that contract with no modifier.

Mechanical inspection of the eight frozen contracts predicts this condition is not met in any of them. The source contains inline `msg.sender` authorization checks, but those are not the modifier signal used by the current extractor. `FactoryRegistry` has modifier-protected administrative functions but no unmodified administrative sibling.

Predicted authorization hypotheses: **0**.

### Arithmetic

The current arithmetic extractor is the exact Benchmark 003 fixture predicate requiring `(assets * SCALE + 996) / 997`.

Prediction: **0 arithmetic hypotheses** for the frozen target.

### Cached accounting

The current accounting extractor is the exact Benchmark 004 predicate requiring the `poolCached` / live `balanceOf(address(this))` / `burn` pattern and the specific vulnerable payout expression.

Prediction: **0 cached-accounting hypotheses** for the frozen target.

### Total predicted hypotheses

**3** hypotheses across the four currently supported extraction classes, all predicted to be initialization hypotheses.

## Mechanical scope check

The blind runner must convert only the eight declared paths into `ContractModel` inputs.

Any CYDRA hypothesis whose source path is outside the eight-path manifest is a **scope violation** and invalidates the blind run before oracle comparison.

The run must record, for each of the eight contracts, whether parsing/model construction succeeded or failed.

## Verification methods — pre-committed

Independent verification methods are fixed before the blind result.

### Initialization finding

Deploy the frozen target contracts or the smallest faithful local reproduction of the frozen initialization path using Foundry. Execute the candidate initializer from an unprivileged actor in the relevant pre-initialized state. Verify the claimed privileged/lifecycle state transition directly with assertions against storage/state getters. Repeat with the corresponding safe/control state where applicable.

### Authorization finding

Deploy the frozen contract in Foundry. Call the claimed privileged state-changing function from an unprivileged actor. Assert that the claimed privileged state cannot be changed. If the finding depends on a particular role transition, reproduce that transition explicitly and verify the unauthorized actor's state-changing capability.

### Arithmetic finding

Construct a Foundry PoC from the frozen contracts and the smallest required mocks. Execute the claimed input and record the runtime numerical values. Assert the claimed numerical invariant/differential directly. The PoC must derive the values from contract execution, not from a Python reimplementation of the arithmetic.

### Accounting finding

Construct a Foundry PoC from the frozen contracts and the smallest required mocks. Establish the precondition, perform the claimed accounting/state transition, execute the affected operation, and assert the claimed payout/accounting differential from runtime values. The PoC must reproduce the state transition and consequence, not merely match source text.

### Null result

For a null result, manually review every emitted CYDRA invariant/hypothesis against the frozen source, attempt a bounded local Foundry reproduction of every confirmation-capable hypothesis, and compare the resulting state transition with the stated invariant. Target documentation may be consulted after the CYDRA freeze for intended behavior. External security-history sources remain sealed until the freeze.

## Post-freeze oracle classification

After the CYDRA output is frozen:

- confirmed + independently reproducible exploitable behavior = **True Positive**;
- confirmed + independently non-exploitable/non-security-relevant = **False Positive**;
- declined + independently non-exploitable = **True Negative**;
- declined + independently verified vulnerability within an existing supported rule class = **False Negative**;
- vulnerability exists but its invariant is outside current rule coverage = **Rule Gap**;
- a meaningful hypothesis cannot be represented/executed/classified by an existing pipeline layer = **Pipeline Gap**;
- no hypotheses generated where the expected rule should have fired = **Extraction Gap**.

## Extraction-gap category

**Extraction Gap** is a distinct Benchmark 005 outcome.

If fewer than three initialization hypotheses are generated despite the source-derived expectation of three, the run must record which of the eight contracts produced no extraction and whether the failure is:

- extractor predicate mismatch;
- parser/model construction failure;
- contract genuinely outside the rule's supported structure; or
- another mechanical pipeline limitation.

This is not silently classified as a genuine negative.

## Freeze protocol

After the blind run completes:

1. preserve the complete output verbatim;
2. record UTC timestamp;
3. compute SHA-256 of the frozen output;
4. store the exact target commit and CYDRA commit used;
5. do not edit or rerun the blind result before opening the external oracle.

Only after these five steps may external security history be consulted.

## Claim boundary

The benchmark measures one frozen LiquidClaw source snapshot. It does not establish general DeFi vulnerability-detection capability.

The benchmark tests whether the existing CYDRA reasoning pipeline can operate on a real target without a hand-crafted vulnerability rule and whether the research methodology remains clean when the researcher does not know the target's security answer in advance.
