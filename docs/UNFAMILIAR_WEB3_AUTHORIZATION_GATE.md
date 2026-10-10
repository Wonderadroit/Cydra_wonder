# Unfamiliar-Target Gate: Web3 Authorization Specialist

## Purpose

Measure whether CYDRA's existing authorization specialist transfers to an unfamiliar Solidity/EVM target without target-specific engineering. This is a bounded validation gate, not a new detector and not a claim that a bounty finding exists.

## Non-negotiable safety and evidence rules

- The human operator must record the bounty/program URL, in-scope repository/contracts, exclusions, allowed testing environment, and permission for the exact planned tests before the campaign starts.
- Pin the target source to an immutable commit SHA. Do not infer authorization from public source availability.
- Prefer local compilation and local/fork/testnet experiments. Do not send state-changing transactions to production.
- Keep the target blind to CYDRA: do not feed historical reports, known vulnerable function names, benchmark labels, or expected answers into the campaign.
- Preserve provenance for every observation: source file and line, target commit, tool/version, command, raw output, hypothesis, and experiment result.
- A candidate is not a finding until an independent human verifies scope, novelty, impact, and reproducibility.
- Never weaken a test or mark a blocked experiment as a pass to make the campaign green.

## Fixed specialization

The only vulnerability class under test is missing or incorrect authorization on state-changing Solidity/EVM operations: a caller outside the intended role/ownership boundary can cause a protected state transition.

Out of scope for this gate: reentrancy, arithmetic, oracle manipulation, denial of service, economic attacks, generic fuzzing for its own sake, and unrelated Web2 issues.

## Campaign stages

1. **Intake** — capture program rules and explicit authorization; reject the campaign if scope or permitted test environment is unclear.
2. **Freeze** — record repository URL, immutable commit SHA, in-scope paths/contracts, exclusions, and compiler/toolchain versions.
3. **Blind discovery** — run existing source discovery/model construction without target-specific patches or answer hints.
4. **Authorization model** — enumerate state-changing entry points, declared modifiers/guards, role/owner predicates, and the evidence supporting each inferred boundary. Mark uncertainty explicitly.
5. **Hypotheses** — generate authorization hypotheses only from the discovered model. Each hypothesis must name the caller capability, protected transition, expected guard, and evidence needed to falsify it.
6. **Readiness check** — classify every experiment prerequisite as already satisfied, constructible by the existing adapter/harness, or unresolved. An unresolved prerequisite is a blocker, not a vulnerability.
7. **Local experiment** — execute the highest-information safe experiment using the existing Foundry path. Capture transaction trace/state delta and caller identity.
8. **Causal verification** — where technically possible, apply a minimal guard correction in a disposable worktree and repeat the exact experiment. The vulnerable behavior should reproduce before the correction and disappear after it; unrelated behavior should remain stable.
9. **Independent reproduction** — rerun from a clean checkout using the pinned revision and recorded commands.
10. **Human finding gate** — check scope, duplicate/known status, impact, and reportability. No automatic submission.

## Gap-filling policy

When the run stops, record exactly one primary blocker and its evidence. Use these blocker categories:

- SCOPE_UNCONFIRMED
- SOURCE_OR_TOOLCHAIN_DISCOVERY
- MODEL_MISSING_STATE_CHANGING_SURFACE
- AUTHORIZATION_BOUNDARY_UNCERTAIN
- EXPERIMENT_PREREQUISITE_UNAVAILABLE
- EXECUTOR_FAILURE
- INSUFFICIENT_CAUSAL_EVIDENCE
- REPRODUCTION_FAILURE
- NO_SUPPORTED_HYPOTHESIS
- NO_CANDIDATE_FOUND

Only fix a blocker if a captured log, test, or artifact demonstrates that it prevents this authorization campaign from progressing. Prefer a generic repair that improves the reusable Solidity/EVM path. Every repair must add a regression test, rerun the focused authorization tests, and replay the same frozen target.

Do not add target-specific function names, addresses, expected findings, or selectors to the detector; introduce unrelated vulnerability classes; repeatedly expand the architecture without a measured blocker; count a compile error, unavailable prerequisite, or unexecuted experiment as a negative security result; or call a historical known vulnerability a new discovery.

## Required campaign artifact

Write a machine-readable JSON report and a concise Markdown summary containing:

- campaign ID and timestamp;
- authorization/program URL and operator scope confirmation;
- repository URL and immutable commit SHA;
- toolchain versions;
- discovered contract/function counts;
- state-changing surfaces and authorization evidence;
- hypotheses generated, tested, falsified, blocked, and unresolved;
- experiment commands, caller identity, transaction/state evidence, and provenance;
- primary blocker (if any), exact error/log reference, and whether a generic repair is justified;
- patch/replay and clean reproduction results;
- novelty/scope review status;
- final disposition: VERIFIED_CANDIDATE, NO_CANDIDATE_FOUND, BLOCKED, or OUT_OF_SCOPE.

A successful engineering run is not necessarily a successful vulnerability campaign. Keep those outcomes separate.

## Measurable finish line

The specialist passes this gate only when, on at least two unfamiliar, explicitly authorized, immutable target revisions:

1. it reaches the authorization-model and hypothesis stages without target-specific detector patches;
2. each attempted experiment is either executed or assigned an evidence-backed blocker;
3. the campaign preserves complete, reproducible artifacts;
4. at least one positive control and one negative control retain their expected behavior;
5. no unrelated vulnerability class is introduced;
6. a human can independently reproduce the campaign disposition from the artifacts.

This is a transfer/readiness gate, not a promise that every target contains a vulnerability. A NO_CANDIDATE_FOUND result can be a valid campaign outcome if discovery and experiments completed properly. It must not be described as proof that the target is secure.

## Operator checklist

- [ ] Program rules reviewed and authorization recorded
- [ ] Target and immutable revision pinned
- [ ] Scope/exclusions recorded
- [ ] Blind run completed without answer hints
- [ ] Model and hypothesis provenance captured
- [ ] Every experiment executed or explicitly blocked
- [ ] First demonstrated blocker diagnosed
- [ ] Generic repair and regression added only if justified
- [ ] Same frozen target replayed after repair
- [ ] Positive and negative controls passed
- [ ] Artifacts retained and independently reproducible
- [ ] Human scope, novelty, and impact review completed