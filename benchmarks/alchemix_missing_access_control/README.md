# Benchmark 001 — Alchemix Missing Access Control

## Purpose

This is the first CYDRA end-to-end benchmark. It is a **minimal reconstructed fixture**, not a copy of the historical production source.

The public Immunefi material records an Alchemix access-control case in July 2021: an arbitrary user could call `setWhitelist()` and thereby obtain the ability to call the `harvest` function. Immunefi's public PoC repository lists the case as **Alchemix Missing Access Control**, with the corresponding PoC test path `test/Alchemix/PoCNoAccessControl.t.sol`.

Sources:

- Immunefi Web3 Security Library — BugFixReviews: https://github.com/immunefi-team/Web3-Security-Library
- Immunefi public PoC repository: https://github.com/immunefi-team/bugfix-reviews-pocs

## Benchmark target

The fixture preserves the reasoning pattern:

1. `setGovernance()` is a privileged administrative state transition protected by `onlyGov`.
2. `setWhitelist()` mutates authorization state but has no equivalent protection.
3. CYDRA should model both functions.
4. CYDRA should infer the authorization invariant from the protected sibling.
5. CYDRA should generate a hypothesis specifically against `setWhitelist()`.
6. CYDRA should plan an experiment using an unprivileged caller.

## Acceptance result

The first pipeline passes this benchmark when it produces:

- a system model containing both functions;
- `INV-AUTH-001` for privileged state-changing operations;
- hypothesis `H-AUTH-setWhitelist`;
- an experiment that distinguishes missing authorization from protection elsewhere;
- source-linked evidence for `setWhitelist()`.

This benchmark is intentionally narrow. It proves the pipeline can move from **code structure → invariant → hypothesis → discriminating experiment**. It does **not** yet claim exploit confirmation. That requires the Phase 3/4 execution layer.
