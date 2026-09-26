# CYDRA Live Dogfood State

> This file is the durable checkpoint for live-target work. It is intentionally short enough for a new agent to read first and detailed enough to reconstruct the current state.

## Mission

Live-target dogfooding only. Pinned target: Hinkal public-code target.

## Frozen target

- Repository: `Hinkal-Protocol/Hinkal-Contracts-Circuits`
- Commit: `61b6839aa80fc0c33bfdcde0323753c83cb2ce67`

## Current CYDRA branch

- Branch: `dogfood-readiness-expression-provenance`
- Current checkpoint commit: `5930f4d110733cccdb2992b9692464f8bc0cf80b`

## Latest validated live run

- Workflow: `CYDRA canonical live-target dogfood`
- Run: `36225320370`
- Artifact: `10900860794` (cydra-live-hinkal-5930f4d110733cccdb2992b9692464f8bc0cf80b)
- Artifact URL: https://api.github.com/repos/Wonderadroit/Cydra_wonder/actions/artifacts/10900860794/zip
- Artifact digest: `sha256:9ca073d3c9ae267a9246665d8f42f23bd8b974ad320dcdb76ac30ad23178d606`

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



### Latest failed live run

Run `36182788690` reached the new callback adapter but failed before pipeline execution because `scripts/run_benchmark_blind.py` contained literal `\\n` escape text in the generated adapter block, producing a Python `SyntaxError` at import time. This is an implementation/validation failure in CYDRA, not a Hinkal target failure. The adapter block has been rewritten with real newlines in commit `feeea090010c8e3d87681b42230587f91b77102e`.

The subsequent live run `36225095992` (artifact `10900701699`) completed successfully, but its artifact showed the callback hypothesis was still recorded as `UNIMPLEMENTED`. Diagnosis: the callback adapter had been implemented, but `run_live_contest.py` still passed only the legacy five-class tuple, and `run_benchmark_blind.py` did not include `callback_state_order` in `SUPPORTED_CLASSES`. This was a CYDRA integration omission, not a Hinkal execution result.

Generic repair commits:
- `3569d9d6ec1f6a4f5ddeadb0b8b989c58327de19`: register `callback_state_order` as a supported executable class and map its invariant family through the live execution/readiness paths.
- `463d7d8e3dea6dddb75637703b527ee64debb3f3`: include `callback_state_order` in the canonical live runner class set.

## Findings

No confirmed finding from this live campaign.

## Next action

Dispatch the canonical workflow from `dogfood-readiness-expression-provenance` and inspect whether `H-CALLBACK-STATE-ORDER-runAction` is now Foundry-generated and executed. The next expected boundary is generic callback experiment input planning: the current experiment has `planned_inputs: []` while `runAction` has structured parameters, so the harness should fail closed and expose that missing generic argument-planning capability rather than inventing Hinkal-specific values. Classify the result only from execution evidence.

Canonical workflow:
https://github.com/Wonderadroit/Cydra_wonder/actions/workflows/cydra-live-contest.yml

## Automatic checkpoint format

After each canonical workflow run, the workflow updates the run/artifact/commit metadata in this file. Human/agent engineering changes should update the diagnosis and next-action sections.
