# CYDRA

**Evidence-first security research reasoning engine for authorized targets.**

> Understand systems rather than memorize vulnerabilities.
>
> **LLMs propose. Deterministic tools test. Evidence decides.**

## Current milestone: 0.1.0 — thin end-to-end pipeline

CYDRA can currently:

1. Parse a small Solidity target into a deterministic system model.
2. Extract functions, visibility, modifiers, state writes, external calls, and source locations.
3. Derive a first structural authorization invariant from protected administrative siblings.
4. Generate a structured hypothesis for an unprotected administrative operation.
5. Produce a discriminating experiment rather than declaring a vulnerability.
6. Preserve evidence provenance.

### First benchmark

`benchmarks/alchemix_missing_access_control/` is a minimal reconstructed fixture based on the public Alchemix Missing Access Control case documented by Immunefi. It is deliberately not copied production source.

The acceptance path is:

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
discriminating experiment
```

The benchmark does **not** claim exploit confirmation yet. Execution and causal verification are the next milestone.

## Run

```bash
python -m pip install -e .
pytest
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
