# Benchmark 003 — Prediction 5A-Transport-A

## Prediction

With `fs_permissions` granted for the write path in the Benchmark 003 fixture's `foundry.toml`, and with no other changes to the measurement-producing Solidity logic, the file-mediated transport probe will produce:

- `invoked_successfully: true`
- `file_written: true`
- `file_content_readable_by_python: true`
- `file_content_shape: "structured_json"`

The file content is hypothesized to be produced by executed Solidity and to contain at least the three runtime-derived measurements required by the experiment:

- `observed`
- `referenceValue`
- `patched`

Whether `delta` is included is a separate observation. If Solidity emits it, it is a reported runtime value. If Python derives it downstream, it is a computed value. The presence or absence of `delta` is therefore not a pass/fail criterion for the transport mechanism.

Python may read and decode the resulting file, but must not independently calculate or reconstruct the three measured values.

## Falsification boundaries

### CONFIRMED — transport available

All four required transport fields are satisfied and the file contains structured JSON produced by the current Solidity execution. The structured JSON contains at least the three runtime-derived measurements above.

### FALSIFIED — text-coupled

`invoked_successfully=true` and `file_written=true`, but `file_content_shape="unstructured_text"`.

### FALSIFIED — write without content

`invoked_successfully=true`, `file_written=true`, but `file_content_shape="empty"`.

### FALSIFIED — file not created

`invoked_successfully=true`, but `file_written=false`.

### FALSIFIED — invocation failure

`invoked_successfully=false`.

In this case the failure must be classified using the recorded permission/error fields rather than interpreted as an arithmetic or Evidence-layer failure.

### FALSIFIED — Python cannot read transport

The Solidity execution successfully writes the file, but Python cannot read it.

### FALSIFIED — stale-file contamination

A pre-existing file satisfies the read condition without being written by the current execution.

The probe must therefore remove any previous probe file before execution and verify that the file content contains a run-specific marker produced by the current Solidity execution.

## Scope

This prediction applies to the controlled Benchmark 003 fixture.

It does not establish that file-mediated transport is universally available for real Foundry targets. Real targets are target-conditional because their `foundry.toml` may not grant CYDRA filesystem write permission.

## Non-goals

This prediction does not test:

- Evidence schema generalization
- classifier generalization
- arithmetic transport abstraction
- downstream finding classification
- Python reimplementation of the arithmetic invariant

Those remain unreached until measurement transport succeeds.

## Source-of-truth requirement

The numerical values must originate from executed Solidity.

Parsing generated Solidity source is invalid.

Parsing human-readable Foundry output is invalid.

Recomputing the arithmetic in Python is invalid.

The transport is successful only if the runtime-produced measurements cross the Solidity/Python boundary through the file as structured data.
