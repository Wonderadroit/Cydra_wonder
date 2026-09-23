# CYDRA Agent Handoff

Last reviewed: 2026-09-23
Repository: Wonderadroit/Cydra_wonder

## 1. Mission

CYDRA is a personal, authorized security-research reasoning/orchestration engine.

Core doctrine:

> Understand systems rather than memorize vulnerabilities.
> LLMs propose. Deterministic tools test. Evidence decides.

The Project Bible is authoritative. CYDRA is not being turned into a commercial audit/compliance product.

## 2. Accepted baseline

main: 52aecb0b4d11462fbe90fbbd3b5215ff5e7ed664

Main currently contains the generic execution-readiness chain developed from unfamiliar-target research:
- target/environment adapter;
- execution prerequisite modeling;
- execution value-producer resolution;
- inherited/imported producer resolution;
- compiler-backed state-effect evidence;
- state setup candidate discovery;
- state-guard polarity;
- compiler-backed collection-bound input planning.

The maturity/post-maturity validation gate is closed. Do not reopen it or create another benchmark unless a genuine blocker invalidates the closure.

## 3. Current research target

The active unfamiliar-target study is a public-code Arcadia Lending study, not a live bounty action.

Frozen target:
- repository: arcadia-finance/lending-v2
- commit: def3c94995773e2feb48b6d8a02dc603d96fd96c4
- primary source: src/LendingPool.sol

Boundary:
- no live Arcadia deployment interaction;
- no live-state mutation;
- no HackenProof submission;
- historical findings remain hidden from the initial blind run;
- generic repairs only.

The initial blind run established that target intake and compilation worked, but generated experiments often failed before reaching their security-relevant paths because constructor/runtime/state prerequisites were not sufficiently modeled or constructed. Those failures are execution-readiness evidence, not vulnerability evidence.

## 4. In-flight implementation

### PR #203
Branch: fix/generic-transitive-state-producers
Title: feat: follow generic compiler state dependencies through calls

Purpose:
- preserve compiler-resolved call edges;
- consume imported/inherited source ASTs in the dependency closure;
- propagate compiler-backed state reads/writes through resolved calls;
- fail closed on unresolved calls.

This is the correct abstraction boundary and aligns with the Bible.

### Important repair made during this checkpoint

The original PR #203 implementation indexed state effects by function name alone. That is unsafe for real Solidity projects because different contracts commonly contain functions with the same name. It could mix state effects across contracts during transitive propagation.

The branch has now been hardened to:
- key compiler state effects by contract::function;
- use compiler metadata to identify the called contract;
- propagate only along qualified call edges;
- require an unambiguous function when callers use the legacy lookup form;
- fail closed on ambiguous function names;
- pass the target contract explicitly from execution-readiness;
- add a regression proving balanceOf in one contract cannot leak into another same-named function.

This is a generic correctness repair, not an Arcadia-specific workaround.

## 5. Other recent work

PRs #198–#202 represent the execution-readiness validation/repair sequence leading to the current baseline. Inspect their merged state before repeating any work.

PR #197 was the earlier generic prerequisite/input-planning repair. Its key accepted boundary is:
state setup candidate → generic sequence construction/runtime dependency satisfaction

PR #203 continues that boundary by making compiler-backed producer dependencies transitive and contract-safe.

## 6. Current architectural boundary

The intended pipeline is:

Target → Adapter → System Model → Execution Readiness → State/Execution Guard Semantics → State Setup Candidates → Compiler-backed Input Planning → Executable Sequence → Runtime Dependency Construction → Verified State/Value → Security Experiment → Evidence → Causal Verification

Important distinction:
- discovered prerequisite != satisfied prerequisite;
- constructible transition != successful transition;
- execution failure != vulnerability;
- hypothesis != finding.

## 7. Immediate next work

1. Run focused tests for PR #203, especially compiler state-effect consumption and execution-readiness.
2. Inspect generated artifacts/results for the Arcadia blind study after the contract-qualified state-effect repair.
3. Run the intended research workflow, not the unrelated historical benchmark fan-out.
4. Diagnose the next concrete execution blocker from actual evidence.
5. Repair the generic abstraction only.
6. Retest and update this handoff.
7. Do not merge PR #203 until its relevant CI is genuinely complete and the regression/behavioral acceptance is satisfied.

## 8. CI fan-out warning

The repository has accumulated many historical benchmark workflows. A push can therefore create dozens of workflow runs even when only one research workflow is relevant.

GitHub Actions supports branch/path filters, and the repository should progressively isolate historical benchmark workflows from research branches while keeping required mainline validation intact. Do not interpret unrelated legacy workflow failures as evidence about the Arcadia investigation.

When checking CI, identify:
- intended workflow;
- commit SHA;
- workflow status/conclusion;
- jobs actually required for the current change;
- unrelated historical runs.

Never declare the current research change green while its required jobs are queued/running.

## 9. Resume procedure for any future agent

1. Read PROJECT_BIBLE.md.
2. Read docs/CYDRA_OPERATING_PROTOCOL.md.
3. Read this file.
4. Inspect main and all open PRs.
5. Inspect recent workflow runs for the relevant commit.
6. Inspect actual failing job logs before editing code.
7. Check whether the proposed repair is already present in an open PR.
8. Prefer the smallest generic repair.
9. Add focused positive and negative regression coverage.
10. Run the affected benchmark/campaign.
11. Wait for relevant CI.
12. Merge only after acceptance.
13. Update this file with the new durable checkpoint.

The chat may disappear. The repository must not lose the reasoning state.
