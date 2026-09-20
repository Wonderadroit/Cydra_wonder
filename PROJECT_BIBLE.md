# CYDRA Project Bible

## 1. Mission

CYDRA is a personal security-research reasoning engine for authorized targets. Its purpose is to help its owner understand a target system deeply and discover real, non-obvious, reproducible vulnerabilities that can be responsibly reported under the target program's rules and potentially submitted for bug-bounty rewards.

CYDRA is not being built as a company product, commercial audit platform, compliance product, or service to sell. Its primary purpose is practical personal bug-bounty/security research.

CYDRA optimizes for **truth, causal understanding, reproducibility, and useful research outcomes**, not the number of alerts or reports produced.

## 2. Central philosophy

> Understand systems rather than memorize vulnerabilities.

> LLMs propose. Deterministic tools test. Evidence decides.

A vulnerability is not a prompt answer. It is a demonstrated causal relationship between attacker capability, system behavior, a violated invariant, and meaningful impact.

## 3. Non-negotiables

1. Authorized testing only.
2. Program scope and permitted environments are first-class constraints.
3. No unsupported findings.
4. Every material claim must have evidence provenance.
5. Correlation is not causation.
6. Suspicion is not a finding.
7. Static-analysis output is a hypothesis until validated.
8. Historical findings are reasoning evidence, never answers to copy.
9. Competing explanations must be preserved when uncertainty remains.
10. Test selection should maximize information gained per unit of investigation budget.
11. Findings require reproducible causal evidence.
12. Regression tests must preserve every confirmed result and important failure.
13. CYDRA must adversarially challenge its own hypotheses.
14. Human review remains responsible for any external submission.
15. CYDRA must never fabricate functions, state variables, execution paths, impact, or evidence.
16. CYDRA development must not drift toward a commercial-product objective that is not part of its mission.
17. The Project Bible is the authoritative source of truth for CYDRA's purpose, architecture, priorities, and development direction.

## 4. Investigation doctrine

The canonical flow is:

**Evidence → Correlation → Uncertainty → Causality → Test Planning → Hypothesis Updating → System Model → Finding**

The engine repeatedly cycles through this loop. It does not assume that the first explanation is correct.

## 5. Role of AI

AI/LLMs are reasoning instruments, not authorities. They may:

- summarize code and architecture;
- propose invariants;
- propose hypotheses;
- identify structural inconsistencies;
- generate candidate experiments;
- suggest tool configurations;
- interpret raw tool results;
- propose competing explanations;
- identify missing evidence.

AI may not independently promote a hypothesis to a confirmed vulnerability.

All AI-generated claims must resolve against the actual target model and evidence store.

## 6. System understanding

Before deep vulnerability hunting, CYDRA builds a system model containing, where available:

- source files and compiler metadata;
- contracts/modules/packages;
- functions and signatures;
- callers and call graph edges;
- state variables and state transitions;
- modifiers and authorization boundaries;
- external calls and trust boundaries;
- assets and economic flows;
- proxy and implementation relationships;
- deployment/network information;
- configuration and initialization paths;
- tests and declared properties;
- program scope and exclusions.

The model must preserve source provenance and confidence.

## 7. Invariants

CYDRA asks what must remain true for the system to behave as intended.

Invariant candidates may arise from:

- explicit specifications;
- documentation;
- tests;
- access-control structure;
- accounting relationships;
- state-machine rules;
- economic conservation;
- sibling-function symmetry;
- cross-contract expectations;
- initialization assumptions;
- protocol lifecycle constraints.

An invariant is not accepted merely because an LLM invented it. Its provenance and confidence must be recorded.

## 8. Structural reasoning

CYDRA must systematically compare related behavior, including:

- sibling functions;
- read/write pairs;
- deposit/withdraw flows;
- mint/burn flows;
- initialize/reinitialize flows;
- privileged/unprivileged entry points;
- callback/non-callback variants;
- equivalent operations across contracts;
- proxy versus implementation behavior;
- configuration paths and their consumers.

The engine should actively ask whether an inconsistency is intentional, harmless, protected elsewhere, or exploitable.

## 9. Hypotheses

Each hypothesis must be structured, not free-form prose.

Minimum conceptual fields:

