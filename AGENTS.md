# CYDRA Agent Contract

## Current assignment

The only active engineering objective is **live-target dogfooding**.

The success condition is not "CI is green" and not "another benchmark passes". The success condition is:

**run the complete CYDRA pipeline against the pinned authorized live target → observe the first real pipeline gap → repair that gap generically → rerun the same target.**

## Canonical execution path

The canonical external entrypoint is:

`python scripts/run_live_contest.py --target-spec targets/live-contest.json --target-checkout <checkout> --output live-artifacts`

GitHub Actions must invoke this path for the live target. The live runner is the integration boundary; lower-level modules are implementation details.

## Hard stop / retraction rules

Before making a change, ask:

1. Does this change directly improve the live dogfood path?
2. Is the need demonstrated by the current live-target artifact/log?
3. Is the repair generic rather than target-specific?
4. Can the same pinned target be rerun to prove the repair?

If the answer to any of these is **no**, stop and return to the live dogfood failure.

Do **not**:
- add a new benchmark;
- add a synthetic fixture;
- expand a benchmark matrix;
- polish unrelated CI;
- create a new vulnerability-class detector because its name appears in a target;
- modify the target to make an experiment pass;
- bypass an execution/readiness blocker;
- treat a tool error or failed setup as a vulnerability;
- create architecture without a live-dogfood failure demonstrating the need.

## Required diagnosis order

Every live run is read as a pipeline:

1. target freeze / scope
2. target environment and dependencies
3. source and compiler extraction
4. system model
5. invariant candidates
6. hypotheses
7. experiment planning
8. execution readiness
9. generated experiment
10. deterministic execution
11. evidence
12. hypothesis update / causal verification
13. reproducible finding gate

The **first demonstrated blocker** is the next engineering task. Do not jump ahead.

## Agent handoff

At the end of work, leave:
- the exact live-target commit/ref;
- the exact CYDRA commit;
- the current live artifact/run;
- the observed blocker;
- the generic repair;
- the rerun result;
- the next blocker, if any.

