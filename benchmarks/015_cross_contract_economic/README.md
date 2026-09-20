# Benchmark 015 — cross-contract economic conservation

This benchmark deliberately starts as an extractor-blind historical-style regression.

The system has three contracts: an asset, a strategy, and a vault. The vault treats the strategy's reported harvest amount as newly backed assets. The strategy can return the requested amount while actually delivering less. The vault's internal accounting can therefore exceed the assets physically held by the vault.

The initial blind run is expected to produce no existing structural hypothesis. That is the learning signal: the mechanism is not a transferFrom mismatch, local arithmetic-rounding defect, or single-contract guard violation.

The intended system invariant is vault.accountedAssets <= asset.balanceOf(vault).

The vulnerability is cross-contract: the source of the claimed asset increment is Strategy, while the economic backing is held by Asset/Vault. The impact is economic: the vault can later release more assets than its actual backing permits.

This benchmark must not be treated as proof of a named historical exploit. It is a causal regression for CYDRA's ability to discover a previously unrecognized system-level mechanism.
