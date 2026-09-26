# CYDRA Live Dogfood State

> This file is the durable checkpoint for live-target work. It is intentionally short enough for a new agent to read first and detailed enough to reconstruct the current state.

## Mission

Live-target dogfooding only. Pinned target: Hinkal public-code target.

## Frozen target

- Repository: `Hinkal-Protocol/Hinkal-Contracts-Circuits`
- Commit: `61b6839aa80fc0c33bfdcde0323753c83cb2ce67`

## Current CYDRA branch

- Branch: `dogfood-readiness-expression-provenance`
- Current checkpoint commit: `521efe91c9e67387f9b4c9a7aab3a0fd5e2bddeb`

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

The readiness repair was validated by live run `36182788690`. The next generic gap was the missing runtime adapter for `INV-CALLBACK-STATE-ORDER-*`.

Implemented on this branch:
- `src/cydra/callback_state_order_execution.py`: generic one-shot reentrant caller harness;
- `scripts/run_benchmark_blind.py`: callback-state-order capability registration and runtime dispatch;
- `tests/test_callback_state_order_execution.py`: generator regression coverage.

The harness derives the target function, ABI shape (using compiler-checked `abi.encodeCall`), constructor shape, and experiment inputs from the model/experiment. It does not contain Hinkal-specific callback interfaces or function names. It deliberately reports execution as `NOT_REACHED` until causal differential verification is performed.

## Findings

No confirmed finding from this live campaign.

## Next action

Dispatch the canonical workflow from `dogfood-readiness-expression-provenance` and inspect whether `H-CALLBACK-STATE-ORDER-runAction` is now Foundry-generated and executed. Classify the result only from execution evidence; if the generic harness cannot reach the callback, use that failure to identify the next generic prerequisite/argument-planning gap.

Canonical workflow:
https://github.com/Wonderadroit/Cydra_wonder/actions/workflows/cydra-live-contest.yml

## Automatic checkpoint format

After each canonical workflow run, the workflow updates the run/artifact/commit metadata in this file. Human/agent engineering changes should update the diagnosis and next-action sections.