- hypothesis ID;
- claim;
- target entities;
- violated invariant;
- suspected attacker capability;
- required execution path;
- expected state transition;
- expected impact;
- supporting evidence;
- contradictory evidence;
- confidence;
- competing hypotheses;
- proposed experiment;
- validation status;
- provenance.

A hypothesis can be rejected, weakened, strengthened, or confirmed. Evidence must not be silently discarded.

## 10. Competing hypotheses

CYDRA should prefer explicit alternatives over premature certainty.

Example:

- H1: missing authorization is exploitable;
- H2: authorization is intentionally delegated elsewhere;
- H3: the path is reachable but economically harmless;
- H4: another invariant prevents exploitation.

The test planner should select experiments capable of distinguishing these explanations.

## 11. Information-gain testing

The engine should not blindly execute every available scanner. It should select the next investigation step based on:

- uncertainty;
- expected information gain;
- cost/time;
- tool suitability;
- environmental permissions;
- reproducibility;
- ability to distinguish competing hypotheses.

Possible actions include code inspection, static analysis, targeted Foundry tests, fuzzing, symbolic execution, formal checking, forked execution where permitted, or additional system-model extraction.

## 12. Tool orchestration

CYDRA should reuse mature tools rather than reinventing them.

Initial tool families include:

- Solidity/Vyper compiler and parser tooling;
- Slither;
- Foundry;
- Echidna;
- Medusa;
- Halmos;
- Kontrol/KEVM where justified;
- Chimera and compatible property-testing workflows;
- custom Python analyses.

The engine chooses tools according to hypotheses and evidence requirements. Tool output becomes evidence, not truth by itself.

## 13. Execution and PoC discipline

For an exploitable claim, CYDRA must seek executable reproduction in an authorized environment.

Where economically relevant, the reproduction should demonstrate the actual security consequence, including attacker capability and state/economic effect rather than merely reaching a suspicious line.

Forking mainnet is not a universal rule. CYDRA must first evaluate the target program's authorization and environment rules and use only permitted environments.

## 14. Causal verification

A confirmed finding requires, as applicable:

1. real target code;
2. real reachable path;
3. real attacker capability;
4. real violated invariant;
5. real causal state transition;
6. demonstrated security/economic impact;
7. reproducibility;
8. evidence provenance;
9. competing explanations sufficiently eliminated.

If these conditions are not satisfied, the result remains a hypothesis or observation.

## 15. Finding gate

CYDRA must never convert:

**AI suspicion → Finding**

The required promotion path is:

**Observation → Hypothesis → Test → Evidence → Causal verification → Reproducible finding**

No PoC or equivalent rigorous proof means no confirmed finding when the claim depends on exploitability.

## 16. Submission boundary

CYDRA is not an autonomous bounty-report generator.

It may assemble an evidence package and a draft containing only verified facts, but a human researcher must review and own the final submission.

The system must reject or flag claims that reference nonexistent code, unsupported impact, unverifiable execution, or evidence not linked to the target.

## 17. Historical learning

Historical vulnerabilities, Immunefi cases, public PoCs, audit reports, and benchmark cases are used to learn reasoning patterns.

CYDRA must learn abstractions such as:

- missing protection among sibling operations;
- broken accounting invariants;
- initialization inconsistencies;
- privilege-boundary mismatches;
- cross-contract trust failures;
- temporal/state-machine violations;
- economic conservation failures.

It must not simply retrieve a similar historical report and reproduce its answer.

## 18. Benchmarking

CYDRA will maintain blind historical benchmarks. The system should measure:

- confirmed findings;
- missed findings;
- false positives;
- hypotheses rejected correctly;
- time/cost per validated hypothesis;
- evidence completeness;
- reproducibility;
- impact-confirmation rate;
- tool usefulness;
- reasoning-pattern effectiveness.

A benchmark answer must never be injected into the investigation context before the blind run is complete.

## 19. Adversarial self-testing

CYDRA must attack its own conclusions.

For every serious hypothesis it should ask:

- What assumption could be wrong?
- Can another actor explain the behavior?
- Is the path actually reachable?
- Is the impact real or merely theoretical?
- Is there an external guard not yet modeled?
- Does the same reasoning hold for sibling functions?
- Can the claimed impact be reproduced independently?

## 20. Evidence provenance

Evidence must identify where it came from, when it was observed, which target/version it applies to, and which hypothesis it supports or contradicts.

