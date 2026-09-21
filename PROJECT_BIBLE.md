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


## 51. Unfamiliar Stader initializer — first blind end-to-end security result

The Stader unfamiliar-target campaign has now completed the generic initialization reasoning and execution path on the pinned VaultProxy.sol revision 7566b5a35f32ebd55d3578b8bd05c038feb7d9cc.

The important result is a blind security-relevant state-transition observation, not merely a generated hypothesis:

- compiler-backed semantic evidence succeeded;
- CYDRA independently generated H-INIT-initialise from the unfamiliar target;
- the experiment was rendered and executed by Foundry;
- an arbitrary caller successfully reached initialise;
- the generic storage-access assertion observed 6 target storage writes;
- the execution therefore failed the invariant that an arbitrary caller must not be able to claim initialization state;
- the canonical initialization classifier promoted the hypothesis to confirmed;
- the same CI research run was rerun successfully, reproducing the result.

The campaign also exposed and repaired three generic blockers before reaching this result:
1. target-project npm dependencies were absent from the temporary checkout;
2. the generic fallback initializer renderer emitted invalid try ...; { Solidity;
3. the runtime classifier did not recognize the generic initializer-mutation assertion emitted by the renderer.

None of these repairs add Stader-specific names, selectors, exploit sequences, or historical answers.

The current evidence proves a real causal initialization-state violation on the historical target. It does not yet claim the complete historical impact or declare the final finding gate READY. The next step is adversarial causal verification of the security/economic consequence using the target's own dependency boundary, followed by an independent reproduction. If that impact cannot be demonstrated generically, the result remains a confirmed invariant violation rather than a fully promoted finding.

This milestone is stronger evidence for the Solidity maturity gate because the hypothesis was generated on an unfamiliar project and the experiment was materialized and executed without historical-answer leakage. It is not evidence that Solidity generalization is complete.

The canonical research artifacts for the successful run must remain the provenance source for this milestone.
 

Causal verification record:
- blind hypothesis: `H-INIT-initialise`;
- blind experiment: `X-H-INIT-initialise`;
- compiler semantic evidence: `initialise` writes `owner`;
- blind execution: one Foundry test, one failure, six target storage writes;
- attacker-controlled dependency behavior: the generated probe returns the attacker address from the initializer's `getAdmin()` dependency;
- target code causal chain: `initialise` → `staderConfig.getAdmin()` → `owner`;
- reproducibility: the same result was reproduced in CI on the PR run and again on merged `main` run #35;
- finding gate: **READY** for the bounded initialization/privilege-takeover claim.

The public historical Stader finding is external corroboration discovered only after the blind campaign; it is not part of CYDRA's blind evidence or hypothesis-generation context.

## 52. Unfamiliar Olas transfer-accounting — blind end-to-end finding

The Olas historical campaign is the next unfamiliar-project generalization result after the Stader initializer and Olympus cross-contract campaigns. The target was the historical Olas repository at commit `3ce502ec8b475885b90668e617f3983cea3ae29f`, with `registries/contracts/staking/StakingToken.sol` as the source surface. The historical answer was kept out of hypothesis generation.

The campaign exposed and repaired only demonstrated generic blockers:
- inherited accounting state (`balance` and `availableRewards`) was absent from the lightweight target model, so the reasoning surface was generalized to recover a local-alias → state-addition → state-assignment flow directly from observed source dataflow;
- the execution gate checked `transferFrom` case-sensitively and therefore missed `safeTransferFrom`; the gate now recognizes both generic inbound transfer forms;
- the campaign runner duplicated the already-built-in transfer-accounting reasoning surface when explicitly injecting it, so the blind harness now uses the canonical pipeline once;
- the target's unrelated historical test fixtures had optional Gnosis Safe dependencies, so the causal regression isolates the production path from unrelated target tests;
- the injected causal test uses an ABI-compatible local tuple and target-agnostic initialization dependencies rather than relying on the target's global struct declaration.

The resulting blind chain completed:

**Target → System Model → Invariant → Blind Hypothesis → Experiment → Vulnerable Execution → Patched Execution → Causal Verification → Finding Gate**

Observed result:
- blind hypothesis: `H-TRANSFER-ACCOUNTING-deposit`;
- invariant: internal credit for an inbound token transfer must equal the actual token balance delta received, not merely the requested amount;
- experiment: `X-H-TRANSFER-ACCOUNTING-deposit`, using a 100-unit deposit boundary;
- vulnerable execution: 1 Foundry test executed and failed the accounting assertion because the contract credited the requested 100 while the fee-on-transfer test token delivered 90;
- patched execution: 1 Foundry test executed and passed after the patched target bounded the credited amount to the actual received balance delta;
- causal verification: `VERIFIED`, chain `causal:olas-transfer-accounting-differential`;
- finding gate: **READY**;
- historical public reporting was not used during hypothesis generation and is post-run corroboration only.

This is evidence of a blind, reproducible transfer-accounting capability on an unfamiliar Solidity project and materially strengthens the Solidity maturity gate. It does not by itself close the maturity gate; additional unfamiliar targets and materially different mechanisms remain required.


## 53. Unfamiliar Morph L2 initializer — blind causal finding with independent reproduction

The Morph L2 historical campaign has now completed the full blind initialization-finding path on the pinned `morph-l2/morph` revision `aa35ed6d1d0bb1e0a38f04dcfb9c5b3203f90604`, using `contracts/contracts/l2/staking/L2Staking.sol` as the source surface. The historical answer was not supplied during hypothesis generation.

The campaign exposed and repaired demonstrated generic blockers rather than adding Morph-specific knowledge:
- constant/immutable declarations were incorrectly entering mutable lifecycle-state modeling, so a timestamp/epoch constant could select the wrong double-call lifecycle shape instead of the arbitrary-caller initialization probe;
- generic initializer inputs used zero addresses and zero scalars, which could fail ordinary target preconditions before the hypothesized transition was observable;
- the generic initializer probe needed to preserve typed ABI encoding while safely treating an ordinary revert as non-confirmation, so the fallback now uses a typed `try/catch` call and observes target storage writes;
- timestamp/epoch-constrained initializer parameters now receive a generic future, epoch-aligned value when the target source exposes the corresponding `block.timestamp` modulo guard;
- the finding gate now requires an independent fresh vulnerable execution and patched control reproduction after the first causal differential succeeds.

The resulting blind chain completed:

**Target → System Model → Invariant → Blind Hypothesis → Experiment → Vulnerable Execution → Patched Control → Causal Verification → Independent Reproduction → Finding Gate**

Observed result from CI research run #109:
- blind hypothesis: `H-INIT-initialize`;
- invariant: `INV-INIT-001` — initialization must not allow an arbitrary caller to claim privileged initialization state after deployment;
- compiler-backed semantic evidence: 366 records;
- vulnerable blind execution: one Foundry test executed and failed because the arbitrary initializer call mutated 2 target storage slots;
- patched control: one Foundry test executed and passed after a synthetic constructor `_disableInitializers()` control was applied;
- causal verification: `VERIFIED`, chain `causal:initialization-lock-differential`;
- independent reproduction: vulnerable execution failed with the same 2-storage-write assertion and the reproduced patched control passed;
- reproduction verification: `VERIFIED`, chain `reproduction:initialization-lock-differential`;
- finding gate: **READY**.

The exact target revision and all raw execution/provenance evidence are preserved in the CI research artifact. The finding is bounded to the demonstrated initialization-state control failure; the artifact does not claim impact beyond what the executed invariant and causal differential establish.

This milestone is materially stronger evidence for Solidity generalization because the target was unfamiliar, the hypothesis was generated blind, the execution required generic input/environment handling, the causal control was synthetic rather than a supplied historical patch, and the result survived an independent reproduction. It does not close the Solidity maturity gate; another unfamiliar target and a materially different mechanism are still required.

## 54. Unfamiliar Alchemix authorization — blind causal finding with independent reproduction

The real historical Alchemix authorization campaign has now completed the full blind authorization path on the pinned Alchemix Protocol revision `0261dd5a23c63aaa354d56f506701a6fa79cfe1f`, using `contracts/AlchemistEth.sol` as the source surface. The historical answer was not supplied during hypothesis generation.

The campaign required and demonstrated several generic execution capabilities rather than a target-specific Alchemix detector:
- authorization reasoning identified `setWhitelist` as an externally callable state-mutating administrative surface with no observed authorization modifier;
- the blind runner inferred an authorization control from observed modifier semantics and selected `onlyGov` from the target's sibling-function usage, rather than hard-coding the modifier name;
- the causal control is applied to the same isolated Foundry source tree that the generated blind test imports, preserving the vulnerable-versus-control differential;
- the generated authorization assertion renderer is handled generically for both success-gated and revert-gated authorization assertions;
- the finding gate requires both a first causal differential and a fresh vulnerable/patched reproduction before `READY`;
- the CI workflow was corrected to execute the exact command arguments and to preserve the machine-readable result artifact.

The resulting blind chain completed:

**Target → System Model → Invariant → Blind Hypothesis → Experiment → Vulnerable Execution → Causal Control → Causal Verification → Independent Reproduction → Finding Gate**

Observed result from the real Alchemix CI campaign (run #301):
- blind hypothesis: `H-AUTH-setWhitelist`;
- invariant: `INV-AUTH-001` — an arbitrary external caller must not mutate privileged authorization/configuration state;
- blind execution: one Foundry test executed and failed because an unauthorized caller successfully invoked the modeled administrative operation;
- blind classification: `confirmed`;
- inferred causal authorization control: `onlyGov`;
- patched execution: one Foundry test executed and passed after the inferred authorization modifier was applied;
- causal verification: `VERIFIED`, chain `causal:authorization-modifier-differential`;
- independent vulnerable reproduction: one fresh Foundry test executed and failed with the same authorization assertion;
- independent patched reproduction: one fresh Foundry test executed and passed;
- reproduction verification: `VERIFIED`, chain `reproduction:authorization-modifier-differential`;
- finding gate: **READY**.

The machine-readable CI artifact records the exact historical target, hypothesis, experiment, execution results, inferred control, causal verification, reproduction verification, and `finding_gate: READY`. The result is bounded to the demonstrated missing-authorization state-transition claim and does not infer impact beyond the executed invariant.

This milestone materially strengthens the Solidity generalization gate because it is a genuinely unfamiliar target and a materially different mechanism from the earlier Morph/Olas initialization and transfer-accounting findings. The hypothesis was generated from the target's observed model, the causal control was inferred from sibling authorization semantics, and the result survived independent vulnerable/patched reproduction. It still does not mean arbitrary Solidity research is solved; the next priority remains another unfamiliar mechanism and continued adversarial generalization.

## 55. Unfamiliar Blueberry cross-contract read-only state — blind causal finding with independent reproduction

A third materially different unfamiliar-target mechanism has now completed the full causal/reproduction finding gate: transient cross-contract state observed through a public state-derived view during an external callback.

Target:
- repository: `https://github.com/sherlock-audit/2023-04-blueberry.git`;
- pinned revision: `1f123ee62b0479637557ea320493249059db6981`;
- source: `blueberry-core/contracts/oracle/BalancerPairOracle.sol`;
- target function discovered blind: `getPrice`.

The new reasoning surface is class-neutral. It looks for a public/external view that combines state-derived reads from multiple external components (for example a balance/reserve vector with a supply/rate/invariant) and lacks an observed context guard. It then forms the hypothesis that a callback can observe one component while it is in an intermediate state, producing a value that differs from the settled observation. No Blueberry, Balancer, Curve, pool, or historical-answer condition is encoded in the reasoning rule.

The blind campaign completed:

**Target → System Model → Cross-Contract Invariant → Blind Hypothesis → Experiment → Vulnerable Execution → Synthetic Causal Control → Causal Verification → Independent Reproduction → Finding Gate**

Observed CI result from the Blueberry backtest:
- blind hypothesis: `H-READONLY-XCONTRACT-getPrice`;
- invariant: `INV-READONLY-XCONTRACT-getPrice`;
- blind execution: one Foundry test executed and failed because the callback-time `getPrice` observation differed from the settled-state expectation;
- patched causal control: one Foundry test executed and the synthetic external-context guard reverted the callback-time observation;
- causal verification: **VERIFIED**;
- independent vulnerable reproduction: one fresh Foundry test executed and failed with the same transient-state assertion;
- independent patched reproduction: one fresh Foundry test executed and the synthetic guard prevented the observation;
- reproduction verification: **VERIFIED**;
- finding gate: **READY**.

The causal control is deliberately described as **synthetic**, not as a claim that this exact guard is the historical production remediation. Its purpose is to demonstrate causality: blocking observation while the external component is in the intermediate context removes the observed transient value. The result therefore supports the bounded claim that the target's state-derived view can return a materially different value when queried during an external state transition. Impact beyond that invariant is not asserted.

The CI artifact for run #17 records:
- target revision and source path;
- blind hypothesis and invariant;
- executable vulnerable differential;
- patched differential;
- causal verification;
- independent reproduction;
- independent patched reproduction;
- `finding_gate: READY`.

This milestone materially expands the Solidity generalization evidence beyond authorization, initialization, transfer/accounting, rounding, and state-transition parity. It is especially important because the mechanism is **cross-contract**: the vulnerable observation is not merely a local state write/read sequence, but a trust-boundary problem involving externally sourced state observed during another component's transition.

The Solidity maturity gate remains open. The next investigation should seek another unfamiliar target and mechanism, preferably one where the existing reasoning surfaces are initially insufficient, while continuing to reject unsupported impact and target-specific hardcoding.


## 56. Unfamiliar TitlesGraph storage-reference persistence — blind causal finding with independent reproduction

A fourth materially different unfamiliar-target mechanism has now completed the full causal/reproduction finding gate: a state-changing helper copies a persistent storage element into a memory return variable and mutates the copy, so the apparent state transition does not persist.

Target:
- repository: https://github.com/sherlock-audit/2024-04-titles.git;
- pinned revision: d7f60952df22da00b772db5d3a8272a988546089;
- source: wallflower-contract-v2/src/graph/TitlesGraph.sol;
- target function discovered blind: acknowledgeEdge;
- related helper discovered blind: _setAcknowledged.

The new reasoning surface is class-neutral. It identifies the topology persistent collection element → memory alias → member mutation → externally reachable caller, then proposes the invariant that a successful state-changing operation must persist the modeled state transition across the transaction boundary. It does not encode TitlesGraph, acknowledgeEdge, _setAcknowledged, acknowledged, or the historical answer.

The blind campaign completed:

**Target → System Model → Persistence Invariant → Blind Hypothesis → Experiment → Vulnerable Execution → Synthetic Causal Control → Causal Verification → Independent Reproduction → Finding Gate**

Observed CI result from the unfamiliar storage-persistence backtest (run #17):
- blind hypothesis: H-STORAGE-PERSISTENCE-acknowledgeEdge;
- invariant: INV-STORAGE-PERSISTENCE-acknowledgeEdge;
- blind execution: one Foundry test executed and failed because the successful acknowledgment did not persist to the target's stored edge;
- patched causal control: the isolated target source was changed only at the causal reference boundary from Edge memory to Edge storage;
- patched execution: one Foundry test executed and passed;
- causal verification: VERIFIED, chain causal:storage-persistence-differential;
- independent vulnerable reproduction: one fresh Foundry test executed and failed with the same persistence assertion;
- independent patched reproduction: one fresh Foundry test executed and passed;
- reproduction verification: VERIFIED;
- finding gate: READY.

The causal control is explicitly a synthetic control, not a claim that this exact source edit is the historical production remediation. Its purpose is to isolate the causal variable: changing the reference location from memory to storage makes the observed state transition persist.

The final machine-readable artifact records:
- target repository, pinned revision, and source;
- blind hypothesis and invariant;
- vulnerable execution: executed=true, tests_run=1, tests_failed=1;
- patched execution: executed=true, tests_run=1, tests_failed=0;
- causal verification: VERIFIED;
- independent vulnerable reproduction: FAIL;
- independent patched reproduction: PASS;
- reproduction_verified: true;
- finding_gate: READY.

This milestone materially expands the Solidity generalization evidence into storage-reference semantics / state persistence, a mechanism that the previous reasoning surfaces did not recognize. The result is bounded to the demonstrated persistence violation: acknowledgeEdge can return successfully while the intended acknowledgment state remains unchanged. No broader impact is asserted without additional evidence.

The Solidity maturity gate remains open. The next investigation should continue toward another unfamiliar mechanism, preferably one that initially breaks the current reasoning surfaces, while preserving the same blind, causal, independent-reproduction, and fail-closed finding gate.


## 57. Unfamiliar Tapioca double-debit fund-flow — blind causal finding with independent reproduction

A fifth materially different unfamiliar-target mechanism has completed the full causal/reproduction finding gate: a leveraged purchase flow acquires the economic value into the market through the external executor path and then invokes a collateral-accounting path that pulls the same modeled collateral amount from the caller again, while only one collateral accounting position is recorded.

Target:
- repository: https://github.com/sherlock-audit/2024-02-tapioca.git;
- target source: Tapioca-bar/contracts/markets/bigBang/BBLeverage.sol;
- target function discovered blind: buyCollateral;
- related inherited mechanisms: BBLendingCommon._addCollateral and BBCommon._addTokens.

The new reasoning surface is class-neutral. It looks for the topology external value acquisition → returned value/accounting → subsequent caller-funded pull, then proposes the invariant that one economic amount must not be charged twice while only one persistent accounting position is recorded. It does not encode Tapioca, buyCollateral, the historical issue, or its expected answer.

The blind campaign completed:

**Target → System Model → Fund-Flow Invariant → Blind Hypothesis → Experiment → Vulnerable Execution → Synthetic Causal Control → Causal Verification → Independent Reproduction → Finding Gate**

Observed CI result from the unfamiliar double-debit backtest (run #11):
- blind hypothesis: H-DOUBLE-DEBIT-buyCollateral;
- invariant: INV-DOUBLE-DEBIT-buyCollateral;
- blind execution: one Foundry test executed and failed because the same modeled economic amount was charged twice;
- patched causal control: the second caller-funded pull was disabled while retaining the acquired collateral and accounting position;
- patched execution: one Foundry test executed and passed;
- causal verification: VERIFIED, chain causal:double-debit-differential;
- independent vulnerable reproduction: one fresh Foundry test executed and failed with the same double-charge assertion;
- independent patched reproduction: one fresh Foundry test executed and passed;
- reproduction verification: VERIFIED;
- finding gate: READY.

The benchmark binds its hypothesis to the real Tapioca source by requiring the observed buyCollateral, _borrow, leverageExecutor.getCollateral, and _addCollateral topology, plus the inherited _addTokens implementation in BBCommon. The executable Foundry harness is source-derived and isolates that fund-flow causal variable rather than claiming to compile the entire historical Tapioca dependency graph.

The causal control is explicitly synthetic, not a claim that this exact harness edit is the historical production remediation. Its purpose is to isolate whether the second caller-funded pull is the variable that creates the extra economic charge.

The final machine-readable CI artifact records:
- blind hypothesis and invariant;
- blind execution: executed=true, tests_run=1, tests_failed=1;
- patched execution: executed=true, tests_run=1, tests_failed=0;
- causal verification: VERIFIED;
- independent vulnerable reproduction: FAIL;
- independent patched reproduction: PASS;
- reproduction_verified: true;
- finding_gate: READY.

This milestone expands the Solidity generalization evidence into **fund-flow provenance / duplicate economic charging**, distinct from transfer accounting, storage persistence, authorization, initialization, and transient read-only state. The result is bounded to the demonstrated double-charge invariant; broader financial impact is not asserted without additional evidence.

The Solidity maturity gate remains open. The next investigation should continue against an unfamiliar mechanism that is not reducible to an already-covered surface, while preserving blind hypothesis generation, causal isolation, independent reproduction, provenance, uncertainty, and fail-closed finding gates.


## 58. Unfamiliar execution-domain signature replay — blind causal finding with independent reproduction

A sixth materially different mechanism has completed the canonical causal/reproduction gate as a **source-derived execution-domain differential**: a signature authorization whose digest does not bind the deployment or chain context can be accepted by a second deployment, while a domain-bound control rejects the same authorization.

Target-derived source:
- repository: https://github.com/sherlock-audit/2024-10-ethos-network.git;
- source path: ethos/packages/contracts/contracts/EthosAttestation.sol;
- blind target function: createAttestation;
- target-derived topology: createAttestation → digest helper → validateAndSaveSignature.

The reasoning surface is class-neutral. It identifies signature verification combined with a digest helper and checks whether the observed signed message binds execution-domain context such as chainid or address(this). It does not encode the historical issue or expected answer.

The executable differential uses an isolated source-derived control because the public audit repository's nested Ethos source revision is not independently checkout-able as a top-level repository ref. The target source is preserved in the benchmark as a source snapshot; therefore this milestone is **not** treated as equivalent to the pinned historical-source milestones.

Observed CI result (latest dedicated signature-replay run):
- blind hypothesis: H-SIGNATURE-REPLAY-createAttestation;
- invariant: INV-SIGNATURE-REPLAY-createAttestation;
- vulnerable execution: executed=true, tests_run=1, tests_failed=1;
- patched execution: executed=true, tests_run=1, tests_failed=0;
- causal verification: VERIFIED;
- independent vulnerable reproduction: FAIL;
- independent patched reproduction: PASS;
- reproduction verification: VERIFIED;
- finding gate: READY.

The initial harness mistake was caught by the differential itself: the first version asserted that vulnerable replay should succeed, causing both controls to PASS and the gate to remain UNRESOLVED. The harness was corrected so the security invariant is expressed as a failure condition on replay; the next run produced the required FAIL/PASS differential and VERIFIED causal chain.

The result demonstrates another generalizable reasoning/execution surface — **signature-domain binding / authorization replay** — distinct from authorization topology, initialization, transfer/accounting, rounding, transient cross-contract state, storage-reference persistence, and duplicate economic charging.

Important boundary: this milestone demonstrates that CYDRA can independently derive and causally verify the execution-domain invariant from the preserved target source. It does **not** claim a newly discovered production vulnerability in Ethos until CYDRA executes the actual target dependency graph or another independently reproducible target implementation with equivalent semantics.

The Solidity maturity gate remains open. The next cycle should prioritize an unfamiliar target that can be executed directly, so the same signature-domain reasoning can be tested without a source-snapshot boundary.


## 59. Unfamiliar single-use signed authorization — blind causal finding on a directly executable target

A seventh materially distinct mechanism has now completed the full causal/reproduction finding gate on an unfamiliar target whose **actual pinned repository and dependency graph were executed**: a valid signed claim can be submitted repeatedly because the claim path records a per-minter consumption marker but does not reject the already-consumed state before recording it again.

Target:
- repository: https://github.com/code-423n4/2024-08-phi.git;
- pinned revision: 2465e04364b759c721f1a0aebace69920411f8aa;
- source: src/PhiFactory.sol;
- blind target function: signatureClaim;
- related helper discovered from the target topology: _validateAndUpdateClaimState.

The new reasoning surface is class-neutral. It identifies a signed state-changing entry point, follows its claim-state helper, observes a persistent boolean/mapping consumption marker being written, and asks whether the same marker is checked and rejected before the write. It does not encode Phi, signatureClaim, artMinted, credMinted, or the historical answer.

The blind campaign completed:

**Target → System Model → Single-Use Authorization Invariant → Blind Hypothesis → Experiment → Actual Target Execution → Causal Control → Causal Verification → Independent Reproduction → Finding Gate**

Observed dedicated CI run #4 (run ID 35538206816, artifact ID 10613118546):
- blind hypothesis: H-SIGNATURE-REUSE-signatureClaim;
- invariant: INV-SIGNATURE-REUSE-signatureClaim;
- the blind hypothesis bound to the observed _validateAndUpdateClaimState consumption-marker topology;
- vulnerable execution: executed=true, tests_run=1, tests_failed=1; the exact same signed authorization was accepted twice;
- patched causal control: the target source was changed only to reject an already-consumed artMinted state with the target's existing AddressAlreadyMinted error;
- patched execution: executed=true, tests_run=1, tests_failed=0;
- causal verification: VERIFIED;
- independent vulnerable reproduction: FAIL;
- independent patched reproduction: PASS;
- reproduction verification: VERIFIED;
- finding gate: READY.

The executable test used the real Phi claim setup from the pinned repository, generated one valid signed claim, submitted that exact authorization twice, and required the second submission to be rejected. On the vulnerable source the second claim succeeded and the security assertion failed. On the patched control the second claim reverted and the test passed.

This milestone is stronger than Milestone 58 on target provenance: it does not use a preserved source snapshot or a synthetic standalone authorization fixture. CYDRA cloned the pinned Phi repository, initialized its dependencies, installed the repository's declared npm dependencies, compiled the real Solidity project, and executed the generated test against that dependency graph. The patched version is still a causal control, not a claim that the historical production remediation was exactly that edit.

The benchmark also caught and repaired two implementation blockers before reaching READY: the reasoning test initially lacked an explicit recover topology, and the target repository required npm-installed @prb/test dependencies for its existing test harness. The final run was green only after both were resolved.

This milestone expands the demonstrated Solidity reasoning surface into **single-use signed authorization / consumption-state enforcement**, distinct from execution-domain signature binding. It also demonstrates that CYDRA can connect cryptographic authorization evidence to persistent application state and then verify the resulting lifecycle invariant against a real unfamiliar project.

Boundary: the benchmark proves the demonstrated invariant violation in the pinned historical Phi source and its causal reproduction. It does not independently assign severity beyond the tested unauthorized repeated claim transition, and it does not generalize the result to all signature-based systems without evidence.

The Solidity maturity gate remains open. The next cycle should deliberately seek a materially different mechanism and unfamiliar target, while preserving direct execution, blind hypothesis generation, causal isolation, independent reproduction, provenance, uncertainty, and the fail-closed finding gate.
## 60. Unfamiliar epoch-boundary accounting — blind causal finding with independent reproduction

An eighth materially distinct Solidity mechanism has now completed the full causal/reproduction finding gate on an unfamiliar target whose **actual pinned repository and dependency graph were executed**: a reward/accounting transition can carry the rate from the epoch containing an unaligned checkpoint across the next epoch boundary because the segment end is calculated as the current position plus a full epoch rather than the next aligned epoch boundary.

Target:
- repository: https://github.com/code-423n4/2024-01-canto.git;
- pinned revision: 5e0d6f1f981993f83d0db862bcf1b2a49bb6ff50;
- source: src/LendingLedger.sol;
- blind target function: update_market;
- observed mechanism: BLOCK_EPOCH-aligned cantoPerBlock schedule combined with an unaligned market.lastRewardBlock and iterative reward accumulation.

The new reasoning surface derives the epoch-accounting invariant from the target source. It recognizes an epoch bucket derived from the current position, a next segment expressed as current position + BLOCK_EPOCH, and a bounded interval calculation. The implementation was generalized to preserve Solidity token boundaries and numeric separators and to recover directly from source text when the lightweight model does not expose a function. It does not encode the Canto historical answer.

The blind campaign completed:

**Target → System Model → Epoch Accounting Invariant → Blind Hypothesis → Experiment → Actual Target Execution → Causal Control → Causal Verification → Independent Reproduction → Finding Gate**

Observed dedicated CI run #11 (run ID 35539921742, artifact ID 10614910600):
- blind hypothesis: H-EPOCH-ACCOUNTING-update_market;
- invariant: INV-EPOCH-ACCOUNTING-update_market;
- vulnerable execution: executed=true, tests_run=1, tests_failed=1;
- vulnerable observation: starting at block 50,000 and updating through block 150,000 produced 100,000e18 accumulated CANTO-per-share instead of the piecewise 150,000e18 schedule implied by 50,000 blocks at 1e18/block followed by 50,000 blocks at 2e18/block;
- patched causal control: only the epoch segment-end expression was changed from i + BLOCK_EPOCH to the next aligned epoch boundary;
- patched execution: executed=true, tests_run=1, tests_failed=0;
- causal verification: VERIFIED;
- independent vulnerable reproduction: FAIL;
- independent patched reproduction: PASS;
- reproduction verification: VERIFIED;
- finding gate: READY.

The actual pinned Canto repository was cloned and executed with Foundry. The benchmark did not install or mutate an unrelated npm dependency graph. The generated Foundry harness configured two reward epochs, created an unaligned checkpoint, crossed the epoch boundary, and asserted the resulting accounting state. Four fresh target clones were used for vulnerable, patched, independent-vulnerable, and independent-patched executions.

The causal control is explicitly synthetic: it isolates the epoch-segment-end calculation as the causal variable and is not presented as the historical production remediation.

This milestone expands the demonstrated Solidity reasoning surface into **piecewise epoch-boundary accounting / temporal rate partitioning**, distinct from authorization, initialization, transfer/accounting, rounding, transient cross-contract state, storage-reference persistence, duplicate economic charging, signature-domain binding, and single-use signed authorization.

Boundary: this benchmark establishes the invariant violation and causal reproduction in the pinned historical Canto revision. It is evidence of CYDRA's ability to derive and verify this mechanism on a directly executable unfamiliar target; it is not by itself an open-ended proof that every temporal/accounting defect can be discovered.

The Solidity maturity gate remains open. The next cycle should deliberately seek another unfamiliar mechanism that is not reducible to the current reasoning surfaces, while preserving direct execution, blind hypothesis generation, causal isolation, independent reproduction, provenance, uncertainty, and the fail-closed finding gate.
## 61. Unfamiliar control-flow progress failure — blind causal finding with independent reproduction

A ninth materially distinct Solidity mechanism has now completed the full causal/reproduction finding gate on an unfamiliar target whose actual pinned repository and dependency graph were executed: a reachable continue branch in a gas-optimized loop bypasses the loop-counter update, so a previously processed element can prevent the loop from advancing and make the whole batch execution exhaust gas.

Target:
- repository: https://github.com/code-423n4/2023-09-venus.git;
- pinned revision: 23f5db740d8a794ac563ac32195b675c53042bb4;
- source: contracts/Tokens/Prime/Prime.sol;
- blind target function: updateScores;
- observed mechanism: a loop over users checks isScoreUpdated[nextScoreUpdateRoundId][user] and executes continue without advancing i.

The new reasoning surface derives a loop progress / termination invariant from source topology: every reachable iteration of a terminating loop must make progress toward its termination condition, and a continue branch must not bypass the loop-counter or termination-state update. The planner then asks for a discriminating execution containing an already-processed first element followed by a still-unprocessed element. It does not receive the historical finding as its answer.

The blind campaign completed:

Target -> System Model -> Loop Progress Invariant -> Blind Hypothesis -> Experiment -> Actual Target Execution -> Causal Control -> Causal Verification -> Independent Reproduction -> Finding Gate

Dedicated CI run #25 (run ID 35555875658, artifact ID 10620885446):
- blind hypothesis: H-CONTROL-FLOW-updateScores;
- invariant: INV-CONTROL-FLOW-updateScores;
- vulnerable execution: executed=true, tests_run=1, tests_failed=1;
- vulnerable observation: with the first supplied user already marked as processed and a second user still pending, updateScores failed to make progress and exhausted the bounded gas call;
- patched causal control: only the continue branch was changed to increment i before continuing;
- patched execution: executed=true, tests_run=1, tests_failed=0;
- causal verification: VERIFIED;
- independent vulnerable reproduction: FAIL;
- independent patched reproduction: PASS;
- reproduction verification: VERIFIED;
- finding gate: READY.

The target was executed through its real upgradeable ERC1967 proxy boundary. The pinned Venus repository was cloned at the historical revision, its declared npm dependency graph was installed, Foundry dependencies were initialized, and the generated test executed against the real target implementation. A minimal access-control contract was used only as an environmental dependency required to reach the target's externally callable setup; the vulnerable loop and its state transition remained the pinned target implementation.

This milestone demonstrates a materially different reasoning capability from the accounting, authorization, lifecycle, transfer, rounding, state-persistence, signature, and epoch-boundary surfaces: control-flow progress / termination reasoning. CYDRA derived the invariant from loop topology, selected an input that makes the problematic branch reachable, isolated the progress update as the causal variable, and reproduced the differential independently.

Boundary: this benchmark establishes the control-flow invariant violation and causal reproduction in the pinned historical Venus revision. It does not claim that every non-terminating-loop defect is discoverable by this single structural surface, and the synthetic patch is a causal control rather than a claim about the historical production remediation.

The Solidity maturity gate remains open. The demonstrated surface count is now nine materially distinct mechanisms, but the final gate still requires evidence that CYDRA can select and validate findings beyond its existing explicitly designed reasoning surfaces. The next campaign should therefore move toward a more open-ended blind target where the vulnerability class and specialized surface are not supplied in advance, while preserving direct execution, causal isolation, independent reproduction, provenance, uncertainty, and the fail-closed finding gate.



## Milestone 62 — First class-hidden open-ended blind discovery

Benchmark 022 completed the first true class-hidden blind campaign. CYDRA investigated a pinned unfamiliar Intuition AtomWallet target without being supplied a vulnerability class, target function, state surface, exploit sequence, or historical answer. It generated three candidate hypotheses and its class-neutral information-per-cost selector independently selected H-SIGNED-METADATA-_validateSignature. The selected experiment was executed against the real pinned repository and dependency graph. The vulnerable target accepted the same 65-byte ECDSA signature after only the 12-byte validity metadata suffix was changed, including after the original validity window had expired. A minimal causal control bound the validity metadata into the signed digest; vulnerable execution failed the security assertion and the patched control passed. Fresh independent vulnerable and patched clones reproduced the same split. Canonical causal verification reached verified, reproduction verification was true, and the finding gate reached READY.

This milestone is materially different from the prior specialized benchmarks because the benchmark selection boundary is class-hidden: the benchmark does not tell CYDRA what mechanism to look for. The benchmark harness retains the historical oracle only for evaluation and causal-control construction after CYDRA has selected and tested its own hypothesis.

**Maturity gate:** still open. This milestone establishes the first open-ended selection-and-verification result, but it is one bounded class-hidden campaign. Solidity maturity should close only after repeated open-ended unfamiliar-target campaigns demonstrate that CYDRA can choose and causally verify findings across materially different mechanisms without benchmark-provided vulnerability-class guidance.


## Milestone 64 — strict blind signature-reuse finding (Benchmark 025)
- Benchmark 025 reran the unfamiliar pinned Phi signature-reuse target through CYDRA's normal investigation pipeline rather than injecting the signature-reuse reasoning surface or custom experiment planner.
- Blind context supplied no vulnerability class, target function, state surface, reasoning-surface injection, or benchmark answer. The class-neutral selector independently selected H-SIGNATURE-REUSE-signatureClaim.
- The selected hypothesis was tested against the actual pinned Phi repository and dependency graph. Vulnerable execution FAIL demonstrated that the same signed authorization was accepted twice; the isolated patched control PASS rejected reuse.
- Canonical causal verification reached VERIFIED. Independent vulnerable reproduction FAIL and independent patched reproduction PASS; finding gate READY.
- The strict blind run completed successfully in CI, and the canonical Solidity research loop on the merged main commit also completed successfully.
- This strengthens the generalization evidence because the historical signature-reuse capability survived the normal blind orchestration boundary instead of being manually supplied by the benchmark harness.
- The Solidity maturity gate remains open. Benchmark 025 is a third consecutive open-ended/class-hidden causal success across signed metadata integrity, role-intent authorization, and signature-consumption mechanisms, but closure still requires further unfamiliar-target campaigns and evidence that CYDRA continues to discover findings without accumulating target-shaped detectors.

## Milestone 63 — class-hidden role-intent blind finding (Benchmark 023)
- Benchmark 023 exercised a stricter open-ended blind campaign against unfamiliar pinned Blackhole target contracts/SetterTopNPoolsStrategy.sol at revision 92fff849d3b266e609e6d63478c4164d9f608e91.
- CYDRA received only the pinned source target. The benchmark did not supply the vulnerability class, target function, exploit sequence, or expected answer.
- A new class-neutral reasoning surface, role-intent parity, identified a documented caller boundary (owner or AVM) that was narrower in enforcement (onlyExecutor). The blind selector selected H-INTENT-PARITY-setTopNPools as its only candidate.
- Real pinned target execution: vulnerable FAIL (owner caller rejected); causal control PASS after changing only the setter modifier to onlyOwnerOrExecutor; canonical causal verification VERIFIED.
- Independent vulnerable reproduction FAIL and independent patched reproduction PASS. Finding gate READY.
- Target execution used the actual pinned source and dependency versions, with an isolated Foundry harness to avoid unrelated compilation failures elsewhere in the historical repository.
- This is a reproduced historical benchmark finding, not a claim of a newly discovered production vulnerability.
- The Solidity maturity gate remains open: this adds another class-hidden blind success, but closure still requires repeated genuinely open-ended campaigns across materially different mechanisms without benchmark-specific detectors being introduced solely for the target.


## Milestone 65 — strict blind control-flow selection miss and pipeline exposure

Benchmark 026 was run as an adversarial strict-blind test against the pinned unfamiliar Venus Prime control-flow target. The benchmark supplied no vulnerability class, target function, state surface, reasoning-surface injection, custom planner, exploit sequence, or historical answer. The normal selector instead chose H-INIT-initialize/initialize, so the campaign failed before target execution.

This failure is retained as evidence rather than hidden or repaired by benchmark-specific ranking. Diagnosis showed that the demonstrated generic control-flow reasoning surface existed but was not part of the normal default reasoning surface set. The existing specialized control-flow benchmark was still green, proving the reasoning capability itself; the blind miss was therefore an orchestration/generalization boundary, not a failure of the control-flow detector.

PR #123 promoted the already demonstrated control-flow reasoning surface and its existing planner into the normal class-neutral pipeline. Existing full regression and the specialized control-flow backtest remained green, and the strict blind signature-reuse campaign also remained green after the change.

The strict blind control-flow campaign remains closed as a negative regression experiment. The important remaining blocker is broader research-loop hypothesis selection: after the normal pipeline exposes multiple valid hypotheses, CYDRA currently makes a one-shot score choice and does not yet execute a selected hypothesis, update its belief from the result, and then choose the next discriminating hypothesis. The next development work should address that generic evidence-driven loop rather than special-case control-flow or initialization.

The Solidity maturity gate remains open. This milestone is a deliberate negative result that identifies the next general capability needed for open-ended discovery.


## Milestone 66 — evidence-driven iterative blind finding

Benchmark 027 closed the generic research-loop gap identified by Benchmark 026.

Against the pinned unfamiliar Venus Prime target, CYDRA began with a strict blind investigation: no vulnerability class, target function, state surface, reasoning-surface injection, custom planner, exploit sequence, or historical answer. The normal selector first chose the initialization hypothesis. CYDRA executed that selected hypothesis; its measured result was non-confirming/unmeasurable rather than silently treated as success. The generic hypothesis-selection API then excluded that candidate and performed a second selection.

The second selection reached the independent control-flow hypothesis. CYDRA then executed the actual pinned target, applied an isolated causal control, and independently reproduced both vulnerable and patched behavior. Benchmark 027 completed with the causal differential verified and the finding gate READY.

The campaign also exposed and fixed a generic Solidity project-root/import-provenance issue affecting non-Foundry repositories. Repository root detection now recognizes Git/package-based project roots, and generated runtime interface imports preserve the already-resolved source provenance. Full Python regression remained green.

This is a materially stronger research-loop result than a one-shot benchmark: CYDRA did not need the final vulnerability class or target function to be selected initially, and it used measured evidence to reject its first hypothesis and continue research.

The Solidity maturity gate remains open. The next gate is repetition on additional unfamiliar targets and materially different mechanisms, with the same strict blind boundary and causal/reproduction requirements.


## Milestone 67 — strict blind external-call outcome finding (Benchmark 029)

Benchmark 029 added a generic class-neutral reasoning surface for external-call outcome / transition integrity and exercised it against the unfamiliar pinned Nested Finance Withdrawer target.

Target:
- repository: https://github.com/code-423n4/2022-06-nested.git;
- pinned revision: b4a153c943d54755711a2f7b80cbbf3a5bb49d76;
- source: contracts/Withdrawer.sol;
- blind target function selected by CYDRA: withdraw.

Strict blind boundary:
- no vulnerability class;
- no target function;
- no state surface;
- no specialized reasoning-surface injection;
- no custom planner;
- no exploit sequence;
- no historical answer.

The normal pipeline independently selected H-EXTERNAL-OUTCOME-withdraw from the pinned source. The hypothesis was then executed against the actual pinned repository and dependency graph.

The first causal harness attempt is retained as a research failure: the generated receiver test could not accept native value and the patched control was initially evaluated against the vulnerable assertion. CYDRA therefore reached UNRESOLVED, and the failure was diagnosed from execution evidence rather than counted as a finding.

The harness was corrected generically:
- the adversarial receiver now accepts native value;
- vulnerable execution asserts that value must not be released after a false transferFrom result;
- patched execution explicitly expects the causal validation revert;
- the same harness is used for independent vulnerable and patched reproductions.

Final dedicated CI run #7 (run ID 35585078197) completed:
- blind hypothesis: H-EXTERNAL-OUTCOME-withdraw;
- vulnerable execution: FAIL;
- patched causal control: PASS;
- causal verification: VERIFIED;
- independent vulnerable reproduction: FAIL;
- independent patched reproduction: PASS;
- finding gate: READY.

This is a materially different mechanism from the existing accounting, lifecycle, authorization, signature, control-flow, state-persistence, and rounding campaigns: an external dependency can report failure without reverting, and the target must not continue into a subsequent value-releasing transition.

The historical Code4rena report is post-selection corroboration/evaluation context only; it was not supplied to CYDRA during hypothesis generation.

This milestone strengthens the Solidity maturity evidence because the new reasoning surface generalized from a mechanism-level invariant rather than encoding the Nested target's function name, historical exploit sequence, or answer. The Solidity maturity gate remains open. The next campaigns should continue testing materially different unfamiliar mechanisms and, where possible, reduce the need for target-specific causal harness code while preserving the strict blind boundary and fail-closed finding gate.

## Milestone 68 — operational end result: repeated blind causal findings on main

After Benchmark 030, the merged main commit was exercised by the canonical Solidity research workflow and the open-ended blind workflow.

The operational end result is now demonstrated: CYDRA can take an unfamiliar pinned Solidity target through system modeling, class-neutral hypothesis generation, experiment selection, real Foundry execution, causal differential verification, and finding-gate evaluation, producing a reproducible finding without being handed the historical vulnerability class or answer.

Evidence on main commit b586cc66f62a3b1e0d0c745ac22c9e1a3efecf81 includes:

- Benchmark 030 strict blind type-domain reachability: blind selection of H-TYPE-DOMAIN-reRoll-tokenId; vulnerable FAIL; causal control PASS; causal verification VERIFIED; independent vulnerable FAIL; independent patched PASS; finding gate READY.
- Benchmark 022 open-ended blind regression: blind selection of H-SIGNED-METADATA-_validateSignature; vulnerable FAIL; patched PASS; causal verification VERIFIED; independent reproduction verified; finding gate READY.
- The canonical Solidity research workflow completed successfully with the full Python regression suite, the verified unfamiliar-target historical backtest, real Alchemix authorization, Stader initialization, Olas transfer-accounting, and Morph initialization backtests all completing successfully. The Olas and cross-contract historical runs reached a READY finding gate with causal verification.
- The strict-blind epoch-boundary campaign initially remained a retained negative result because its one-shot selector chose H-INTENT-PARITY-whiteListLendingMarket instead of the epoch hypothesis. That negative result is preserved as the pre-loop baseline rather than erased. After the generic evidence-driven research loop was applied, the same blind campaign independently selected H-EPOCH-ACCOUNTING-update_market, executed it against the pinned target, reproduced the causal differential, and reached READY.

This establishes the practical end result required by the project: CYDRA is no longer only an architecture or benchmark framework; the merged system has demonstrated reproducible blind finding production on unfamiliar Solidity targets.

The broader Solidity maturity/generalization gate remains open. Future work should improve the generic evidence-driven research loop, reduce benchmark-specific harness assumptions, and test additional unfamiliar targets. No future benchmark should be accepted merely because a specialized detector was made to select its historical answer.

Doctrine remains: **LLMs propose. Tools test. Evidence decides.**


## Milestone 69 — generic research-loop recovery of the retained blind miss

Benchmark 028 was rerun after the class-neutral evidence-driven research loop became mainline. This was a held-out regression of the exact one-shot selector failure documented in Milestone 68; no selector score, vulnerability-class hint, target function, state surface, historical answer, or benchmark-specific reasoning surface was added to the blind context.

The blind investigation initially generated multiple competing hypotheses. The generic loop selected a non-executable hypothesis when appropriate, recorded the observation as UNMEASURABLE rather than treating it as success, and fed that evidence back into hypothesis selection. The next selection reached the epoch-boundary accounting hypothesis:

- hypothesis: H-EPOCH-ACCOUNTING-update_market;
- invariant: INV-EPOCH-ACCOUNTING-update_market;
- target: pinned Canto LendingLedger.sol at revision 5e0d6f1f981993f83d0db862bcf1b2a49bb6ff50;
- vulnerable execution: FAIL, with the observed accounting value 100000000000000000000000 versus the piecewise expected 150000000000000000000000;
- patched causal control: PASS;
- causal differential: VERIFIED;
- independent vulnerable reproduction: FAIL;
- independent patched reproduction: PASS;
- reproduction verification: true;
- finding gate: READY.

The artifact is from the actual strict-blind CI run #37 (run ID 35596000527). Full Python regression also passed in the same job.

This is important evidence about the research loop itself: the previously retained selector miss was recovered by executing and learning from the first hypothesis rather than by changing selector scoring or teaching the system the historical answer. The original one-shot miss remains preserved as a negative baseline, while the iterative run demonstrates evidence-driven recovery.

Boundary: Benchmark 028 remains a bounded historical campaign and does not establish arbitrary open-ended discovery. The next maturity work should therefore continue on a genuinely unfamiliar target/mechanism and test whether the generic loop produces the same kind of recovery and finding-gate evidence without a benchmark-specific execution binding.

## Milestone 70 — strict blind callback-before-state-update finding (Benchmark 032)

Benchmark 032 completed the next materially different strict-blind campaign against the pinned Phi `Cred.sol` target at revision `8c0985f7a10b231f916a51af5d506dd6b0c54120`.

Strict blind boundary:
- no vulnerability class;
- no target function;
- no exploit sequence;
- no state surface;
- no specialized reasoning-surface injection;
- no custom planner;
- no historical answer.

The normal pipeline initially selected two non-executable hypotheses and recorded both as `UNMEASURABLE`. The generic selector then selected `H-CALLBACK-STATE-ORDER-buyShareCred` from source-level callback/state-order evidence. The selected hypothesis was bound to the public `buyShareCred` wrapper while preserving the internal `_handleTrade` provenance.

The campaign exposed and fixed two generic issues before completion:
- callback topology needed source-level binding through internal helpers rather than relying on direct model writes;
- an `UNMEASURABLE` observation needed stronger generic information-gain deprioritization so the research loop would move to a different executable hypothesis instead of repeatedly selecting the same non-renderable candidate.

The isolated Foundry differential harness then executed the real pinned repository after installing its authoritative `bun.lockb` dependencies.

Final canonical CI run #26 (run ID `35610469250`) completed successfully:
- blind selection: `H-CALLBACK-STATE-ORDER-buyShareCred`;
- vulnerable execution: FAIL;
- patched causal control: PASS;
- causal verification: VERIFIED;
- independent vulnerable reproduction: FAIL;
- independent patched reproduction: PASS;
- reproduction verification: true;
- finding gate: READY.

The vulnerable trace showed the attacker-controlled callback successfully reentering `sellShareCred` before the temporal state was established; the patched control moved the timestamp write before the external value transfer and blocked the reentrant sell. The final artifact was uploaded by the canonical GitHub Actions run and its `result.json` records the complete blind loop, differential execution, causal verification, and READY gate.

This is a materially different mechanism from the preceding resource-authorization, type-domain, epoch-boundary, external-outcome, signature, authorization, lifecycle, accounting, rounding, and control-flow campaigns. The historical Phi source was used as the pinned evaluation target and causal-control basis only after blind hypothesis selection.

The Solidity maturity/generalization gate remains open. Benchmark 032 adds another successful unfamiliar-mechanism blind finding, but closure still requires repeated evidence across additional unfamiliar targets and mechanisms without target-shaped detectors or benchmark-provided selection hints.

Doctrine remains: **LLMs propose. Tools test. Evidence decides.**

## Milestone 71 — iterative strict-blind read-only reentrancy finding (Benchmark 033)

Benchmark 033 completed the next unfamiliar-target campaign against the pinned Bond Protocol `BondFixedTermTeller.sol` target from `sherlock-audit/2022-11-bond`.

The campaign preserved the strict blind boundary:
- no vulnerability class supplied to selection;
- no target function supplied;
- no exploit sequence supplied;
- no state surface supplied;
- no historical answer supplied;
- no benchmark-specific selector override.

The first normal class-neutral selection chose `H-EXTERNAL-OUTCOME-create`. CYDRA executed that hypothesis against the real pinned repository with a false-returning ERC20 transferFrom probe. The experiment passed, meaning the selected external-outcome hypothesis was contradicted for the target. The generic research loop fed that measured result back into selection as a rejected hypothesis rather than silently replacing it.

The second selection independently reached:
`H-READONLY-_mintToken-mapping`

The selected experiment was then executed against the actual pinned Bond repository. The vulnerable implementation allowed the ERC1155 receiver callback to read the public `tokenMetadata` mapping while the bond-token supply was still zero; after the callback returned, the settled supply became the minted amount.

Canonical differential result from CI run #13 (run ID `35613621802`):
- first hypothesis: `H-EXTERNAL-OUTCOME-create`;
- first experiment: PASS / contradicted;
- second blind hypothesis: `H-READONLY-_mintToken-mapping`;
- vulnerable execution: FAIL;
- patched causal control: PASS;
- causal verification: VERIFIED;
- independent vulnerable reproduction: FAIL;
- independent patched reproduction: PASS;
- reproduction verification: true;
- finding gate: READY.

The causal control changed only the ordering in `_mintToken`: record the supply before invoking the callback-capable ERC1155 mint. The vulnerable and patched executions were run from independent clones. The uploaded CI `result.json` artifact contains the complete selection/reselection, execution differential, causal verification, and READY gate.

This campaign is materially different from Benchmark 032. Benchmark 032 tested callback-before-security-state-update where the callback reentered a state-changing function; Benchmark 033 tests a read-only observation of transient aggregate state through a public mapping during a token receiver callback. It therefore adds evidence for cross-function temporal consistency and evidence-driven hypothesis reselection on an unfamiliar target.

The Solidity maturity/generalization gate remains open. The next maturity step is not to add another target-shaped detector merely to increase the benchmark count. The evidence now supports continuing toward broader open-ended campaigns where CYDRA must generate, test, reject, and reselection hypotheses across unfamiliar targets while preserving causal verification and independent reproduction.

Doctrine remains: **LLMs propose. Tools test. Evidence decides.**

## Milestone 72 — strict blind incentive-state divergence finding (Benchmark 036)

Benchmark 036 completed a strict-blind holdout for permissionless incentive payout coupled to caller-manufactured work. The campaign required blind selection, vulnerable/patched differential execution, causal verification, independent reproduction, and READY finding-gate promotion. The campaign exposed and repaired execution-model and economic-measurement issues before the final green run. It is evidence for generic incentive-state reasoning, not evidence that the maturity gate is closed.

## Milestone 73 — strict blind keeper zero-work incentive finding (Benchmark 037)

Benchmark 037 completed a strict-blind holdout derived from the security-relevant shape documented in Sherlock's 2023 Perennial V2 judging material: a reward-bearing keeper path could pay after a zero-iteration settlement call. The CYDRA fixture is an executable reduction rather than the historical deployment itself.

The benchmark forced the generic incentive-liveness capability to recognize reward flow through a modifier and work through iterable execution rather than relying on a direct payout in the function body. The blind boundary supplied no vulnerability class, target function, exploit sequence, invariant, patch, historical answer, or selector override.

The final validated campaign on PR #158 completed all repository checks with zero failures and reached:
- blind selection: generic incentive-liveness hypothesis for settle;
- vulnerable execution: FAIL with the security assertion triggered by reward paid for zero work;
- patched execution: PASS;
- causal verification: VERIFIED;
- independent vulnerable reproduction: FAIL with the same security assertion;
- independent patched reproduction: PASS;
- finding gate: READY.

The campaign also exposed and repaired two harness defects before acceptance: an initially non-executable abstract fixture and an incorrect caller-balance baseline taken before target funding. This is precisely the required diagnose → repair → retest loop.

The result strengthens evidence for generic incentive-state reasoning and adversarial execution measurement. It does not close the Solidity maturity/generalization gate. Further unfamiliar targets must continue to test whether the reasoning generalizes without benchmark-shaped selection or target-specific detectors.

Doctrine remains: **LLMs propose. Tools test. Evidence decides.**

## Milestone 74 — multi-finding and evidence-backed severity architecture

CYDRA now supports target-scoped accumulation of independently confirmed findings. The generic research loop can retain multiple verified findings across investigation rounds instead of replacing the target result after the first finding. Findings can be ordered for reporting by their demonstrated canonical impact level.

Pre-confirmation impact potential is a bounded research-priority signal only. UNKNOWN receives no bonus. It must never be treated as final severity. Final severity remains evidence-backed and is required to agree with the demonstrated impact assessment.

An optional program-specific severity policy can be supplied after the conservative baseline classifier. This avoids assuming that all bounty programs use identical severity taxonomies while preserving the underlying technical impact evidence.

PR #162 integrated the target-scoped finding collection. PR #163 connected impact potential to generic hypothesis selection. PR #164 integrated multi-finding accumulation into the research loop. PR #165 added explicit program severity policy handling. All four milestones passed their repository CI gates before merge; PR #165 completed 39/39 checks with zero failures before merge.

This architecture does not close the Solidity maturity/generalization gate. The remaining proof obligation is behavioral: repeated strict-blind unfamiliar-target campaigns must demonstrate that the generalized research loop can discover and causally verify genuine vulnerabilities, including more than one finding where the target supports it, without benchmark-specific detectors or selector overrides.

Doctrine remains: **LLMs propose. Tools test. Evidence decides.**
