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


## 38. Historical backtest milestone — inbound transfer accounting / actual balance delta

An unfamiliar accounting mechanism has now completed the blind differential finding path: a receiving contract can credit a requested token amount even though the token's transfer semantics deliver less than requested, causing internal liabilities to exceed assets actually received.

The capability is class-neutral. It observes externally callable state-changing functions that perform an inbound `transferFrom` and then credit accounting state with the requested transfer argument without observing a pre/post token balance delta. It forms an invariant that internal credit must equal the actual received balance delta, plans a boundary transfer experiment, and validates vulnerable versus patched behavior through the canonical causal path. The detector does not encode a named protocol, token, historical exploit, or expected answer.

The historical regression represents the documented fee-on-transfer accounting pattern observed across multiple DeFi incidents and audit findings: the receiving contract records the requested amount while the token delivers less, creating an accounting mismatch that can make later redemptions undercollateralized. Public security analysis documents the standard mitigation as measuring the receiving contract's token balance before and after the transfer and crediting the delta. This benchmark is an extracted causal regression, not a claim about any current production repository.

Successful blind benchmark 013 evidence:
- blind hypothesis: `deposit may credit the requested token amount even when the token delivers less, allowing internal accounting to exceed assets actually received`;
- discriminating experiment: transfer 100 units through `deposit` and compare internal credit with the actual token balance held by the receiver;
- vulnerable execution: FAIL because 100 units were credited while only 90 units arrived;
- patched execution: PASS because the patched path credited the measured received amount;
- canonical causal verification: VERIFIED;
- finding gate: READY.

During validation, the execution harness initially exposed two generic runner problems rather than hiding them with target-specific exceptions: the temporary Foundry project lacked the repository's `forge-std` dependency, and the benchmark renderer had temporary diagnostic syntax that was corrected. The final renderer uses only Solidity's native `require`, keeping the extracted regression dependency-free. The benchmark then completed with pytest, Foundry execution on both historical sides, causal verification, and finding-gate promotion all successful.

This milestone is evidence that CYDRA can reason about an asset/accounting conservation boundary that differs materially from authorization, arithmetic rounding, sibling guard parity, temporal ordering, repeated-record idempotency, and transient read-only state. The next unfamiliar target must continue to test transfer/accounting reasoning against a different concrete system before treating the capability as broadly generalized.

## 39. Historical backtest milestone — conservative redemption rounding / empty-market accounting

The next unfamiliar historical investigation after inbound transfer accounting exposed a distinct accounting failure: a withdrawal path can convert a requested asset amount into receipt/share units using integer division and round the required burn down. Under an extreme exchange rate, the one-unit truncation is no longer economically negligible.

The capability is class-neutral. It observes a redemption transition that derives an exchange rate from a supply-backed asset balance, converts a requested asset withdrawal into receipt units by division, and releases assets while the conversion rounds down. It forms the invariant that the required receipt-unit burn must not be below the mathematical ceiling, plans a fractional boundary experiment, and validates vulnerable versus patched behavior through the canonical causal path.

The extracted historical regression represents the causal shape documented in the November 2023 Onyx Protocol incident and the related Compound-v2 empty-market incidents: a near-empty receipt-token market can be given an extreme exchange rate by direct asset inflow, after which redemption rounding can burn fewer receipt units than required. The benchmark intentionally contains no Onyx contract name, exploit sequence, market name, flash-loan choreography, or expected historical answer.

Successful benchmark 014 requires:
- blind extraction of the redemption-rounding hypothesis;
- no matching hypothesis on the patched counterpart;
- executable vulnerable FAIL because the required burn is rounded down;
- executable patched PASS because the required burn uses the mathematical ceiling;
- canonical causal verification; and
- finding-gate readiness.

This milestone is a generalization candidate, not proof that all redemption or share-accounting systems are covered. The next unfamiliar target must determine whether conservative redemption-rounding reasoning transfers to a different concrete accounting system before the capability is treated as broadly generalized.


## 40. Historical-style discovery milestone — cross-contract economic conservation

