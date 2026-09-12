# Benchmark 005 — Prediction 5C: System-Model Enrichment

## Locked prediction

**Prediction 5C-SystemModel-Enrichment:** Extending the Solidity system model to extract constructor signatures, function parameter types (names and declared ABI-facing types), and inline authorization predicates from function bodies will enable the initialization generator to produce Foundry tests that compile against the three LiquidClaw initializers.

This prediction is scoped to **Group A — syntactic extraction** only. It does not predict execution, test success, vulnerability confirmation, or semantic correctness of initialization arguments/post-conditions.

## Regression precondition

The enrichment is additive. It adds new fields to `FunctionModel` and `ContractModel` without removing or renaming existing fields. Existing extraction behavior for `name`, `visibility`, `modifiers`, `writes`, `external_calls`, and `line` must remain unchanged. If any existing field's behavior changes, that is a regression, not an enrichment.

Benchmarks 001–004 are the precondition gate. If any fixture produces a different hypothesis, experiment plan, or classification after enrichment, the run stops before LiquidClaw and the enrichment is treated as regressed.

## LiquidClaw compilation gate

For Pool, Minter, and Voter, record:

| Contract | Constructor captured | Parameters captured | Inline predicate captured | Generator output | Foundry compile |
|---|---|---|---|---|---|
| Pool | pending | pending | pending | pending | pending |
| Minter | pending | pending | pending | pending | pending |
| Voter | pending | pending | pending | pending | pending |

Compilation is the only LiquidClaw gate in this prediction. Do not execute the generated tests in this session.

## Falsification conditions

1. Generator emits a test referencing `target.guardian()` → **FALSIFIED**.
2. Generator emits `new Minter()` with no constructor arguments → **FALSIFIED**.
3. Generator emits `initialize(attacker)` with the wrong arity → **FALSIFIED**.
4. Generated tests compile for all three initializers → **CONFIRMED**.

## Boundary interpretation

- **Captured = no:** extraction boundary failed; remain within Group A.
- **Captured = yes, compile = no:** model-to-generator boundary failed; examine the interface without modifying reasoning or semantic lifecycle modeling.
- **Captured = yes, compile = yes:** Group A confirmed for that contract.
- **All three compile:** Group A confirmed; next boundary is Group B lifecycle/deployment semantics, which requires its own prediction.

## Explicitly untouched

- `src/cydra/reasoning.py`
- `src/cydra/foundry.py`
- Benchmark 005 reasoning
- Group B implementation-vs-clone lifecycle/deployment modeling
- Initialization post-condition semantic modeling
- Semantic interpretation of extracted authorization predicates