Source locations, tool versions, command/configuration, execution environment, and relevant artifacts should be retained where practical.

## 21. Regression doctrine

Every important discovery or failure becomes a regression case when practical.

CYDRA must preserve:

- confirmed findings;
- rejected false positives;
- important near-misses;
- parser/compiler failures;
- tool-routing failures;
- reasoning failures;
- benchmark cases.

## 22. Security boundaries

CYDRA is a research engine for authorized security work. It must not be designed around unauthorized access, credential theft, persistence, evasion, destructive exploitation, or indiscriminate scanning.

## 23. Success criterion

The primary success metric is not the number of alerts.

CYDRA succeeds when it can take a real authorized target, understand its behavior, identify non-obvious hypotheses, efficiently select discriminating tests, and produce reproducible evidence for a genuine vulnerability that survives adversarial review.

For the owner's practical objective, CYDRA should ultimately function as a useful personal bug-bounty research instrument: something that improves the researcher's ability to discover and validate genuine vulnerabilities in authorized programs.

## 24. Architectural rule

Do not add architecture merely because it is interesting.

Every component must improve at least one of:

- system understanding;
- hypothesis quality;
- uncertainty reduction;
- test selection;
- causal verification;
- reproducibility;
- benchmark performance.

If it does not, defer it.

## 25. Build philosophy

Build → run → test → inspect evidence → benchmark → improve.

Prefer one demonstrated capability over many speculative files.

The project should continuously prove that each new reasoning capability works against historical or authorized live cases.


## 26. Guided-to-blind development loop

CYDRA development should now use a deliberate two-stage backtesting cycle to accelerate diagnosis while preserving the ultimate requirement of blind discovery.

### 26.1 Guided discovery

In guided mode, CYDRA may be told the general security question or vulnerability class being investigated, but it must not be given the answer.

Guidance must not reveal:
- the vulnerable function;
- the exact vulnerable line or condition;
- the exploit sequence;
- the expected invariant violation;
- the expected state transition;
- the expected impact;
- the historical finding or PoC answer.

CYDRA must still perform the reasoning chain itself: Target → System Model → Invariant → Hypotheses → Experiments → Evidence → Causal Conclusion.

Guided mode exists primarily to expose missing capabilities quickly and make failures diagnosable.

### 26.2 Diagnose and repair

When guided discovery fails, CYDRA development must identify the exact stage that failed before changing architecture.

Possible failure stages include extraction/modeling, invariant generation, hypothesis generation, competing-condition discovery, experiment planning, input planning, execution/rendering, observation/evidence collection, hypothesis updating, causal classification, and impact/finding promotion.

Only the demonstrated blocker should drive the next implementation change. After a repair, the guided target and appropriate negative controls must be retested.

### 26.3 Blind discovery

After the guided capability works, the same or comparable target should be investigated in blind mode.

Blind mode removes the vulnerability-class guidance and exposes CYDRA only to the information a real researcher would have in the authorized investigation.

A historical benchmark's known answer must remain hidden from CYDRA until the blind investigation is complete.

### 26.4 Repeating the cycle

The preferred development cycle is:

Guided → Diagnose → Fix → Guided Retest → Blind → Diagnose → Fix → Blind Retest → New Target

This replaces speculative infrastructure expansion as the default development method.

A guided success is not proof of general vulnerability discovery. A blind success is stronger evidence that the capability generalizes.

### 26.5 Differential causal verification

Where a historical vulnerable and patched version are available, they may be used for differential validation after CYDRA has independently formed its investigation.

The patched version is evidence for causal discrimination, not an oracle that tells CYDRA what to find.

Record at least: guided failure; guided success but blind failure; blind correct hypothesis; blind hypothesis without sufficient proof; blind incorrect hypothesis; blind unrelated real finding; unsupported claim; and execution/tool failure.

## 27. Anti-overfitting and generalization rule

CYDRA must not be built as a collection of isolated detectors for a growing list of named vulnerability classes.

Existing reasoning capabilities such as authorization, initialization, arithmetic, and cross-function state reasoning are examples of demonstrated capabilities, not the boundaries of CYDRA's brain.

When a new historical vulnerability is missed, ask: What general reasoning capability did the investigation require that CYDRA lacked?

Address that demonstrated capability at the appropriate abstraction level rather than encoding the historical answer or benchmark-specific pattern.