The next discovery-validation step deliberately began with a mechanism outside the existing extractor set. A three-contract asset/strategy/vault regression was first run with the prior reasoning surfaces only, and CYDRA produced no hypothesis. This negative result is preserved as the rule-set gap that justified the new capability.

The new class-neutral surface reasons across a contract boundary: one contract reports an asset amount, another contract delivers the underlying assets, and the receiving system adds the reported amount to internal accounting. CYDRA forms the system invariant that internal accounting must not increase by more than assets actually delivered across the boundary.

The discriminating experiment triggers the synchronization, then compares the receiving vault's internal accounted assets with the actual asset balance held by the vault.

Successful Benchmark 015 evidence:
- prior extractors alone: no hypothesis;
- new blind cross-contract economic surface: one hypothesis;
- vulnerable execution: FAIL because the strategy reports 100 while delivering 90 and the vault records 200 against 190 actual assets;
- patched execution: PASS because the strategy reports the delivered 90 and accounting remains backed;
- canonical causal verification: VERIFIED;
- finding gate: READY.

This benchmark establishes all three requested discovery dimensions together:
1. cross-contract accounting violation;
2. economic invariant violation; and
3. a mechanism initially unrecognized by CYDRA's existing extractors.

The fixture is an extracted causal regression rather than a claim that this exact code existed in a named production protocol. Public incident research shows that cross-scope accounting isolation is a real failure mode in shared DeFi systems; for example, the May 2024 Predy Finance incident involved cross-pair liquidity theft caused by accounting scope and post-callback validation failures. The public analysis reports that funds belonging to other pairs could be moved during a callback while an aggregate balance check still appeared healthy. This source is post-run contextual validation, not an input to CYDRA's blind hypothesis generation.

This milestone is stronger than merely adding another detector: the project explicitly measured an extractor blind spot, generalized the reasoning at the system/economic level, executed a vulnerable/patched differential, and promoted the causal result through the normal finding gate. The next step is to transfer this reasoning to a genuinely unfamiliar historical target rather than treating Benchmark 015 itself as proof of universal cross-contract coverage.

## 41. Historical backtest milestone — cross-contract balance-delta attribution

The next unfamiliar historical investigation moved beyond the existing inbound-transfer accounting rule. Olympus DAO's historical treasury repayment path already measured the receiving balance delta correctly, but the delta itself could be contaminated by an unrelated cross-contract inflow occurring during the external token transfer.

The new class-neutral reasoning surface recognizes the broader pattern: a state-changing function snapshots an asset balance, performs an external token transfer, derives a balance delta, and uses that delta to reduce caller-specific accounting without bounding the reduction by the caller-requested transfer. The invariant is that unrelated assets delivered during the external call must not be attributed to the caller's payment.

The historical target is the Olympus DAO contest repository at commit `549b96bcf8b97807738572605f6b1e26b33ef411`, specifically `src/modules/TRSRY.sol`. CYDRA receives only the historical source during hypothesis generation. The public Code4rena finding is kept as post-run contextual verification rather than blind guidance.

Benchmark 016 proved all of the following in CI:
- legacy reasoning surfaces alone do not produce the cross-contract attribution hypothesis;
- the new surface independently extracts `repayLoan` and forms the attribution invariant;
- the discriminating experiment requests a 100-unit repayment while a callback causes an unrelated 50-unit inflow;
- the vulnerable causal regression reduces debt by the full 150-unit balance delta;
- the patched counterpart bounds the reduction to the requested 100 units;
- canonical causal verification reaches VERIFIED; and
- the finding gate reaches READY.

The dedicated Benchmark 016 workflow completed successfully after the generic execution harness was corrected to use a non-underflowing 200-unit debt baseline. The final vulnerable execution was measurable and FAIL; the patched execution was measurable and PASS.

This is deliberately different from Benchmark 013. Benchmark 013 asks whether the receiver measures the actual balance delta at all. Benchmark 016 asks whether a measured delta can be safely attributed to the caller when another contract can change the same balance during the external call.

