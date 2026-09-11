# CYDRA Project Bible

## 1. Mission

CYDRA is a security-research reasoning engine for authorized targets. Its purpose is to understand a target system deeply and discover real, non-obvious, reproducible vulnerabilities that can be responsibly reported under the target program's rules.

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
