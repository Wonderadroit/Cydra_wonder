# CYDRA Development Protocol

## Purpose

This protocol keeps development aligned with the Project Bible and prevents CYDRA from becoming an LLM wrapper, alert factory, or over-engineered audit platform.

## Build-before-Bible rule

Documentation is not progress unless it changes what can be executed or falsified.

After the minimum doctrine is established, every major phase must produce a runnable capability against a real historical benchmark or authorized target before substantial architecture is added.

## Before changing code

1. State the research capability being improved.
2. Identify the exact Project Bible rule involved.
3. Identify the smallest useful implementation.
4. Define a pre-registered acceptance test.
5. Define what would falsify the implementation.
6. Prefer existing mature tools over new replacements.

## Strong-vs-weak acceptance tests

For each reasoning capability, define the strong output before implementation.

### System Model

**Strong:** source-linked functions, state writes, modifiers, calls, and relevant relationships agree with the target code.

**Weak:** an LLM produces a plausible prose summary.

**Falsifier:** a human or deterministic comparison finds material model errors on the benchmark target.

### Invariant → Hypothesis Binding

**Strong:** a provenance-backed invariant identifies a concrete violating operation, execution path, and expected consequence.

**Weak:** an LLM writes a generic statement such as "balances should be consistent."

**Falsifier:** the hypothesis cannot identify the target operation or a testable violation path.

### Competing Hypotheses

**Strong:** at least two materially different explanations are preserved when the evidence permits ambiguity, and the planner identifies a test that distinguishes them.

**Weak:** the engine produces multiple differently worded versions of the same conclusion.

**Falsifier:** the selected experiment cannot change the relative plausibility of the alternatives.

### Information-Gain Test Planning

**Strong:** the next action is selected because it can materially reduce uncertainty within the available budget.

**Weak:** every scanner is run in a fixed sequence.

**Falsifier:** a cheaper or more discriminating available experiment is ignored without justification.

### Causal Finding Gate

**Strong:** a finding requires target-linked code, attacker capability, reachable path, violated invariant, causal state transition, demonstrated impact, and reproducibility.

**Weak:** a static warning or LLM conclusion is promoted to a finding.

**Falsifier:** the gate accepts a claim whose impact cannot be reproduced or whose referenced code does not exist.

## During implementation

- Keep evidence provenance explicit.
- Keep uncertainty explicit.
- Do not silently turn suggestions into facts.
- Do not hard-code historical answers into detection logic.
- Do not add a detector unless its output can feed the reasoning/verification loop.
- Do not add an LLM call unless its output has a structured role and validation boundary.
- Fail closed on unknown authorization/scope for active execution.
- Keep tool adapters thin: `run(input) -> structured_output` plus explicit failure state.

## Human boundary

The human researcher owns final judgment and external submission.

CYDRA's job is to produce an auditable evidence package containing, where applicable:

- target/version and scope;
- invariant;
- execution path;
- state transition;
- attacker capability;
- tool results;
- PoC/reproduction;
- impact evidence;
- contradictory evidence;
- regression test.

The human reviews this package, independently checks the important claims, and writes/owns the final submission narrative.

## Required validation

Every meaningful feature should have:

- unit tests;
- integration coverage where relevant;
- a representative historical or authorized live case;
- negative/false-positive coverage where practical;
- reproducibility information.

For reasoning changes, test both:

1. a case that should strengthen the hypothesis;
2. a case that should reject or weaken a superficially similar hypothesis.

## Investigation budget

The engine must support explicit investigation budgets. A budget may constrain:

- number of reasoning rounds;
- number of tool executions;
- runtime;
- fuzzing effort;
- symbolic exploration;
- LLM calls.

The planner should spend budget where expected information gain is highest.

## Evidence rules

A tool result is evidence, not a conclusion.

A static detector may create an observation.

A passing test may strengthen a hypothesis.

A reproducible exploit may establish causality.

Contradictory results must be retained.

## Tool adapter contract

Each external security tool should have a thin adapter with:

```text
ToolAdapter.run(input) -> ToolResult
```

`ToolResult` must preserve:

- tool name and version when available;
- command/configuration;
- exit status;
- stdout/stderr or artifact references;
- structured findings/results;
- execution environment;
- timeout/failure state.

Adapters must not convert tool output directly into findings.

## Benchmark protocol

Historical cases are divided into development and blind evaluation sets.

A blind case must not expose its expected finding before CYDRA completes its investigation.

For every benchmark run record:

- target/version;
- scope/environment;
- initial observations;
- system model;
- invariants;
- hypotheses generated;
- competing hypotheses;
- tests selected;
- tool runs;
- evidence;
- final disposition;
- expected result after the blind run;
- false positives and misses;
- elapsed/runtime budget.

Phase 5 must eventually report measurable reproduction rate and false-positive rate rather than qualitative claims that the engine is "getting better."

## Self-falsification by phase

Each phase needs a direct test of how CYDRA could be wrong:

- **Phase 1:** model accuracy against a human/deterministic reference.
- **Phase 2:** hypothesis usefulness and rejection of superficial lookalikes.
- **Phase 3:** experiments actually distinguish competing hypotheses.
- **Phase 4:** a fixed vulnerability causes the PoC/property test to fail.
- **Phase 5:** historical findings reproduce through the same causal chain without answer leakage.
- **Phase 6:** evidence packages survive human review and target-program triage rules.

## Research loop

```text
Build
→ Run
→ Observe
→ Compare against expected behavior
→ Identify failure
→ Form hypothesis
→ Test
→ Update model
→ Record regression
→ Repeat
```

## Completion rule

A task is not complete because files exist or tests pass.

It is complete when the new capability is demonstrated to improve or preserve CYDRA's ability to understand a target, reduce uncertainty, choose better tests, or verify causality.

## Stop conditions

Stop adding architecture when:

- the current hypothesis cannot yet be tested;
- a feature has no benchmark;
- a mature existing tool already provides the capability;
- the implementation is becoming a speculative abstraction;
- the change improves appearance but not research outcomes.

## Commit discipline

Prefer small, semantically meaningful commits. Commit messages should describe the research capability or invariant being changed.

## Reporting progress

Every development checkpoint should report:

- changed files;
- capability added/fixed;
- tests run and result;
- benchmark/live-case result;
- known blocker;
- next highest-value task.
