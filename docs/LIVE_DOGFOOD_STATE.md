# CYDRA Live Dogfood State

> This file is the durable checkpoint for live-target work. It is intentionally short enough for a new agent to read first and detailed enough to reconstruct the current state.

## Mission

Live-target dogfooding only. Pinned target: Hinkal public-code target.

## Frozen target

- Repository: `Hinkal-Protocol/Hinkal-Contracts-Circuits`
- Commit: `61b6839aa80fc0c33bfdcde0323753c83cb2ce67`

## Current CYDRA branch

- Branch: `dogfood-readiness-expression-provenance`
- Current checkpoint commit: `aa68b51d44715de017602c3141b2cfd167e0b4a0`

## Latest validated live run

- Workflow: `CYDRA canonical live-target dogfood`
- Run: `36182788690`
- Artifact: `10884960775` (cydra-live-hinkal-93fa562c48df5ef30e1105ddaaa4ca05e53ab33b)
- Artifact URL: https://github.com/Wonderadroit/Cydra_wonder/actions/runs/36182788690/artifacts/10884960775
- Artifact digest: `sha256:893726515cf391f34bd595a311331417d010e2b6b2ffc88ce7df18106097633c`

## Last observed pipeline boundary

The previous live artifact showed false execution-readiness blockers:

- Solidity `abi.decode` was incorrectly treated as a runtime dependency — repaired.
- Deterministic casts such as `bytes4(op.callData)` and `int256(...)` were still being reclassified as unresolved producer dependencies — generic repair added.
- `utxoSet.skipLast` was treated as an external runtime dependency — generic local-value classification added.

The latest run (36182788690 / artifact 10884960775) confirms the readiness repair worked:
- `abi.decode` is no longer a runtime dependency.
- `bytes4(op.callData)` is classified as a deterministic local constraint.
- `int256(balancesAfter[i]) - int256(balancesBefore[i])` is classified as a deterministic local constraint.
- `utxoSet.skipLast` is no longer a runtime requirement.
- `runAction` now has zero runtime requirements and zero state-setup requirements in readiness.
- The next genuine blocker is the missing generic runtime adapter for the generated callback-order reasoning surface.

## Latest generic repair

Branch `dogfood-readiness-expression-provenance` now contains generic execution-readiness handling for:

- Solidity builtin namespaces;
- deterministic builtin/cast expressions;
- local/parameter/bound-value member operations;
- regression tests for deterministic expression provenance.

The readiness artifact has now proved those false blockers are resolved. The next engineering task is the generic callback-order runtime adapter; it must remain target-neutral.

## Findings

No confirmed finding from this live campaign.

## Next action

Implement the generic callback-order runtime adapter, add regression coverage, then rerun the same frozen Hinkal target. Do not claim a finding until causal execution and independent verification produce evidence.

Canonical workflow:
https://github.com/Wonderadroit/Cydra_wonder/actions/workflows/cydra-live-contest.yml

## Automatic checkpoint format

After each canonical workflow run, the workflow updates the run/artifact/commit metadata in this file. Human/agent engineering changes should update the diagnosis and next-action sections.
