# CYDRA Operating Protocol — Human + LLM + GitHub Actions

## Purpose

CYDRA is operated as a research system, not as a standalone autonomous chatbot.

The working arrangement is:

1. **The human researcher** defines authorization, scope, program rules, target intake, and final submission decisions.
2. **The LLM in the research chat** interprets CYDRA, plans and explains investigations, diagnoses failures, proposes generic repairs, reviews evidence, and keeps the research direction aligned with the Project Bible.
3. **CYDRA in GitHub** is the durable reasoning/tooling system. Its code, tests, benchmarks, artifacts, and Project Bible are the persistent state that another agent can inherit.
4. **GitHub Actions** is the deterministic execution environment for regression, blind campaigns, target backtests, batch campaigns, and long-running validation.
5. **Target adapters** must first establish the target's language/framework/compiler/dependency/execution environment and record unresolved blockers before deep reasoning or generated experiments. (Foundry, Slither, fuzzers, symbolic/formal tools, compilers, parsers, and custom analyses) generate measurements. They do not by themselves establish a vulnerability.
6. **A human reviewer** decides whether a verified result is actually in program scope and whether/how to submit it.

## Chat continuity and agent handoff

The chat is useful working memory, but it is not the authoritative project state.

If a chat ends, another agent must be able to resume from the repository without relying on hidden conversation memory.

The durable handoff surface is:

- `PROJECT_BIBLE.md` — mission, doctrine, architecture, current phase, milestones, and non-negotiables.
- this document — operating contract between human, LLM, GitHub Actions, and deterministic tools.
- repository code/tests — current implementation.
- benchmark runners and workflow files — reproducible validation procedures.
- CI run records and benchmark artifacts — observed execution evidence.
- merged commit history — durable chronology of changes.
- open PRs — temporary in-flight work; they must be inspected before starting duplicate work.

A future agent must inspect these sources before implementing changes.

## Required continuation procedure

Before changing CYDRA:

1. Read the current Project Bible.
2. Inspect `main`, recent commits, open PRs, and current CI.
3. Determine the last accepted milestone and any in-flight campaign.
4. Inspect the actual failing run/log before proposing a repair.
5. Prefer a generic repair over a benchmark-specific workaround.
6. Test the repair with focused regression.
7. Run the affected benchmark.
8. Run the relevant batch/full CI matrix.
9. Wait for long-running jobs to finish.
10. Merge only when the acceptance criteria are genuinely satisfied.
11. Record the result in the Project Bible and leave the repository resumable.

Never declare a campaign green while required jobs remain queued or running.

## Investigation operating loop

For real authorized research the operating loop is:

**Intake/scope → Environment/adapter discovery → Target snapshot → System model → Invariants → Competing hypotheses → Information-gain experiments → Deterministic execution → Evidence → Causal verification → Independent reproduction → Finding package → Human review**

A negative or unmeasurable result is evidence about the current hypothesis/execution, not permission to invent a result.

Before executing a generated experiment, CYDRA should derive **execution readiness** from the target model. This includes constructor/deployment dependencies, caller-role requirements, caller-identity predicates, external runtime dependencies, and transient call-result data flow. When a reachability predicate depends on a helper result, CYDRA should resolve the producer through the modeled source/inheritance graph when possible, while keeping producer discovery distinct from proof that the required value is satisfiable. Each prerequisite is classified as already satisfied, constructible by the adapter/harness, or unresolved. Unresolved prerequisites produce an explicit execution/environment blocker rather than being interpreted as security evidence. This layer is generic and target-independent.

A real finding requires reproducible evidence and must survive adversarial challenge.

## Blindness and the LLM

The LLM may help interpret CYDRA and the evidence produced by CYDRA. It must not leak historical answers into a blind benchmark or turn a known benchmark answer into a selector.

When a campaign is explicitly blind, the blind runner is the authority on what information was exposed to CYDRA.

The LLM should distinguish:

- what the code/model says;
- what a deterministic tool measured;
- what is an inference;
- what remains uncertain;
- what has been causally verified.

## Batch-campaign policy

Independent campaigns may be run concurrently when they do not share mutable target state.

A batch campaign must preserve each campaign's own:

- target snapshot;
- blind boundary;
- hypotheses;
- experiments;
- execution evidence;
- causal result;
- reproduction result;
- finding gate.

Batching is an orchestration optimization. It must not change the semantics of an individual benchmark.

If one campaign is blocked by an environmental/transient failure, the batch remains fail-closed. Diagnose and rerun the affected campaign rather than weakening its acceptance condition.

## Bug-bounty readiness boundary

CYDRA can be used as a research instrument before it is perfect.

The safe starting point is **human-supervised dogfood on explicitly authorized, in-scope programs**.

CYDRA should not be treated as an autonomous submitter. Before a result is submitted, the human researcher must independently review:

- program scope and exclusions;
- target/version/commit;
- exact vulnerable path;
- attacker capability;
- invariant violation;
- reproducible proof;
- demonstrated impact;
- duplicate/known-issue status where applicable;
- evidence provenance;
- report wording.

The first production use should therefore be an evidence-producing co-researcher, not an unattended scanner.

## Future language adapters

Solidity/EVM remains the current production research adapter.

Additional adapters such as Solana/Rust may be added later, but only through the same architecture:

**language adapter → system model → invariants → hypotheses → experiments → deterministic evidence → causal verification → finding**

A new language must not weaken the core evidence and provenance rules.