A new component, heuristic, detector, or abstraction should require evidence from an actual investigation or reproducible regression showing that it improves system understanding, hypothesis quality, uncertainty reduction, test selection, causal verification, reproducibility, or benchmark performance.

## 28. Blind discovery is the primary progress criterion

CYDRA must not be considered mature merely because CI is green, many benchmarks pass, many vulnerability classes have dedicated code, many hypotheses are generated, many scanners are integrated, or the repository contains extensive infrastructure.

The stronger progress signal is demonstrated behavior on unfamiliar authorized targets.

The development priority is therefore:

Use CYDRA → observe what it cannot do → diagnose the failure → improve the missing general capability → retest → hide the guidance → verify generalization.

The purpose of historical backtesting is to make CYDRA better at real bug-bounty research, not to maximize benchmark scores.

## 29. Project Bible authority and drift prevention

The Project Bible is the single source of truth for CYDRA.

Before any new feature, architecture change, benchmark strategy, recommendation, prioritization, or change in project direction, the current Project Bible must be consulted.

No recommendation should silently introduce a new objective, product direction, abstraction, workflow, or capability that conflicts with the Bible.

When a proposed change appears to conflict with the Bible, stop and resolve the conflict against the Bible before implementation.

Decision hierarchy:
1. Project Bible.
2. Demonstrated evidence from authorized investigations and regressions.
3. Actual tool and execution evidence.
4. Engineering judgment.

Engineering convenience, novelty, benchmark aesthetics, or speculative future needs must not override the first three.

If the project direction genuinely needs to change, update the Bible deliberately first; implementation then follows the updated Bible. Drift must never happen implicitly through accumulated code.

## 30. Working-branch discipline

main is the canonical working branch after repository consolidation.

Feature branches are temporary laboratories for a specific demonstrated investigation need. They should not become permanent parallel versions of CYDRA.

Preferred workflow:

main → focused experiment/change → validate → merge into main → clean up branch → continue from main

Branch proliferation must not become a substitute for deciding what CYDRA actually needs.

## 31. Current development phase

CYDRA is now in a discovery-validation phase, not a foundation-expansion phase.

The immediate objective is to use the consolidated system on unfamiliar historical vulnerable targets and determine whether the complete reasoning loop can produce useful, reproducible discoveries.

Do not add another layer of architecture merely because the Project Bible mentions it.

Instead:

Backtest → Diagnose → Fix demonstrated blocker → Retest → Blind → Generalize → Repeat.

The next capability should be determined by the next real investigation failure.

### CYDRA development rule

> Before we add anything, we read the Bible.
>
> Before we recommend anything, we check it against the Bible.
>
> Before we change direction, we update the Bible deliberately.
>
> We do not build CYDRA around what sounds impressive. We build what real investigations prove it needs.
>
> Guided testing teaches us where we are weak. Blind testing tells us whether we actually learned.
>
> The end goal is a personal bug-bounty research instrument that helps its owner find and prove real vulnerabilities—not a commercial product.


## 32. Historical backtest milestone — generalized weighted-average rounding

The next demonstrated capability after the Alchemix authorization backtest and the Enzyme trusted-input boundary is structural weighted-average rounding reasoning.

The implementation is permitted because it comes from a real historical investigation blocker, not from a target-specific detector. The capability should recognize a generic four-unsigned-integer weighted-average shape, form a conservative rounding-direction hypothesis, choose a fractional boundary experiment, and validate the result through executable differential evidence.

The Graph historical benchmark is used as a demonstration target. Its repository, historical revision, and patched revision are benchmark inputs; CYDRA's reasoning must discover the candidate from the source model rather than receiving the known vulnerable function, line, exploit sequence, or expected answer.

The benchmark is successful only when:
- the blind source produces a weighted-average rounding hypothesis;
- CYDRA creates a concrete fractional boundary experiment;
- the vulnerable historical source executes and violates the modeled invariant;
- the patched source executes and satisfies it;
- the differential evidence passes the canonical causal-verification path; and
- the finding gate has sufficient evidence and impact assessment.

This milestone does not justify adding The Graph-specific names, ratios, or exploit sequences to the reasoning engine. A failure on another rounding mechanism must be diagnosed as a new general capability gap before code is changed.

## 33. Historical backtest milestone — sibling postcondition parity

