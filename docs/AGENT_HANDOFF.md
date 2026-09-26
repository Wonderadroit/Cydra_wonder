# CYDRA Agent Handoff

This file is the durable continuation contract for any agent working on CYDRA.

## First read

1. `PROJECT_BIBLE.md`
2. `AGENTS.md`
3. `docs/LIVE_DOGFOOD_STATE.md`
4. `docs/CONTINUE_CYDRA_PROMPT.md`

The repository is authoritative. Do not rely on previous chat history when these files contain the required state.

## Active mission

Only live-target dogfooding is active.

Canonical loop:

**run pinned target → inspect evidence → identify first genuine pipeline gap → implement generic repair → add regression → rerun the same target**

Do not expand benchmarks, redesign maturity, add target-specific logic, or work on unrelated CI.

## Required checkpoint

After every meaningful engineering step, update `docs/LIVE_DOGFOOD_STATE.md` with:

- CYDRA commit;
- target commit;
- workflow run;
- artifact ID/name/digest;
- observed blocker;
- generic repair;
- validation status;
- next blocker;
- exact next action.

The live workflow also refreshes this state automatically after each run.

## Current target

Pinned Hinkal public-code target:

`61b6839aa80fc0c33bfdcde0323753c83cb2ce67`

Canonical workflow:

`.github/workflows/cydra-live-contest.yml`

Canonical runner:

`python scripts/run_live_contest.py --target-spec targets/live-contest.json --target-checkout <checkout> --output live-artifacts`

## Handoff rule

A new agent must reconstruct the current task from the files above before changing code. If the state says a blocker is unresolved, reproduce/inspect that blocker before proposing the next architecture.
