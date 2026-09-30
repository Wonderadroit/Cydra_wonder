# CYDRA Live Dogfood State

> This file is the durable checkpoint for live-target work. It is intentionally short enough for a new agent to read first and detailed enough to reconstruct the current state.

## Mission

Live-target dogfooding only. Pinned target: Hinkal public-code target.

## Frozen target

- Repository: `Hinkal-Protocol/Hinkal-Contracts-Circuits`
- Commit: `61b6839aa80fc0c33bfdcde0323753c83cb2ce67`

## Current CYDRA branch

- Branch: `dogfood-readiness-expression-provenance`
- Current engineering head: `0d1280c383910f20d9e72ea16ad8ed352259e94f`

## Latest validated live run

- Workflow: `CYDRA canonical live-target dogfood`
- Run: `36750700158`
- Artifact: `11113888699` (cydra-live-hinkal-fe2b81167e3fccfe86f1dccc09e14c86dfc12fce)
- Artifact URL: https://api.github.com/repos/Wonderadroit/Cydra_wonder/actions/artifacts/11113888699/zip
- Artifact digest: `sha256:8a916eed6e99622a07c325dfbc34d267c6ee519c504750b13811201ed1d5fe6a`

## Last observed pipeline boundary

The previous live artifact showed false execution-readiness blockers:

- Solidity `abi.decode` was incorrectly treated as a runtime dependency — repaired.
- Deterministic casts such as `bytes4(op.callData)` and `int256(...)` were still being reclassified as unresolved producer dependencies — generic repair added.
- `utxoSet.skipLast` was treated as an external runtime dependency — generic local-value classification added.

The latest readiness validation run (36182788690 / artifact 10884960775) confirms the readiness repair worked:
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

## Current repair in progress

The structured-input planner is now live-validated: the latest artifact contains a complete two-argument vector for `runAction`. The caller-prerequisite layer then exposed two generic implementation defects in its initializer-call rewriter: the whitespace terminator regex was over-escaped, and the replacement path referenced a nonexistent `match` variable. Those defects were repaired, but the latest live artifact exposed a third generic issue: the generated initialization lifecycle used Solidity `try target.initialize(...) {}` syntax, while the rewriter only accepted semicolon-terminated calls. The rewriter now preserves either `;` or `{` and has a regression test for try-call syntax.

The generic caller-prerequisite layer is now being refined around the authorization boundary:
- `src/cydra/caller_prerequisite.py` reuses the existing initialization generator and proxy topology;
- it discovers an initializer/reinitializer from the model rather than naming a Hinkal function;
- it only binds the attacker into semantically identified caller-identity parameters such as allowed/recipient/account collections;
- it runs the target call after target-provided initialization and emits prerequisite evidence only when Foundry actually executes and passes;
- `scripts/run_benchmark_blind.py` applies that evidence through the existing fail-closed prerequisite graph.

No Hinkal-specific selector, address, setup bypass, or target-specific workaround was added. Regression coverage is in `tests/test_caller_prerequisite.py`.


### Latest canonical run: 36259368563 / artifact 10911264183

The canonical workflow completed operationally, but the caller-prerequisite experiment was **UNMEASURABLE** because the generated Solidity harness from the prior repair had two generic generator defects: it emitted a Python-only helper name into Solidity, and its `unauthorized` local collided with an initializer-generated declaration. The security hypothesis remained `NOT_REACHED`; this was not evidence against Hinkal.

Generic repair at CYDRA commit `94eb961e5a8604db7edf432d506da13a6235a764`:
- generated caller variables now use collision-resistant harness-local names;
- the authorization-boundary comparison is emitted entirely as Solidity-native logic;
- the Python observation helper remains only as testable Python logic and is not referenced by generated Solidity.

Next action: rerun the same canonical Hinkal workflow against target commit `61b6839aa80fc0c33bfdcde0323753c83cb2ce67`. Do not move to another capability until this generated-harness blocker is cleared.

The latest caller-role probe exposed an important boundary error: it treated successful completion of the entire target function as proof that the caller authorization requirement was satisfied. On the pinned Hinkal target, an authorized caller can pass `onlyAllowedRecipient` and still hit later `runAction` execution predicates, so a full-call revert is not sufficient to classify the caller role as unresolved. The probe now compares an unauthorized call with the same authorized call: unauthorized must fail, and the authorized call either succeeds or produces a different revert payload, demonstrating progress beyond the authorization failure. Identical revert payloads fail closed. Regression coverage was added for all four observation cases.


## Current callback execution repair

The latest canonical artifact proved the caller prerequisite is now verified. The remaining callback blocker was not caller authorization; it was execution-readiness treating adapter-satisfiable path guards as hard environment prerequisites. The adapter has now been extended to:

