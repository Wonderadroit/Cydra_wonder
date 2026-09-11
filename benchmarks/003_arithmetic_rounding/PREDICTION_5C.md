# Benchmark 003 — Prediction 5C: Numerical Differential Classification

## Prediction

The existing CYDRA classifier can classify an arithmetic hypothesis from an `Evidence` object carrying structured runtime measurements, using the numerical differential rather than relying only on execution status.

For arithmetic evidence, the numerical rule is selected when:

1. `Evidence.payload` is populated;
2. `Evidence.source_verification` is populated with a verification tier; and
3. the payload contains the required arithmetic measurements: `observed`, `referenceValue`, and `patched`.

The numerical confirmation rule is:

```text
observed > referenceValue AND patched == referenceValue -> confirmed
```

The execution status fields remain secondary/contextual for this rule. In particular, a numerical differential must be sufficient to confirm even when the vulnerable/patched status values do not themselves produce the legacy `FAIL/PASS` differential.

For legacy boolean-outcome evidence with no measurement payload, the existing status-differential rule remains unchanged:

```text
vulnerable FAIL + patched PASS -> confirmed
vulnerable PASS + patched FAIL -> rejected
otherwise -> proposed
```

If neither a usable measurement payload nor the legacy status evidence is available, classification is `proposed`/unmeasurable according to the existing execution gate; no confirmation is permitted.

## Negative control

The negative-control arithmetic evidence contains the same populated measurement fields but no numerical violation:

```json
{
  "observed": 1,
  "referenceValue": 1,
  "patched": 1
}
```

Its execution statuses are deliberately `FAIL` for vulnerable and `PASS` for patched. A status-only classifier would confirm it; the numerical classifier must decline to confirm because `observed > referenceValue` is false.

## Positive control

The positive arithmetic evidence contains the runtime-transported measurements:

```json
{
  "observed": 2,
  "referenceValue": 1,
  "patched": 1
}
```

Its execution statuses are deliberately both `PASS`. The numerical classifier must still confirm because the measurement differential independently satisfies the arithmetic rule.

## Falsification boundaries

- Classifier confirms using status only while ignoring a populated arithmetic payload -> **FALSIFIED**.
- Classifier confirms when the payload has no numerical differential -> **FALSIFIED**.
- Classifier declines when the payload has the required numerical differential but status fields do not form `FAIL/PASS` -> **FALSIFIED**.
- Classifier confirms from a payload that was not execution-sourced -> **FALSIFIED**; the probe must consume the existing 5A-Transport-B runtime payload path and preserve its verification tier.
- Arithmetic requires a separate Evidence subtype or Evidence schema change -> **FALSIFIED**.
- Legacy authorization/initialization status-differential behavior changes -> **FALSIFIED**.
- Positive and negative controls classify according to their numerical measurements, with the same `Evidence` dataclass and no transport/schema change -> **CONFIRMED**.

## Scope of implementation

Only the classifier routing/semantic logic in `src/cydra/foundry.py` may change for the engine implementation.

The benchmark artifact may add one focused 5C probe/negative-control script under `benchmarks/003_arithmetic_rounding/` that:

- consumes the already-confirmed 5A-Transport-B measurement payload for the positive control;
- constructs the negative control with the same Evidence schema but no numerical differential;
- verifies positive numerical confirmation and negative numerical non-confirmation;
- verifies that legacy status-differential classification remains unchanged.

No changes to:

- `Evidence` schema;
- Foundry transport;
- filesystem permissions;
- arithmetic measurement generation;
- extraction rules;
- hypothesis schema;
- experiment schema/planner;
- Foundry generator;
- new classes or Evidence subtypes.

## Epistemic scope

A confirmation establishes numerical differential classification for the Benchmark 003 arithmetic measurement shape. It does not establish generality across all numerical invariants, arbitrary measurement schemas, or dynamic bytecode-level provenance.
