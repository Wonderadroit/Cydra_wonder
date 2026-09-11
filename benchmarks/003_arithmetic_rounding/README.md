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
