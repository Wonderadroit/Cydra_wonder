# Benchmark 005 — Blind real-target discovery prediction

## Target-selection rule

The target is selected before CYDRA is run and without selecting it because of a suspected vulnerability. Selection is based only on structural criteria:

- real deployed Solidity protocol;
- open-source and externally audited;
- small enough for a bounded system-model experiment;
- live immutable v1 deployment;
- protocol behavior exercises authorization, initialization, arithmetic, accounting, or combinations of those classes;
- source snapshot is fixed before the blind run.

## Target

**The Gavel Protocol v1** — commit `bfb5086eb7915d2dc90f52fd761d54bc2806847d`.

The benchmark scope is the six core v1 Solidity contracts:

- `contracts/LoanProtocol.sol`
- `contracts/PositionNFT.sol`
- `contracts/ListingService.sol`
- `contracts/NFTLoanProtocol.sol`
- `contracts/NFTPositionNFT.sol`
- `contracts/NFTListingService.sol`

Interfaces and tests are excluded from the CYDRA model input. The target snapshot is the public repository commit above; no later source changes may enter this benchmark.

## Pre-registered extraction prediction

CYDRA will run only its already-existing rules. No target-specific vulnerability rule may be added before the blind run.

Expected extraction behavior from the target's structure:

1. **Initialization rule:** expected to fire on the six public/external `initialize` entry points.
2. **Authorization rule:** expected to inspect administrative functions and may emit an authorization invariant only where its existing structural rule finds protected administrative siblings. No target-specific authorization hypothesis is predicted in advance unless the existing extractor itself produces one.
3. **Arithmetic Benchmark 003 rule:** expected **not** to fire because the Gavel target does not contain the Benchmark 003 fixture expression.
4. **Accounting Benchmark 004 rule:** expected **not** to fire because this blind benchmark must not be selected or modified around the known Yield/`poolCached` pattern.

Expected hypothesis count: **6 initialization hypotheses**, plus **0 target-specific hypotheses from the arithmetic and cached-accounting rules**. Authorization hypotheses are expected to be zero unless the pre-existing extractor finds an unprotected administrative function; this is an extractor output to be recorded, not a manually supplied finding.

## Confirmation rule

A candidate may be classified as confirmed only if the existing experiment path executes against the real target snapshot and produces evidence of a reproducible security-relevant differential between vulnerable behavior and the applicable control/reference behavior.

For a genuinely discovered candidate, the evidence must establish:

- attacker-controlled precondition;
- relevant state transition;
- violated system invariant;
- measurable consequence;
- reproducible execution;
- no reliance on source-text parsing as the proof of exploitability.

A status-only PASS/FAIL result is insufficient for a measurement-outcome claim.

## False-positive definition

A CYDRA confirmation is a false positive if independent investigation shows that the apparent differential is prevented, neutralized, economically irrelevant to the claimed impact, or otherwise non-exploitable in the target's actual system model.

## Null-result classification

If CYDRA confirms nothing, the result will be separated into:

- **true negative:** generated hypotheses were exercised and independently found non-exploitable;
- **rule-set gap:** the relevant invariant/class was outside the existing extraction/hypothesis rules;
- **pipeline gap:** a rule fired but a later layer failed to represent or execute it.

## Ground-truth protection

No audit report, known-issues list, historical vulnerability database, bug-fix report, or external security analysis of this target will be consulted to guide CYDRA's hypothesis generation or experiment selection before the blind result is frozen.

After the blind result is frozen, external sources may be consulted as an independent oracle for post-run verification.

## Success criterion

Benchmark 005 succeeds methodologically if the complete blind run produces an interpretable outcome whose correspondence to reality can be independently classified as true positive, true negative, false positive, or rule/pipeline gap. A vulnerability discovery is not required for the benchmark to be informative.

## Scope of claim

A positive result would establish blind discovery on this one real protocol snapshot. It would not establish general DeFi discovery capability. A negative result would identify the first scaling limitation of the existing rule set or reasoning pipeline.
