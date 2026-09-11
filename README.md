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