The benchmark fixture is an extracted causal regression from the real historical Olympus source, not a claim that the fixture itself was the production deployment. The external Code4rena report documents M-23 as a cross-contract reentrancy/accounting issue in `repayLoan` and records the confirmed minimal remediation as bounding `received` by `amount_`. This external material is verification after the blind run, not an input to hypothesis generation.

The next step after this benchmark is to use the learned attribution capability on another unfamiliar target and determine whether the reasoning generalizes without relying on Olympus-specific names or token-hook assumptions.


## 42. Solidity maturity gate before ecosystem expansion

CYDRA must not move to another programming language or smart-contract ecosystem merely because that ecosystem is strategically interesting.

The immediate priority is to determine whether the Solidity/EVM reasoning stack is genuinely capable of taking an unfamiliar authorized Solidity project and driving it through the complete research loop end to end:

**Target discovery/environment → system understanding → invariant discovery → hypothesis generation → discriminating experiment → execution → evidence → causal verification → reproducible finding.**

“Solidified” does not mean that every Solidity vulnerability class is implemented. It means the architecture and reasoning loop have demonstrated meaningful generalization across unfamiliar projects and mechanisms rather than only extracted benchmark fixtures.

Before declaring Solidity sufficiently mature, CYDRA should seek repeated blind end-to-end results on genuinely unfamiliar historical or authorized Solidity targets with materially different system structures and failure mechanisms. The tests should include cases where existing extractors do not immediately recognize the mechanism.

The maturity decision must be evidence-driven. Passing CI, increasing benchmark count, or adding more named detectors is not sufficient.

Evidence supporting the Solidity maturity gate should include, where practical:
- successful blind findings on unfamiliar targets;
- successful transfer of capabilities across different concrete mechanisms;
- meaningful system-model construction on projects CYDRA did not previously know;
- ability to recover from extraction/modeling/execution failures without target-specific hardcoding;
- negative controls and patched counterparts where available;
- reproducible causal findings;
- documented misses showing what remains outside the current generalization envelope.

Until this gate is satisfied, Solidity/EVM remains the primary development frontier.

## 43. Future cross-ecosystem direction — Solana/Rust

Solana/Rust is a planned future expansion, but it is explicitly deferred until the Solidity maturity gate provides sufficient evidence.

The goal is not to create a second collection of language-specific vulnerability detectors. CYDRA should preserve one reasoning core and add ecosystem-specific system-model/evidence adapters.

The future architecture is:

**CYDRA reasoning core → ecosystem adapter → system/evidence model → invariant/hypothesis/experiment reasoning → causal verification → finding**

The common reasoning abstractions should include, where the target supports them:
- authorization and authority boundaries;
- asset/economic conservation;
- state transitions and lifecycle;
- temporal/call-order constraints;
- cross-component trust;
- callback/reentrancy-like state exposure;
- accounting and attribution;
- identity and authority relationships.

The Solana/Rust adapter must model the actual semantics of the ecosystem rather than translating Solidity concepts mechanically. Important Solana-specific structures include programs, instructions, accounts, account ownership, signers, PDAs, account constraints, CPIs, and program-derived authority.

Historical Solana/Rust vulnerabilities may be used as blind learning targets under the same anti-overfitting doctrine. A known historical answer must remain hidden from CYDRA during hypothesis generation.

The first Solana/Rust milestone should be one demonstrated blind end-to-end finding on an unfamiliar historical or authorized target. Expansion should then follow the same:

**Guided → Diagnose → Fix → Guided Retest → Blind → Diagnose → Fix → Blind Retest → New Target**

cycle.

This section is a roadmap, not permission to begin speculative Solana infrastructure while Solidity generalization remains unproven.

## 44. GitHub-native research execution

GitHub Actions is the preferred persistent execution environment for CYDRA's repeatable research and backtesting workloads.

The phone/chat session is a control and reasoning interface; the repository and CI are the durable execution surface. A local development environment is not required for every investigation.

A CI research run should be able to:
1. identify the exact target/version;
2. load and validate the research contract;
3. enforce authorization, scope, permitted environment, and exclusions;
4. establish the declared and observed toolchain;
5. build the system model;
6. generate and rank hypotheses;
7. select and execute experiments within the authorized environment;
8. preserve raw evidence and provenance;
9. perform causal verification and adversarial review;
10. emit a machine-readable research result and artifacts.

