# Benchmark 003 — Arithmetic Rounding

This is a deliberately minimal third-class fixture for CYDRA.

The invariant is numerical rather than control-flow based:

> A mint quote must not exceed the exact floor of `assets * SCALE / 997`.

The vulnerable fixture rounds upward; the patched control rounds downward. Solidity integer division truncates toward zero, so the differential is directly measurable in execution.

## Experimental rule

The fixture is not allowed to add an arithmetic-specific reasoning rule. The first run must use the existing `investigate()` pipeline unchanged. If extraction does not produce an arithmetic hypothesis, that is the recorded boundary of the current abstraction.

## Intended differential

For `assets = 1`, the exact floor is `1`, while the vulnerable ceiling implementation returns `2`.

The standalone Foundry test in `foundry/test/ArithmeticRounding.t.sol` proves that the fixture itself has the intended vulnerable/patched differential. Benchmark 003 then asks whether CYDRA can discover and represent that experiment through its existing reasoning pipeline.

## Falsification boundaries — committed before CI result

These meanings are fixed before observing the Benchmark 003 CI result. They must not be reinterpreted after the run.

| Prediction stage | If actual result is NO | Interpretation |
|---|---|---|
| Extraction | The invariant extractor does not identify the arithmetic invariant. | **Plugin/rule limitation, not schema failure.** A new extraction rule may be required; the structural schemas remain untested at this stage. |
| Hypothesis schema | The hypothesis object cannot express the arithmetic hypothesis, for example because it requires caller/privileged-function fields that do not apply. | **Schema failure.** This falsifies the claim that the existing hypothesis abstraction is shape-general. |
| Experiment schema | The experiment object cannot represent an arithmetic test, for example because it assumes expected-revert semantics instead of equality/inequality semantics. | **Schema failure.** The experiment abstraction is narrower than claimed. |
| Evidence schema | The evidence object cannot record numerical assertion evidence, for example because it can only represent status/pass-fail and cannot preserve a numerical delta or equivalent observation. | **Evidence-schema limitation.** Potentially a smaller field-level extension, but still a schema failure for the no-change prediction. |
| Classifier | The differential classifier cannot classify arithmetic evidence using the same causal/differential rule, for example because it requires the vulnerable side to revert. | **Classifier failure.** Whether this is a rule-level or schema-level limitation depends on the observed implementation path. |

### Observation discipline

A NO is recorded exactly at the first stage where it occurs. Later stages are not retroactively marked PASS because an earlier stage failed to produce input for them. `NOT_REACHED` means the experiment did not supply that stage with a valid predecessor artifact; it is not evidence that the stage itself passed or failed.

No reasoning-engine or schema change is permitted while observing the first CI result. The required sequence is:

1. Observe the CI result.
2. Record the actual behavior and generated artifacts.
3. Compare actual behavior against the five locked predictions.
4. Identify the first mismatching stage and classify it using the table above.
5. Only then decide whether a code change is justified.

## Clean-pass boundary

A clean pass would establish only that the current abstraction can represent an invariant whose evidence shape is **numerical drift rather than revert/no-revert control flow**.

It would **not** establish generality to:

- economic invariants where the relevant participant is an economic position/profit state rather than merely a caller;
- cross-contract invariants where the system model must represent relationships spanning multiple targets;
- time-series/state-evolution evidence where the assertion concerns behavior across observations rather than a single end-state.

Therefore a clean Benchmark 003 result must not be summarized as "CYDRA's architecture generalizes." The defensible claim is narrower: **CYDRA's current abstraction generalizes to the tested arithmetic shape.**

## CI observation checklist

When the run completes, inspect the artifacts rather than treating a green workflow as sufficient:

1. **Extraction:** Did an arithmetic invariant actually fire (for example, an `INV-ARITH-*` invariant), or did the fixture merely execute without extraction?
2. **Hypothesis:** Does the produced hypothesis contain meaningful arithmetic fields, or is it an otherwise empty control-flow hypothesis with an `arithmetic` label?
3. **Experiment:** Does the generated Foundry test assert an arithmetic relationship such as equality/inequality or a numerical delta? An `expectRevert`-only test is not evidence of an arithmetic experiment.
4. **Evidence:** Does the evidence preserve the numerical observation/delta or an equivalent structured value, rather than only a generic `FAIL`/`PASS` status?
5. **Classifier:** Did classification use the existing differential causal rule, or did a Benchmark-003-specific classifier path silently appear?

A green CI result is therefore necessary but not sufficient for calling the five predictions correct.

## Prediction 5A — measurement production

Prediction 5A was **FALSIFIED** at the transport boundary. The generated Solidity test computed the runtime values and emitted `CydraMeasurement(observed, reference, patched, delta)`, but the initial measurement-production decoder did not receive a structured execution payload. Evidence and classifier remained `NOT_REACHED`.

