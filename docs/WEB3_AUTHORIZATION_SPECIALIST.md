# Web3 Authorization Specialist — bounded completion plan

Status: proposed specialization; not yet validated as a real-world bug finder.

## Decision

For the first focused Web3 design, CYDRA will specialize in **missing or broken authorization on externally callable, state-changing Solidity functions**.

The initial scope is deliberately narrower than "all access-control bugs":

- identify public/external state-changing functions;
- infer candidate authorization invariants from source-backed modifiers, role checks, protected sibling functions, caller identity, and relevant state transitions;
- identify mismatches that have a plausible security boundary;
- construct a deterministic unauthorized-caller experiment;
- observe the actual state/asset/privileged-action effect;
- compare the result against a patched or otherwise correctly protected control;
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

### Gate C — unfamiliar authorized target

Use a pinned, in-scope Solidity target with a documented authorization policy. Do not infer permission to test from public availability alone. Run the specialist on the target without feeding it a known finding or vulnerable location.

Record separately:
- target/model coverage;
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
3. at least one unfamiliar, authorized target has been tested end to end;
4. any claimed real finding has a minimal reproducible PoC, demonstrated impact, provenance, and an independently checked result.

If no real finding emerges, report the exact failed stage and whether it is a target property, missing prerequisite, modeling gap, hypothesis-selection failure, or causal-verification gap. Do not reopen unrelated vulnerability classes.

## Required measurements

Report, at minimum:

- true positives / false positives on the controlled suite;
- known positives missed;
- hypotheses selected / experiments generated / experiments executed;
- execution blockers by category;
- confirmed findings / independently reproduced findings;
- time and tool cost per executed hypothesis.

Keep CI health separate from security effectiveness.

## Operating rule

**One vulnerability class, one measurable benchmark, one unfamiliar-target proof boundary.**

Loop: inspect evidence → identify the failing stage → repair the narrowest generic capability → run focused regressions → run the blind benchmark → replay the pinned authorized target → inspect every artifact.

No claim of "complete" or "bug-finding ready" is allowed solely because unit tests, CI, or historical benchmarks are green.