A subsequent historical investigation demonstrated another general reasoning capability: a security-relevant postcondition may be enforced by several sibling state-changing transitions while a newly added transition silently omits it.

The implemented capability is class-neutral. It:
- observes postcondition/guard calls in externally callable state-changing siblings;
- identifies a shared state surface between guarded peers and an unguarded transition;
- forms a hypothesis about the missing postcondition rather than naming a vulnerability class;
- plans a discriminating state-reducing experiment;
- executes vulnerable and patched counterparts; and
- sends the differential evidence through the canonical causal-verification and finding gate.

The benchmark fixture is an extracted historical representation of the Euler EToken guard gap. The vulnerable provenance is pinned to the Euler legacy repository commit that introduced `donateToReserves`; the patched counterpart represents the documented post-incident restoration of `checkLiquidity(account)`. This fixture is explicitly recorded as an extracted historical regression, not as a claim that the current Euler repository master is the patched source.

The successful run demonstrated:
- blind structural hypothesis: `donateToReserves may return after mutating shared state without enforcing the postcondition observed in sibling transitions`;
- vulnerable execution: FAIL;
- patched execution: PASS;
- canonical verification: SUPPORTED;
- causal verification: VERIFIED;
- finding gate: READY.

This milestone must not become an Euler-specific detector. The next unfamiliar target must determine whether sibling postcondition parity generalizes beyond the historical extraction.


## 34. Historical backtest milestone — Graph rounding finding reproduced end-to-end

The Graph weighted-average benchmark has now completed the full blind differential finding path after a demonstrated execution-binding failure was repaired.

The blocker was not a reasoning failure: the patched historical revision renamed the structurally equivalent four-uint internal operation from `weightedAverageRoundingUp` to `weightedAverage`, while the runner incorrectly excluded the latter when resolving the patched callable. The fix removed that unjustified exclusion and kept binding structural rather than Graph-specific.

Run evidence on the repaired benchmark:
- blind hypothesis: `weightedAverage may round a weighted average down when the exact result is fractional, weakening a conservative boundary invariant`;
- experiment inputs: `(100, 2, 99, 1)`;
- vulnerable historical execution: FAIL;
- patched historical execution: PASS;
- canonical verification: SUPPORTED;
- causal verification: VERIFIED;
- impact assessment: HIGH for thawing-period enforcement;
- finding gate: READY.

The historical revisions are taken from The Graph contracts repository around commit `25d07528b1107682674bfe0bed56523238fcacb1`. The benchmark must be understood as a historical backtest of the exact revisions, not as a statement about the current repository state.

This milestone is evidence that CYDRA can independently derive a non-trivial arithmetic invariant, select a discriminating fractional boundary, execute the historical vulnerable and patched implementations, and promote the result through causal verification. It does not justify hard-coding The Graph's function names or exploit answer.

The next development step remains unfamiliar-target testing. If another target fails, diagnose the missing general capability rather than adding a target-specific rule.


## 35. Historical backtest milestone — temporal precondition / call-order reasoning

An unfamiliar historical security pattern has now completed the blind differential finding path: a security-relevant precondition can be checked only after an external state-changing call, allowing that call sequence to alter the predicate and make the check succeed retroactively.

The capability is class-neutral. It observes externally callable state-changing functions, detects an external-call-before-precondition topology, forms a temporal invariant, plans an experiment around the predicate changing during the transition, and validates vulnerable versus patched behavior through the canonical causal path.

The historical source pattern is derived from the OpenZeppelin TimelockController vulnerability disclosed in 2021. OpenZeppelin's post-mortem describes the vulnerable ordering in `executeBatch`: calls were executed before the final readiness check, allowing an unprepared batch to schedule itself during execution and become ready; the fix added a readiness check before execution while retaining the post-execution check. This benchmark uses an extracted minimal regression fixture representing that causal shape rather than embedding OpenZeppelin's names or exploit sequence in CYDRA.

Successful blind benchmark 010 evidence:
- blind hypothesis: `execute may make an external state-changing call before checking a security-relevant precondition, allowing the call sequence to change the predicate and satisfy it retroactively`;
- vulnerable execution: FAIL;
- patched execution: PASS;
- canonical causal verification: VERIFIED;
- finding gate: READY.

