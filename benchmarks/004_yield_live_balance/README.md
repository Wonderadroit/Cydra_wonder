# Benchmark 004 — Yield Protocol live-balance accounting

This benchmark is a minimal protocol-level reconstruction of the historical Yield Protocol logic error described by Immunefi. It is not production Yield source and is not a copied PoC.

The historical issue was that an invested Strategy `burn()` calculated redemption from the live pool-token balance, which an attacker could inflate by direct donation, instead of the cached accounting value. Immunefi's public bugfix review says the live-balance formula was exploitable by direct token transfer and that the patch changed the formula to use `poolCached_`. It reports approximately $950k at risk and a $95,000 USDC whitehat bounty.

## Locked prediction

`PREDICTION.md` was committed before implementation. The prediction required CYDRA to derive the cached-accounting invariant, generate the donation → redemption experiment, preserve execution measurements, and classify from the causal numerical differential rather than status alone.

## Result — CONFIRMED

CI run `34660725297` (Foundry 1.8.1) completed successfully.

CYDRA produced:

- `INV-ACCOUNT-001`
- `H-ACCOUNT-burn`
- `X-H-ACCOUNT-burn`

Execution:

- Foundry test: `PASS`
- tests run: `1`
- tests failed: `0`
- exit code: `0`

Structured execution evidence:

```json
{
  "donation": 100,
  "patchedCachedBefore": 200,
  "patchedLiveAfterDonation": 300,
  "patchedPayout": 100,
  "referencePayout": 100,
  "vulnerableCachedBefore": 200,
  "vulnerableLiveAfterDonation": 300,
  "vulnerablePayout": 150
}
```

The classifier confirmed because the executed evidence showed all required causal relationships:

`donation > 0` + `live balance > cached accounting` + `vulnerable payout > cached reference` + `patched payout == cached reference`.

### Controls

The same run also checked the routing behavior:

- negative accounting control: `FAIL/PASS` status pattern but no numerical differential → `proposed`;
- legacy status control: `FAIL/PASS` with no payload → `confirmed`.

Therefore the new accounting predicate fired on the measurements, declined the safe numerical case, and did not replace the legacy status path.

## Verification tier

Evidence is marked `static_plus_execution`. The benchmark verifies the generated runtime bindings statically and then obtains the actual measurements from executed Solidity through the permitted JSON file transport. It does not claim dynamic bytecode-level provenance.

## Architecture result

This is the first benchmark after Benchmark 003 to carry CYDRA through a real historical protocol failure reconstructed at the protocol level rather than a single arithmetic fixture. The result supports the narrower claim that CYDRA can carry a non-boolean, stateful accounting failure through model → invariant → hypothesis → experiment → execution → evidence → causal classification.

It does **not** establish general DeFi accounting coverage or arbitrary real-world vulnerability discovery.