CI must remain fail-closed around authorization and scope. CYDRA must not infer permission from technical reachability.

The Project Bible should treat a research contract as the machine-readable boundary for a campaign. At minimum it should represent:
- target repository, deployed program/contract, or exact target identifier;
- exact commit/version where applicable;
- authorization basis;
- included scope;
- excluded scope;
- permitted environments and prohibited actions;
- required proof/PoC constraints;
- competition start/end or program timing where applicable;
- research budget/time limits;
- toolchain/environment requirements;
- output/submission constraints.

For live competitions or bug-bounty programs, the research contract must be created from the current program rules and scope. Rules are interpreted before experiments begin, and human review remains responsible for confirming that the campaign is authorized.

ChatGPT may act as the on-demand research interpreter/controller: it can inspect current program rules when asked, translate them into a research contract, interpret CI evidence, diagnose failures, and choose the next research question. It is not assumed to be a permanently running daemon inside GitHub Actions.

GitHub Actions may provide scheduled or manually dispatched execution, but persistent automation does not remove the authorization, scope, human-review, or finding-gate requirements.

The preferred operational loop is:

**Research rules/scope → Research Contract → CYDRA CI → Evidence/Result artifacts → ChatGPT interpretation → next authorized investigation**

A CI run that merely reports “no finding” must not be treated as proof that the target is secure. The result must distinguish no candidate, insufficient evidence, execution/model failure, rejected hypothesis, and confirmed finding.

## 45. Current priority decision

The current priority is **not** Solana/Rust implementation.

The current priority is to prove whether CYDRA can pick up unfamiliar Solidity projects and repeatedly complete the full reasoning loop to real findings without being told the historical answer.

Therefore the next work should be selected from the next unfamiliar Solidity investigation:

**Backtest unfamiliar target → observe failure or finding → diagnose the exact blocker → implement only the demonstrated general capability → retest → blind → record evidence in the Project Bible → repeat.**

Do not add speculative Solidity architecture simply to reach a larger feature list. Do not move to another ecosystem merely because the current benchmark suite is large.

The transition to Solana/Rust becomes justified only after the evidence says the Solidity core is sufficiently generalized, or after a deliberate Project Bible decision changes this priority.

The success criterion remains practical: CYDRA should become capable of taking an unfamiliar authorized Solidity project and doing useful end-to-end security research rather than merely recognizing known patterns.

### Current CI execution state — 2026-09-20

The canonical `main` branch now contains `.github/workflows/cydra-solidity-research.yml`.

This workflow provides the durable GitHub-native Solidity research loop:
- runs on pushes to `main`;
- supports manual `workflow_dispatch`;
- runs on a daily UTC schedule;
- serializes research runs with concurrency control;
- installs the CYDRA package, pytest, and Foundry on the GitHub-hosted runner;
- runs the full Python regression suite;
- reruns the verified unfamiliar-target Olympus cross-contract attribution backtest;
- uploads backtest artifacts for later interpretation.

The workflow is an execution surface, not evidence that arbitrary targets are secure. Its historical backtest is a regression anchor for the already demonstrated finding capability.

The Solidity maturity gate remains open. The next evidence must come from additional genuinely unfamiliar targets and from reducing the gap between benchmark-specific execution harnesses and generic target execution. A green regression run therefore means **the demonstrated capability still works**, not **Solidity research is complete**.

## 46. Unfamiliar-target execution campaign — initializer generalization

The first post-maturity-gate execution campaign now deliberately targets a materially unfamiliar Solidity project rather than another CYDRA fixture.

The campaign target is the historical Stader Labs contest repository at commit `7566b5a35f32ebd55d3578b8bd05c038feb7d9cc`, with `contracts/VaultProxy.sol` as the initial source surface. The historical finding is not supplied to CYDRA during hypothesis generation.

This campaign exposed a concrete generalization gap before execution: CYDRA recognized `initialize` and `init`, but not the equivalent Solidity entrypoint spelling `initialise`. It also had an execution-input blind spot when a nonzero-address precondition was expressed through the common `checkNonZeroAddress(parameter)` helper rather than a direct comparison.

