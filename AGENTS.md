# CYDRA_wonder Agent Instructions

## Mission
Continue CYDRA_wonder as an authorized security-research system. The goal is reproducible, evidence-backed security findings on authorized targets—not generic audit/compliance output.

Core doctrine: **LLMs propose. Deterministic tools test. Evidence decides.**

## Mandatory workflow
1. Read `PROJECT_BIBLE.md` before changing architecture or behavior.
2. Read `docs/AGENT_HANDOFF.md` before continuing this work.
3. Inspect the actual repository branch, current commit, open PRs, and GitHub Actions state. Do not rely on chat memory alone.
4. Preserve the closed maturity gate. Do not reopen or redesign completed benchmark validation unless a concrete regression invalidates it.
5. Keep fixes generic. Do not add Arcadia-specific heuristics, target-specific constants, or hard-coded findings.
6. Every behavioral change needs a focused regression and then the relevant broader regression.
7. Diagnose failures from logs/artifacts, fix the smallest generic cause, retest, and inspect the next failure.
8. Never classify a behavior as a vulnerability without causal evidence and reproducibility.
9. Keep blind research blind: do not import historical audit findings or external issue knowledge into the initial target reasoning.
10. Treat execution failures as execution failures until evidence demonstrates security impact.
11. Use GitHub Actions as the canonical reproducible environment for the research run.
12. Do not stop merely because one job finishes. Inspect all required jobs and the final research artifact before declaring a milestone complete.
13. Do not create a new benchmark solely to continue work. Add a benchmark only when a genuinely new capability requires one and the Bible calls for it.
14. Keep the repository self-describing so another agent can resume from the repo alone.

## Current research boundary
The active target-only branch is `research/arcadia-lending`. The frozen public target is Arcadia Finance `lending-v2`; research is against the frozen public source checkout in the workflow. This is local/public-code research only; do not interact with live deployed contracts or bounty-program actions.

## Current objective
Turn the matured CYDRA pipeline from target intake into meaningful executable security research. The current generic blocker is **execution readiness**: discover constructor dependencies, roles/callers, runtime/state prerequisites, and constructible setup paths, then use those verified prerequisites to reach candidate security experiments instead of treating ordinary setup reverts as findings.

A particularly important generic capability is propagating prerequisites through call/data-flow (for example, a required state value produced by a helper call) and turning only verified, constructible prerequisites into setup actions.

## Working rules
- Prefer narrow, generic fixes with tests.
- Preserve provenance and uncertainty.
- Fail closed when dependency resolution is ambiguous.
- Never silently convert an execution failure into a pass.
- Never use a privileged caller to prove an unauthorized-call hypothesis.
- Do not claim that the Arcadia research found a bug until the artifact's evidence is inspected.
- When research is complete, inspect the uploaded artifact, classification, execution evidence, integrity/provenance, and all job conclusions.


## Diagnosis-first rule

When CYDRA encounters an unfamiliar target, adapter issue, compiler/parser error, execution blocker, unexpected revert, or surprising result:

1. **Diagnose before patching.**
2. Determine the target's apparent intent, actors, state, invariants, preconditions, and enforcement mechanisms.
3. Treat the observed error/behavior as evidence about the current system model.
4. Use the target's own structure and mechanisms to construct the smallest discriminating experiment.
5. Fix the generic abstraction that the evidence shows is missing; do not patch the target symptom.
6. Add a focused regression and run the relevant broader regression.
7. Generalize only to the narrowest reusable capability justified by evidence.

Canonical loop:

**Observe → Diagnose → Understand Intent → Model → Identify Preconditions → Use Target Mechanisms → Experiment → Evidence → Update Model → Generalize**

This rule applies to adapters, execution readiness, compiler semantics, state setup, caller/role resolution, data-flow, and security hypotheses. More executions are not automatically progress; more **meaningful, reachable, evidence-producing, causally verified** executions are the goal.