This milestone demonstrates a fourth materially different blind discovery mechanism after authorization, arithmetic rounding, and sibling postcondition parity. It must not become a TimelockController-specific detector. The next unfamiliar target must test whether temporal precondition reasoning generalizes beyond the extracted fixture.


## 36. Historical backtest milestone — repeated-record idempotency / value release

An unfamiliar historical mechanism has now completed the blind differential finding path: a user-controlled batch can repeat the same state-record identifier, and a value-releasing transition can consume that record more than once when it does not enforce the record's required pre-state before the side effect.

The capability is class-neutral. It observes externally callable state-changing batch functions that iterate over supplied record identifiers, mutate per-record state, release value, and lack an observed pre-state guard. It forms an idempotency invariant, plans a repeated-record experiment, and validates vulnerable versus patched behavior through the canonical causal path. The detector does not encode Mt Pelerin, `cancelOnHoldTransfers`, the historical exploit sequence, or the expected answer.

The historical regression represents the documented Mt Pelerin 2022 double-transaction issue, where repeated transaction identifiers could cause the same value to be released repeatedly and the fix added a check that the transfer was still on hold. The benchmark is an extracted historical regression, not a claim about the current target repository.

Successful blind benchmark 011 evidence:
- blind hypothesis: the state record may be processed repeatedly because the value-releasing transition lacks an observed pre-state guard;
- discriminating experiment: the same record identifier is supplied twice in one batch;
- vulnerable execution: FAIL because the same record releases value more than once;
- patched execution: PASS because the repeated record is rejected before the second release;
- canonical causal cycle: completed successfully;
- causal verification: VERIFIED;
- finding gate: READY.

During validation, CYDRA exposed and the benchmark repaired two generic execution weaknesses rather than hiding them with target-specific exceptions: the semantic model did not expose a nested mapping write even though source topology showed it, and the execution harness initially selected the first parsed contract rather than the contract containing the hypothesized function. The detector was made tolerant of qualified/enum state assignments, and the execution path now binds to the contract that actually owns the target function. The benchmark also preserves executable diagnostics as CI artifacts for provenance.

This milestone is evidence that CYDRA can derive and prove a non-obvious repeated-record/idempotency failure mechanism on an unfamiliar historical target. It does not justify adding Mt Pelerin-specific names or exploit answers. The next unfamiliar target must test whether idempotency reasoning generalizes beyond this extracted fixture.


## 37. Historical backtest milestone — transient read-only state during external callbacks

An unfamiliar historical mechanism has now completed the blind differential finding path: a state-changing transition can expose an intermediate state through an externally callable view while an external callback is executing, allowing a consumer to treat a transient value as settled state.

The capability is class-neutral. It observes externally callable state-changing transitions that write a multi-variable state surface and perform an external value transfer, then compares that surface with externally callable view functions that derive values from the same state. If the view has no observed lock protecting it during the transition, CYDRA forms a hypothesis that the view may expose an inconsistent intermediate value during the callback. The reasoning does not encode Curve, Balancer, LP-token names, oracle names, or the historical exploit sequence.

The historical pattern is represented by an extracted regression fixture based on the documented Curve read-only-reentrancy problem. ChainSecurity reported that Curve's `get_virtual_price` could be manipulated by reentering it during liquidity removal, because the pool could be observed in an incompletely updated state. The benchmark uses only the causal pattern as a learning target, not the historical answer.

Successful blind benchmark 012 evidence:
- blind hypothesis: the public view may observe an inconsistent intermediate state when called during the external callback of the state-changing transition;
- discriminating experiment: a receiver reenters the view during the value-transfer callback and compares that observation with the settled value;
- vulnerable execution: FAIL, because the callback-time view returned the transient value;
- patched execution: PASS, because the view was protected while the transition was incomplete;
- canonical causal cycle: completed successfully;
- causal verification: VERIFIED;
- finding gate: READY.

The first CI attempt reached the full benchmark but failed after the detector regression test, so the benchmark output was preserved and the workflow was rerun. The repaired run completed successfully, including the actual Foundry differential path. No target-specific exception was added.

This milestone is evidence that CYDRA can reason about a cross-function transient-state/trust-boundary failure that differs materially from authorization, arithmetic rounding, sibling guard parity, temporal ordering, and repeated-record idempotency. The next unfamiliar target must test whether this transient-state reasoning generalizes beyond the extracted fixture.
