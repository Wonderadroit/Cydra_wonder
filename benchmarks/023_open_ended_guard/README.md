# Benchmark 023 — Open-ended guard discovery

This benchmark tests class-hidden blind selection on an unfamiliar Solidity target using only reasoning capabilities already present in CYDRA.

Target:
- repository: https://github.com/code-423n4/2025-05-blackhole.git
- revision: 92fff849d3b266e609e6d63478c4164d9f608e91
- source: contracts/GenesisPoolManager.sol

The benchmark does **not** pass a vulnerability class, target function, state surface, exploit sequence, or historical answer into `investigate()`. No new reasoning surface is added for this target.

The historical oracle is used only after CYDRA selects a hypothesis, to construct a causal control and score the blind result.

Required end state:
1. blind selector chooses the target mechanism;
2. real pinned target execution fails the security property;
3. causal control passes;
4. canonical causal verification is VERIFIED;
5. independent vulnerable reproduction fails;
6. independent patched reproduction passes;
7. finding gate is READY.

This is a benchmark of generalization from existing reasoning capabilities, not a claim of a newly discovered production vulnerability.