- discover a target-local \`abi.decode\` value feeding an indexed operation;
- discover the operation's external-call endpoint and call-data fields from source provenance;
- construct a one-operation decoded payload with the callback actor as endpoint and zero call value;
- deploy the callback actor before constructing the encoded target input, avoiding an address/data circularity;
- keep the outer target invocation payload separate from the reentry payload;
- reuse the canonical initializer/caller binding machinery;
- reuse proxy initialization topology when the implementation disables direct initialization.

No Hinkal function name, selector, address, or interface was added to CYDRA. The adapter remains fail-closed when the target does not expose this generic decoded-call shape.

Engineering commits in this repair cluster: \`d41b1ebcb301ec81871e5292ceb2b8c96807095d\`, \`d62862748f95fe3c0feaaa71bf2f6f8b998a53ab\`, \`6f0e4ab5f0977dc2bb8624e3aa51a99bff00731b\`, \`7bd36e3ee50aaf380b38234c4f31d968918af226\`, \`8bffca48e347fc8352b2d4e6c3376cd9631ffbd8\`, \`d8926c51c4bdaa830b27e55e14b46e2\`, \`1320d31a50eb7bb321ce9c03d5744b3d80d54faf\`, \`1e531272320902bdbd4ff44e4a57c270e4319560\`.

Validation status: **partially live-validated**. Artifact `10912247113` proved deterministic execution predicates now become constraints, but `success` remained blocked because its modeled producer is a selected external member-call branch. The next generic repair recognizes adapter-selected external member-call outcomes; it is not yet live-validated. The repair keeps ordinary call-derived/state prerequisites fail-closed, but lets the callback adapter own only deterministic local guards and discovered external-call outcomes. Do not treat the callback hypothesis as executed until the same canonical Hinkal workflow produces a new artifact and Foundry evidence.

## Next action

Run the canonical Hinkal workflow from \`dogfood-readiness-expression-provenance\` at head \`1e531272320902bdbd4ff44e4a57c270e4319560\`. Inspect the generated callback test first. If it compiles and reaches \`callbackObserved\`, then classify the reentry outcome from evidence; if generation/compilation fails, fix that generic failure before touching the hypothesis semantics.


CI must validate this caller-prerequisite rewriter fix first. The latest live artifact was generated from `5d167035880c6d0b21fade3eca1e1024e492ace7`, so it genuinely tested the previous repair. After CI validation, dispatch the same canonical Hinkal workflow from `dogfood-readiness-expression-provenance`. If the probe cannot establish the caller role because later target execution predicates are not yet satisfiable, that failure is evidence of the next generic prerequisite gap; do not mark the role verified or bypass it.

Canonical workflow:
https://github.com/Wonderadroit/Cydra_wonder/actions/workflows/cydra-live-contest.yml

Canonical workflow:
https://github.com/Wonderadroit/Cydra_wonder/actions/workflows/cydra-live-contest.yml

## Latest canonical diagnosis: artifact 10913265831 / run 36263372926

The callback harness is now self-contained: the prior custom initializer type/import blocker was cleared by preserving lifecycle initializer imports. The callback harness compiles and executes, but the initial runAction call reverts before the callback is observed.

The live artifact established the next generic capability gap: runAction calls the modeled internal verifyWallet function, whose own execution guards were absent from the caller readiness graph. The compiler-backed model identifies verifyWallet requirements including used-message state, signature verification, deadline validity, and fee-bound validity. The callback adapter must not bypass these prerequisites.

Generic repair: src/cydra/execution_readiness.py now discovers modeled internal calls from source and propagates the callee's execution/state predicates into the caller readiness graph as unresolved internal_execution_predicate / internal_state_predicate requirements. This is fail-closed and bounded; it does not invent target-specific inputs. Regression coverage was added in tests/test_execution_readiness.py.

Engineering commits: 08b385ad3951166f8aec96ebcd3bbc1797823fac and a76ebbe91bb8c25b218b426038cef83db71450ee.

No confirmed Hinkal finding exists. The next canonical run should verify that the callback experiment is no longer generated against an unsatisfied internal prerequisite and that the readiness report names the propagated verifyWallet requirements. If the next blocker is signature/proof construction, implement only the generic capability needed to represent and verify that prerequisite; do not add Hinkal-specific constants or bypasses.

## Latest canonical diagnosis: artifact 10926452747 / run 36303694958

The canonical live workflow completed successfully on CYDRA commit `b239035c7575355dacb8e485a92060790064ec9a`. Initialization and caller-prerequisite evidence passed, and the callback readiness graph propagated the internal `verifyWallet` requirements. However, the ERC-7201 `$.usedMessages[circomData.emporiumMessage]` prerequisite remained `state_observation / unresolved`, so the callback security experiment was not reached.

Diagnosis: the new generic namespaced-state planner contained an over-escaped `_FIELD_RE`, so Solidity struct fields were not parsed. This was a CYDRA parser defect, not Hinkal evidence.

Generic repair: commit `35c25d1302046cfc16fbe188062cb28c23ea4050` corrects the regex to parse mapping/ordinary struct fields. Existing positive/negative planner regressions already cover successful ERC-7201 mapping-slot derivation and fail-closed packed layouts.

Next action: validate this repair in CI, then rerun the same canonical Hinkal workflow. Expected transition: `verifyWallet: $.usedMessages[circomData.emporiumMessage]` from `state_observation / unresolved` to `state_observation / constraint`. Only after that should the generated callback experiment be inspected/executed.

## Automatic checkpoint format

After each canonical workflow run, the workflow updates the run/artifact/commit metadata in this file. Human/agent engineering changes should update the diagnosis and next-action sections.


## Exploration frontier integration

The generic recursive exploration layer is now persisted in every canonical source freeze as `exploration-state.json`.

- `ExplorationState.from_investigation()` derives the frontier from the existing model/hypotheses/experiments/evidence.
- Proposed hypotheses with executable experiments are prioritized by information-gain-per-cost.
- Functions and state surfaces without hypothesis coverage remain explicit unresolved questions.
- The frontier is budget-bounded and fail-closed; it does not invent vulnerabilities or bypass readiness.

Current status: **implemented and artifact-wired, not yet exercised by a new canonical Hinkal run**.

Next action: validate the new module and freeze wiring, then run the same canonical Hinkal workflow. Inspect `exploration-state.json` first and use the live artifact to identify the next missing generic capability.


### Latest exploration-controller state
The frontier now has a generic bounded recursive controller and an evidence-feedback bridge. It has regression coverage but has not yet been exercised through the live canonical Hinkal workflow. Next action: wire the existing canonical execution callback into one bounded exploration round, then rerun the same target and inspect the resulting exploration history.