## Prediction 5A-Probe — Foundry event transport

The probe was locked before execution to distinguish four outcomes:

- **State A — STRUCTURED_JSON:** `--json` exposes the event as structured data.
- **State B — HUMAN_READABLE_ONLY:** the event is exposed by `-vv/-vvv/-vvvv`, but not as structured JSON.
- **State C — NOT_EXPOSED:** none of the tested invocations exposes the event.
- **State D — SEMI-STRUCTURED JSON:** `--json` contains the event, but only as an unparsed text/string blob rather than structured numeric fields.

### CI result — Run 34

GitHub Actions run `34655496942` executed the Benchmark 003 workflow with PR head SHA `089aa319de91d5e46a2bc01c7d48121ec3970ec5`. The PR workflow checked out merge commit `4115a76296ee44485868867abd8f1f43a0f01b22`, whose merge commit message explicitly records `089aa319de91d5e46a2bc01c7d48121ec3970ec5`; the benchmark job completed the acceptance suite and standalone arithmetic differential before reaching the intentional probe boundary.

Foundry version was `1.8.1` (`982849d3140c01fd3b72905759581a132df7aa98`). The probe reported:

```json
{
  "classification": "HUMAN_READABLE_ONLY",
  "structured_json_event": false,
  "human_readable_event_variants": ["vv", "vvv", "vvvv"]
}
```

Per invocation, the machine-readable probe artifact reported:

| Invocation | Exit code | Event visible | Structured JSON | Structured event |
|---|---:|---|---|---|
| `forge test --match-path test/CydraArithmeticInvariant.t.sol --json` | 1 | true | false | false |
| `forge test --match-path test/CydraArithmeticInvariant.t.sol -vv` | 1 | true | false | false |
| `forge test --match-path test/CydraArithmeticInvariant.t.sol -vvv` | 1 | true | false | false |
| `forge test --match-path test/CydraArithmeticInvariant.t.sol -vvvv` | 1 | true | false | false |

The probe therefore classifies the transport as **State B — HUMAN_READABLE_ONLY**: the event is exposed by the tested verbose human-readable interfaces, while the `--json` path does not expose it as a structured event. The artifact does not establish State A or State D because the probe explicitly reports `structured_json=false` and `structured_event=false` for `--json`.

The workflow's red conclusion is an intentional harness boundary stop (`exit_code 1`), not a Foundry test failure. The downstream stages were explicitly `NOT_REACHED`:

- measurement production: `NOT_REACHED`
- evidence schema: `NOT_REACHED`
- classifier: `NOT_REACHED`

### Epistemic consequence

Prediction 5A-Probe is **CONFIRMED** for State B. The current event transport is available through Foundry's verbose human-readable output, but not through the tested structured JSON interface. This does **not** yet justify changing CYDRA's transport or Solidity measurement mechanism. Any transport-mechanism change must be introduced under a separate prediction rather than bundled into the probe result.

## Prediction 5A-Transport-A — File-mediated transport constraint

Before locking Prediction 5A-Transport-A, the file-mediated transport mechanism was probed against the existing generated arithmetic test without modifying the fixture's `foundry.toml`.

The mechanism under test was `vm.writeFile`.

Two consecutive post-generator-fix probes produced identical results:

- `cheat_code_used`: `vm.writeFile`
- `invoked_successfully`: `false`
- `fs_permissions_required`: `true`
- `fs_permissions_declared`: `false`
- `file_written`: `false`
- `file_content_readable_by_python`: `false`
- `file_content_shape`: `not_readable`
- `ffi_required`: `false`
- `ffi_enabled`: `false`

The failure was caused by Foundry filesystem permission enforcement: the write path was not authorized by `foundry.toml`.

This establishes a configuration constraint, not fundamental unavailability of `vm.writeFile`.

For the controlled Benchmark 003 fixture, the constraint is satisfiable by modifying its `foundry.toml`.

For real target projects, availability is target-conditional because CYDRA cannot assume that the target's Foundry configuration grants filesystem write permission.

The probe was repeated after the generated event parameter was changed from `reference` to the compiler-neutral `referenceValue`. All tested fields matched across both runs.

No Evidence schema, classifier, or transport abstraction was changed during this observation.

### forge-std fixture dependency limitation

The Benchmark 003 fixture currently depends on `forge-std` being installed by the CI workflow rather than being vendored in the fixture. This is an environment dependency, not a fixture property. If the fixture is run outside this workflow, `forge-std` must be installed separately. This limitation is recorded so that the minimum-scope result is not attributed to a fully self-contained fixture.

The minimum-scope transport experiment therefore tests file-mediated transport under the controlled workflow environment, with the fixture's `foundry.toml` providing the filesystem permission scope. It does not yet claim that the fixture is independently reproducible without an external `forge-std` installation.