The demonstrated repairs were kept class-neutral:
- initialization reasoning recognizes `initialize`, `initialise`, and `init` without naming a target;
- the initialization renderer preserves the discovered function identity instead of hard-coding `initialize`;
- an unclassified initializer receives a generic arbitrary-caller mutation probe that treats a revert as safe execution rather than a finding;
- initializer input hardening recognizes the common nonzero-address helper form in addition to direct zero-address predicates;
- regressions cover both the spelling variation and helper-based input constraint.

The canonical CI research loop now executes this unfamiliar historical target after the existing Olympus regression and preserves the resulting artifacts.

The result of this campaign must be recorded only after the blind execution artifacts are inspected. A generated hypothesis or measured execution is not itself a confirmed finding. The finding gate still requires causal evidence and reproducibility.

This campaign is evidence for the maturity gate only if CYDRA independently produces and validates the relevant security conclusion without historical-answer leakage. A failure is equally valuable when it identifies the next demonstrated generalization blocker.


### 47. Unfamiliar initializer execution — adversarial dependency probing

The Stader campaign exposed a second execution-layer generalization gap after lifecycle discovery was repaired.

A guarded address input cannot always be tested with an arbitrary nonzero EOA. If the target subsequently calls a method on that address, the EOA has no code and the experiment may revert before the hypothesized state transition is observable. That is an execution-input artifact, not evidence that the hypothesis is false.

The generic initialization surface therefore now:
- recognizes the guarded address as a dependency boundary;
- deploys a minimal CydraInitializerDependencyProbe with a fallback returning a valid static word;
- substitutes the deployed probe for the conservative zero-address replacement when the target requires a nonzero address;
- keeps the probe target-agnostic rather than naming Stader, getAdmin, or the historical exploit;
- records successful state mutation as the security assertion failure for an arbitrary-caller lifecycle hypothesis;
- treats revert/no-execution as non-confirmation;
- binds storage-access observation to the renderer-selected target variable rather than a hard-coded target name.

This is an important distinction in the maturity gate:

**Input validity is not the same as environmental validity.**

An experiment must provide enough adversarial environment for the target's own mechanism to execute, while remaining class-neutral and without importing the historical answer.

### 48. Research-loop CI validation

The canonical Solidity research workflow now also runs for pull requests in addition to main pushes, manual dispatch, and the daily schedule. This makes changes to the blind research machinery subject to the same durable regression/research path before merge.

A workflow being configured is not equivalent to a successful run. CI status and research artifacts must be inspected before a campaign result is counted as evidence.


## 49. Unfamiliar initializer dependency probing — runner validation checkpoint

The Stader initializer campaign exposed one additional execution-layer defect after the target-agnostic dependency probe was added: the generated-test substitution regex for replacing the conservative zero-address placeholder with the local dependency probe was over-escaped. The reasoning capability itself was correct, but the renderer could not reliably materialize the intended input.

The repair corrected the substitution patterns without adding any Stader-specific condition.

This is a useful distinction for the maturity gate:

**A generalized hypothesis can still fail at experiment materialization.**

The campaign therefore treats generation correctness as part of the causal research path:

**Hypothesis → planned input → rendered experiment → executable target path → observed state change → causal conclusion.**

A renderer failure is a pipeline/generalization failure, not evidence against the hypothesis and never a finding.

## 50. Research CI must execute the triggering revision

The Solidity research workflow previously declared a pull-request trigger but explicitly checked out `main`. That meant a pull-request validation run could execute the already-merged baseline instead of the proposed research changes.

The workflow now checks out `github.sha`, so push, manual, scheduled, and pull-request executions test the revision that triggered the run.

This is required for research evidence provenance: a reported green regression or backtest artifact must correspond to the exact CYDRA source revision being evaluated.

The available GitHub connector currently does not expose the workflow-run listing needed to inspect the resulting Actions logs/artifacts directly. Therefore a configured workflow is not counted as an observed research result until its execution artifacts can be inspected.

