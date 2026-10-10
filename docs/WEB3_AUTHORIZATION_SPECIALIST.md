# Web3 Authorization Specialist — bounded completion plan

Status: specialization is defined and the first controlled campaign passes. Real-world novelty and bounty readiness are **not yet established**.

## Decision

For the first focused Web3 design, CYDRA will specialize in **missing or broken authorization on externally callable, state-changing Solidity functions**.

The initial scope is deliberately narrower than "all access-control bugs":

- identify public/external state-changing functions;
- infer candidate authorization invariants from source-backed modifiers, role checks, protected sibling functions, caller identity, and relevant state transitions;
- identify mismatches that have a plausible security boundary;
- construct a deterministic unauthorized-caller experiment;
- observe the actual state/asset/privileged-action effect;
- compare the result against a correctly protected control;
- preserve provenance, uncertainty, and a reproducible test.

A missing modifier, suspicious function name, static-analysis warning, or revert is not itself a finding.

## Explicitly out of scope for this first specialist

Do not expand this milestone to reentrancy, arithmetic/accounting, oracle manipulation, signature/proof failures, generic state-sequence bugs, denial of service, or every possible authorization pattern. Existing shared infrastructure may still be used when it directly supports the authorization experiment, but these classes do not block this milestone.

## Reuse before rebuilding

Prefer existing CYDRA components for:

1. Solidity parsing and target/system modeling;
2. function visibility, modifiers, caller roles, state writes, and inherited-function relationships;
3. authorization invariant and hypothesis generation;
4. Foundry experiment rendering and execution;
5. structured evidence, vulnerable/patched differential checks, causal verification, and finding gates.

Do not create a second parallel reasoning engine. If a capability is missing, record the precise stage and repair the shared abstraction only when the failure demonstrates that it is required for this specialist.

## Acceptance gates

### Gate A — positive and negative controls

Build or reuse a small, diverse, deterministic suite that includes:

- a genuinely unauthorized state-changing action that should be detected;
- a protected counterpart that must not be reported;
- an intentionally permissionless state-changing function that must not be reported;
- inherited authorization and role/caller-state examples;
- a case where another guard enforces authorization even without a conventional modifier.

The suite must assert both detection and rejection behavior. A passing test suite is evidence of benchmark correctness, not proof of real-world bounty performance.

### Gate B — blind selection and executable validation

Run the specialist without revealing the vulnerable function or expected answer. CYDRA must independently select a candidate, generate the experiment, compile and execute it, and preserve raw output and source provenance.

For a candidate to reach the finding gate, the experiment must demonstrate a security-relevant unauthorized effect, not merely a reachable function or an expected revert. Competing explanations and external guards must be checked.

### Gate C — genuinely unfamiliar, authorized target

The first campaign's external target was decentxyz/decent-bridge at commit 7f90fd4489551b69c20d11eeecb17a3f564afb18, contract src/DcntEth.sol. CYDRA selected setRouter and classified the unauthorized state mutation as confirmed. However, this is **not a novel finding**: the same issue was publicly reported in the January 2024 Code4rena Decent findings, including [issue #465](https://github.com/code-423n4/2024-01-decent-findings/issues/465) and [issue #704](https://github.com/code-423n4/2024-01-decent-findings/issues/704). Treat this run as a historical external positive control, not evidence of bounty discovery or novelty.

The unfamiliar-target gate has now been exercised against two source revisions explicitly listed by their programs, using local-only analysis and harness execution:

- Immunefi Vaults System: `immunefi-team/vaults-splitter`, commit `6f64c3f0557967eee9b14482ffa62187101c79ef`, `src/Splitter.sol`.
- OpenZeppelin Community Contracts: `OpenZeppelin/openzeppelin-community-contracts`, commit `0361935dc5edd233adbb9fbae5871ccbb8c739d8`, `contracts/crosschain/axelar/AxelarGatewayAdapter.sol`. This exact commit is listed as in scope by the program.

Both targets compiled and produced compiler-backed state-effect evidence, but neither produced an authorization hypothesis. The runner correctly recorded `BLOCKED / NO_SUPPORTED_HYPOTHESIS / NOT_READY`. These are **not** clean `NO_CANDIDATE_FOUND` outcomes: the campaign did not establish enough coverage to conclude that the specialist has exhausted the relevant authorization surface. No production or public-testnet transactions were sent. Gate C therefore remains open.

Campaign run: [#38074638999](https://github.com/Wonderadroit/Cydra_wonder/actions/runs/38074638999). Its uploaded artifact contains the pinned target revisions, model evidence, dispositions, and logs. The successful workflow means the harness completed and preserved evidence; it does not mean a vulnerability was found or that either target is secure.

For that target, record separately:

- target and scope provenance;
- model/source coverage;
- candidate hypotheses;
- experiments generated and actually executed;
- blockers and their evidence;
- rejected candidates and why;
- confirmed findings and independent reproductions.

Zero findings is a valid result. Do not relax the finding gate to manufacture success.

### Gate D — finish line

The first specialist milestone is complete only when:

1. all focused positive and negative controls pass;
2. the blind runner's candidate selection and experiment path are exercised;
3. at least one genuinely unfamiliar, authorized target has been tested end to end;
4. any claimed real finding has a minimal reproducible PoC, demonstrated impact, provenance, and an independently checked result.

If no real finding emerges, report the exact failed stage and whether it is a target property, missing prerequisite, modeling gap, hypothesis-selection failure, or causal-verification gap. Do not reopen unrelated vulnerability classes.

## Current measurements

- Focused authorization regressions and the no-hypothesis artifact regression: passed.
- Known-vulnerable local positive control: classified confirmed as expected; causal and reproduction differentials verified in the prior focused run.
- Historical external positive control: `setRouter` classified confirmed, but it is a publicly documented January 2024 issue and is not novelty evidence.
- Protected negative control: classified not confirmed.
- Unfamiliar in-scope source revisions tested: 2; both compiler runs succeeded and emitted semantic state-effect evidence, but both ended `BLOCKED / NO_SUPPORTED_HYPOTHESIS / NOT_READY`.
- Experiments executed against those two unfamiliar targets: 0, because no authorization hypothesis was selected.
- Novel, independently reproduced bounty findings: 0.
- New unfamiliar-target evidence: [run #38074638999](https://github.com/Wonderadroit/Cydra_wonder/actions/runs/38074638999), artifact `cydra-unfamiliar-web3-authorization`.
- Main full Python regression after merge: [run #38074782743](https://github.com/Wonderadroit/Cydra_wonder/actions/runs/38074782743), passed.

Keep CI health separate from security effectiveness.

## Required measurements

Report, at minimum:

- true positives / false positives on the controlled suite;
- known positives missed;
- hypotheses selected / experiments generated / experiments executed;
- execution blockers by category;
- confirmed findings / independently reproduced findings;
- time and tool cost per executed hypothesis.

## Operating rule

**One vulnerability class, one measurable benchmark, one unfamiliar-target proof boundary.**

Loop: inspect evidence → identify the failing stage → repair the narrowest generic capability → run focused regressions → run the blind benchmark → replay the pinned authorized target → inspect every artifact.

No claim of "complete" or "bug-finding ready" is allowed solely because unit tests, CI, or historical benchmarks are green.
