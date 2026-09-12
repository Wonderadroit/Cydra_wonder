# Benchmark 003 — Prediction 5A-Probe: Foundry Event Transport

## Prediction

The next probe will determine which Foundry execution interface, if any, exposes the `CydraMeasurement(...)` event emitted by the generated arithmetic test without requiring human-readable stdout parsing.

The probe will compare independent invocation paths:

- `forge test --json`
- `forge test -vv`
- `forge test -vvv`
- `forge test -vvvv`

The probe does not change CYDRA's Evidence schema, classifier, arithmetic generator semantics, or measurement representation. It only observes Foundry's available execution interfaces.

## Source of truth

The source of truth remains the executed Solidity test. The probe must not calculate the expected arithmetic values in Python and must not modify the generated Solidity to hard-code measurements.

## Interpretation

| Observed interface | Interpretation |
|---|---|
| `--json` structurally exposes the emitted event/data | Structured event transport is available; Prediction 5A's transport failure was invocation/decoder-specific and is fixable without redesigning Interface A |
| Only `-vv`, `-vvv`, or `-vvvv` exposes the event | Foundry exposes the event only through human-readable output for this invocation; event transport is stdout-coupled and cannot satisfy the strict structured transport requirement |
| JSON trace output structurally exposes the event | Structured but indirect transport exists; next step is trace extraction rather than stdout parsing |
| No tested Foundry interface exposes the event | Event transport cannot satisfy Interface A through these Foundry interfaces; a different transport mechanism is required |
| Multiple structured interfaces expose it | Prefer the least output-format-coupled structured interface and record the alternatives |

## Failure boundary

A human-readable event line appearing in stdout is evidence that Solidity emitted the event, but it is **not** a structured transport result.

The probe therefore reports event visibility separately from structured JSON availability.

## Constraint

This is an external-tool interface probe. No conclusion about CYDRA's general Evidence or classifier abstractions is permitted from this probe.
