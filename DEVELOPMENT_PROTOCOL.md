# CYDRA Development Protocol

## Purpose

This protocol keeps development aligned with the Project Bible and prevents CYDRA from becoming an LLM wrapper, alert factory, or over-engineered audit platform.

## Before changing code

1. State the research capability being improved.
2. Identify the exact Project Bible rule involved.
3. Identify the smallest useful implementation.
4. Define a test or benchmark that can falsify the change.
5. Prefer existing mature tools over new replacements.

## During implementation

- Keep evidence provenance explicit.
- Keep uncertainty explicit.
- Do not silently turn suggestions into facts.
- Do not hard-code historical answers into detection logic.
- Do not add a detector unless its output can feed the reasoning/verification loop.
- Do not add an LLM call unless its output has a structured role and validation boundary.
- Fail closed on unknown authorization/scope for active execution.

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

## Benchmark protocol

Historical cases are divided into development and blind evaluation sets.

A blind case must not expose its expected finding before CYDRA completes its investigation.

For every benchmark run record:

- target/version;
- scope/environment;
- initial observations;
- hypotheses generated;
- tests selected;
- tool runs;
- evidence;
- final disposition;
- expected result after the blind run;
- false positives and misses;
- elapsed/runtime budget.

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
