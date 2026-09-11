# Prediction 5A-Transport-B — File-mediated measurement payload

## Prediction

With the same minimum filesystem permission scope established by Prediction 5A-Transport-A, the generated arithmetic test will use `vm.writeFile` to write a structured JSON payload containing runtime measurements produced by executed Solidity.

The expected payload must include at least:

- `observed`
- `referenceValue`
- `patched`
- `run_marker`

`run_marker` must be fresh for the current execution so stale-file contamination cannot satisfy the prediction.

The measurement values must originate from the executed Solidity calls:

- `observed` from `vulnerable.quoteMint(assets)`;
- `patched` from `patchedTarget.quoteMint(assets)`;
- `referenceValue` from the Solidity reference calculation `(assets * vulnerable.SCALE()) / 997` (or an equivalent reference expression executed in Solidity).

Python may read and decode the resulting JSON, but it must not calculate or reconstruct the measurement values independently.

## Fixed transport constraint

The filesystem scope is fixed at the minimum scope already confirmed:

```toml
[[profile.default.fs_permissions]]
access = "read-write"
path = "./cydra_file_transport_probe.json"
```

Do not broaden this to `path = "."` for this prediction.

## Source-of-truth requirement

The transport only satisfies this prediction if the values written to the JSON file are runtime values produced by executed Solidity. The following do **not** satisfy the prediction:

- Python recomputing `(assets * SCALE) / 997`;
- Python reading generated Solidity source and extracting expected values;
- Python parsing human-readable Foundry output;
- Solidity writing hard-coded values such as `2`, `1`, and `1` instead of values returned by the executed contracts/reference calculation;
- copying values from the event transport path rather than writing them directly as structured JSON from the executed test.

The file is the sole measurement transport boundary Python is allowed to consume.

## Falsification boundaries

| Observation | Classification |
|---|---|
| Fresh file contains structured JSON with `observed`, `referenceValue`, and `patched`, and all three values originate from executed Solidity expressions/calls | **CONFIRMED — measurement payload transported** |
| File exists and is structured JSON but contains only `run_marker` or otherwise lacks the required measurement fields | **FALSIFIED — transport channel works, measurement payload does not** |
| File is structured JSON with required field names but values are Solidity/Python literals or generator-derived predictions rather than runtime observations | **FALSIFIED — reported/predicted values, not executed measurements** |
| File contains required values but Python obtains them through source parsing or human-readable Foundry output rather than the JSON file | **FALSIFIED — wrong transport/source of truth** |
| File content is unstructured text | **FALSIFIED — text-coupled payload transport** |
| File is stale or `run_marker` does not match the current execution | **FALSIFIED — stale artifact contamination** |
| `vm.writeFile` cannot execute because of a non-permission harness/environment failure | **UNMEASURABLE — transport boundary not reached** |
| `vm.writeFile` is rejected specifically because the already-confirmed minimum file-level permission is insufficient | **FALSIFIED — minimum scope is insufficient; do not infer directory scope until a separate prediction** |

## Delta handling

`delta` is not a required pass/fail field for this prediction. If Solidity writes a `delta` value, Python must report it as transported runtime data. Python must not derive it independently for the purpose of satisfying the prediction.

## Scope of claim

A clean confirmation establishes only that the confirmed file-mediated channel can transport the tested arithmetic runtime measurement payload under the controlled Benchmark 003 configuration.

It does not establish Evidence-schema generalization or numerical classifier generalization. Those remain separate predictions and separate experimental boundaries.

The fixture's `forge-std` dependency remains a separate environment limitation: the current workflow installs `forge-std` into the benchmark's `foundry/lib/` at CI time. This prediction does not claim that the committed fixture is independently runnable without that external installation step.
