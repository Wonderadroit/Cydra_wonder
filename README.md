# CYDRA

**Evidence-first security research reasoning engine for authorized targets.**

> Understand systems rather than memorize vulnerabilities.
>
> **LLMs propose. Deterministic tools test. Evidence decides.**

## Current milestone: 0.1.0 — executable causal experiment

CYDRA currently has one complete reasoning slice:

1. Parse a small Solidity target into a deterministic system model.
2. Extract functions, visibility, modifiers, state writes, external calls, and source locations.
3. Derive a first structural authorization invariant from protected administrative siblings.
4. Generate a structured hypothesis for an unprotected administrative operation.
5. Generate a Foundry security test from that hypothesis.
6. Execute the same invariant test against vulnerable and patched controls.
7. Preserve structured execution evidence and update the hypothesis only when the differential result supports confirmation.

### Benchmark 001

`benchmarks/alchemix_missing_access_control/` is a minimal reconstructed fixture based on the public Alchemix Missing Access Control case documented by Immunefi. It is deliberately not copied production source.

The executable path is:

```text
Solidity fixture
    ↓
system model
    ↓
protected sibling comparison
    ↓
INV-AUTH-001
    ↓
H-AUTH-setWhitelist
    ↓
CYDRA-generated Foundry test
    ↓
vulnerable control: expected test failure
patched control: expected test pass
    ↓
structured execution evidence
    ↓
hypothesis update
```

The benchmark runner is `scripts/run_benchmark_001.py`. The GitHub Actions job executes the full path and treats the vulnerable test's failure as expected experimental evidence, not as a CI failure.

This is still **N=1**. It demonstrates executable causal verification for one invariant class; it does not demonstrate that CYDRA generalizes.

### Benchmark 005 — LiquidClaw initialization

Target: `Jc-asastu/liquidclaw-bsc@58bed220236e8cdd8d279ef7259b3298a71aac0b`.

Benchmark 005 is the first real-target end-to-end pipeline run. It exercised parse → model → invariant extraction → hypothesis generation → experiment planning → Foundry generation → interface resolution → stub generation → compilation → execution → structured extraction → evidence construction → classification across LiquidClaw Pool, Minter, and Voter.

| Target | Runtime | Internal status | Benchmark classification |
|---|---|---|---|
| Minter | PASS | rejected | **not_confirmed** |
| Voter | PASS | rejected | **not_confirmed** |
| Pool | PASS | rejected | **not_confirmed** |

The hypotheses were that an unauthorized caller could claim initialization state. Each generated test called the initializer from an unauthorized address and asserted revert. All three tests passed, so the hypotheses were rejected.

The classification was derived from runtime evidence. Forge JSON supplied the per-target `ExecutionResult`; an independent human-readable Forge run supplied the cross-check; and the integrity gate required all three signals to agree:

1. JSON test total == human-readable aggregate total.
2. JSON failed count == human-readable failed count.
3. JSON failure state agrees with the human-readable exit code.

The final run used Foundry 1.8.1 and completed with 3 tests passed, 0 failed, 0 skipped. Evidence is execution-derived, `static_plus_execution`, and the initialization evidence IDs are `E-EXEC-H-INIT-Minter-INITIALIZATION`, `E-EXEC-H-INIT-Voter-INITIALIZATION`, and `E-EXEC-H-INIT-Pool-INITIALIZATION`.

This benchmark establishes a working real-target pipeline and three true negatives for the initialization class. It does **not** establish bug-finding ability, generality, reasoning quality on unfamiliar targets, or precision/recall. It is evidence of pipeline correctness and negative-control precision, not a positive vulnerability-finding result.

Regression gate at commit `64d719c188c5463907e2185a6bfe2a527ed97be`:

- Benchmark 001: success.
- Benchmark 001 negative control: success.
- Benchmark 002: success.
- Benchmark 002 negative control: success.
- Benchmark 003: expected harness-boundary failure; this remains the intentional `NOT_REACHED` classifier boundary after arithmetic execution evidence, not a regression.

Benchmark 005 therefore closes the pipeline phase. Benchmark 006 begins the reasoning phase: testing whether CYDRA can produce useful hypotheses on a blind target it was not structurally selected around.

## Run

Python acceptance suite:

```bash
python -m pip install -e .
pytest
```

Foundry benchmark (requires Foundry and `forge-std`):

```bash
cd benchmarks/alchemix_missing_access_control/foundry
forge install foundry-rs/forge-std --no-commit
cd ../../..
PYTHONPATH=src python scripts/run_benchmark_001.py
```

## Architecture

```text
Target
  ↓
System Model
  ↓
Invariants
  ↓
Hypotheses
  ↓
Competing Hypotheses
  ↓
Information-Gain Test Planning
  ↓
Deterministic Tool Execution
  ↓
Evidence
  ↓
Hypothesis Update
  ↓
Causal Verification
  ↓
Finding Gate
```

See `PROJECT_BIBLE.md`, `ARCHITECTURE.md`, `DEVELOPMENT_PROTOCOL.md`, and `ROADMAP.md` for the governing design.
