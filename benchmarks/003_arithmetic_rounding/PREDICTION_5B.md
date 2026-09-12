# Prediction 5B — Evidence schema generalization

Prediction 5B is locked before implementation and CI observation.

## Prediction

After the smallest Evidence-schema extension, an arithmetic execution evidence object will carry the structured runtime payload `{observed, referenceValue, patched}` from the confirmed file transport without introducing an arithmetic-specific Evidence subtype and without changing the classifier.

The shared `Evidence` dataclass will remain the single schema for authorization, initialization, and arithmetic evidence. The arithmetic case will differ only in which optional fields are populated, not by using a different object type or class-specific field shape.

## Verification-tier field

The Evidence schema will carry an explicit `source_verification` field so downstream consumers do not have to infer provenance strength from the presence of numeric values alone.

The Benchmark 003 arithmetic artifact uses the tier:

`static_plus_execution`

This means the generated source structurally verifies that the measurement variables are assigned from the intended vulnerable/patched contract instances and reference calculation, and the generated test executes with passing assertions. It is **not** a claim of dynamic EVM-level provenance.

The field is part of the shared Evidence schema and therefore exists for all Evidence objects. Existing authorization and initialization evidence may leave it unset when no execution-source verification tier is being asserted.

## Concrete shape test

All three classes must instantiate the same `Evidence` dataclass with the same schema fields:

| Class | kind | payload | source_verification |
|---|---|---|---|
| Authorization | `model`/`execution` as applicable | `None` unless structured observations exist | unset unless explicitly verified |
| Initialization | `model`/`execution` as applicable | `None` unless structured observations exist | unset unless explicitly verified |
| Arithmetic | `execution` | `{observed, referenceValue, patched}` | `static_plus_execution` |

The test is about schema identity, not identical populated values. Authorization and initialization must not acquire arithmetic-specific fields or subclasses merely because arithmetic now has a payload.

## Falsification boundaries

- Payload field cannot be added without subclassing `Evidence` → **FALSIFIED — schema is class-bound.**
- Payload field exists but arithmetic evidence leaves it empty → **FALSIFIED — population path is broken.**
- Payload field is populated but requires a different payload shape/type for arithmetic than the shared Evidence schema permits → **FALSIFIED — schema is class-bound despite appearing unified.**
- Authorization, initialization, and arithmetic evidence require different Evidence object types or different required field sets → **FALSIFIED — shared schema does not generalize.**
- `source_verification` cannot be represented without an arithmetic-specific field/subtype → **FALSIFIED — verification metadata is class-bound.**
- Arithmetic payload is populated correctly and all three classes use the same Evidence dataclass/schema → **CONFIRMED.**

## Scope

A clean confirmation establishes only that the shared Evidence abstraction can preserve the tested arithmetic measurement payload and an explicit verification tier alongside the existing authorization/initialization evidence shape.

It does not establish numerical classifier generalization, dynamic provenance, or generality to other measurement classes.

No classifier changes, no transport changes, no filesystem-scope changes, and no new Evidence subclasses are permitted while observing this prediction.
