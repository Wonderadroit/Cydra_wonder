# Benchmark 004 — Yield Protocol live-balance accounting

This benchmark is a minimal protocol-level reconstruction of the historical Yield Protocol logic error described by Immunefi. It is not production Yield source and is not a copied PoC.

The historical issue was that an invested Strategy `burn()` calculated redemption from the live pool-token balance, which an attacker could inflate by direct donation, instead of the cached accounting value. Immunefi reports that the fix changed the formula to use `poolCached_`. The public bugfix review states that approximately $950k was at risk and that Yield Protocol paid a $95,000 USDC bounty. citeturn2view0

## What CYDRA must discover

The fixture exposes the protocol relationship rather than a single arithmetic function:

- pool token balances are externally transferable;
- strategy shares are backed by cached pool accounting;
- an unsolicited token donation changes live balance without changing the cache;
- redemption must not let that donation increase the payout to the redeemer.

The benchmark therefore asks CYDRA to cross the full path:

```text
protocol model
  ↓
cached-accounting invariant
  ↓
hypothesis
  ↓
donation → redemption experiment
  ↓
executed vulnerable/patched controls
  ↓
structured measurements
  ↓
accounting differential classifier
  ↓
confirmed / proposed
```

## Run

```bash
cd benchmarks/004_yield_live_balance/foundry
forge install foundry-rs/forge-std --no-commit
cd ../../..
PYTHONPATH=. python scripts/run_benchmark_004.py
```

The CI workflow installs `forge-std` inside this fixture for the same reason as Benchmark 003: the benchmark remains small and its dependency installation is kept separate from CYDRA's Python package.

## Scope

A confirmation means CYDRA reproduced this one historical protocol-level causal failure in a controlled reconstruction. It does not prove general DeFi accounting coverage or arbitrary vulnerability discovery.
