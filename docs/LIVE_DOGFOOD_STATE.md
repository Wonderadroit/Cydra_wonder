# CYDRA Live Dogfood State

> This file is the durable checkpoint for live-target work. It is intentionally short enough for a new agent to read first and detailed enough to reconstruct the current state.

## Mission

Live-target dogfooding only. Pinned target: Hinkal public-code target.

## Frozen target

- Repository: `Hinkal-Protocol/Hinkal-Contracts-Circuits`
- Commit: `61b6839aa80fc0c33bfdcde0323753c83cb2ce67`

## Current CYDRA branch

- Branch: `dogfood-readiness-expression-provenance`
- Current checkpoint commit: `93fa562c48df5ef672b82c62b2a3dec8e0714d4f`

## Latest validated live run

- Workflow: `CYDRA canonical live-target dogfood`
- Run: `36181923745`
- Artifact: `10884308344`
- Artifact URL: https://github.com/Wonderadroit/Cydra_wonder/actions/runs/36181923745/artifacts/10884308344
- Artifact digest: `4ca6771f317b71cd890f7f1a45d588febafc11f76bf90086f0b3f4bfb390b893`

## Last observed pipeline boundary

The previous live artifact showed false execution-readiness blockers:

- Solidity `abi.decode` was incorrectly treated as a runtime dependency — repaired.
- Deterministic casts such as `bytes4(op.callData)` and `int256(...)` were still being reclassified as unresolved producer dependencies — generic repair added.
- `utxoSet.skipLast` was treated as an external runtime dependency — generic local-value classification added.

The next run must determine whether those blockers disappear and expose the next genuine execution gap.

## Latest generic repair

Branch `dogfood-readiness-expression-provenance` now contains generic execution-readiness handling for:

- Solidity builtin namespaces;
- deterministic builtin/cast expressions;
- local/parameter/bound-value member operations;
- regression tests for deterministic expression provenance.

Do not build the callback runtime adapter until the readiness artifact proves these false blockers are resolved.

## Findings

No confirmed finding from this live campaign.

## Next action

Run the canonical workflow from the current branch, inspect the resulting artifact, and update this file with the new run/artifact/blocker.

Canonical workflow:
https://github.com/Wonderadroit/Cydra_wonder/actions/workflows/cydra-live-contest.yml

## Automatic checkpoint format

After each canonical workflow run, the workflow updates the run/artifact/commit metadata in this file. Human/agent engineering changes should update the diagnosis and next-action sections.
