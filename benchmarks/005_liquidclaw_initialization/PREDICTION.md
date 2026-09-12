# Benchmark 005 — Prediction 5D: Generator Interface Consumption

## Locked prediction

**Prediction 5D-Generator-Interface-Consumption:** Modifying the initialization generator to consume `ContractModel.constructor` and `FunctionModel.parameters` will produce Foundry test files that compile for all three LiquidClaw initializers. The postcondition assertion may remain fixture-shaped or be parameterized by a field Group A does not populate; this prediction does not require semantic correctness of the postcondition.

This prediction is scoped to the **model → generator interface boundary** only. It does not predict execution, vulnerability confirmation, deployment-topology correctness, initialization-state semantics, or postcondition correctness.

## Regression precondition

The generator change must preserve existing generator behavior for Benchmarks 001–002 and their negative controls.

Specifically:

- A fixture with a no-argument constructor must still generate `new Target()` when its model is consumed.
- A fixture with a no-argument initializer must still generate `initialize()` when its model is consumed.
- Existing access-control and initialization benchmark hypotheses, experiment plans, and classifications must remain unchanged.
- Any divergence in Benchmark 001/002 or their negative controls is a regression, not an improvement.

## Fields consumed

The generator may consume only the following newly enriched model fields in this prediction:

- `ContractModel.constructor` — constructor parameter declarations used to form a compiling constructor invocation.
- `FunctionModel.parameters` — initializer parameter declarations used to form a compiling initializer invocation.
- `FunctionModel.authorization_predicates` — available to the generator as model data, but not interpreted for this prediction and not used to derive semantic postconditions.

No new semantic state model is introduced.

## LiquidClaw compilation gate

For Pool, Minter, and Voter, record:

| Contract | Constructor consumed | Parameters consumed | Generator output | Foundry compile |
|---|---|---|---|---|
| Pool | pending | pending | pending | pending |
| Minter | pending | pending | pending | pending |
| Voter | pending | pending | pending | pending |

Compilation is the only LiquidClaw gate. Do not execute the generated tests in this session.

## Falsification conditions

1. Generator still emits `new Target()` for Minter or Voter → **constructor consumption failed**.
2. Generator still emits `initialize(attacker)` for Pool or Voter → **parameter consumption failed**.
3. Generator emits `initialize(...)` with structurally invalid argument shape/arity → **parameter extraction/interface consumption failed**.
4. Benchmark 001, 002, or either negative control changes output → **additive/regression property broken**.

## Confirmation condition

All three LiquidClaw generated tests compile, and Benchmark 001/002 plus their negative controls remain unchanged.

The guardian postcondition is **not** a falsification condition for 5D. Postcondition semantics are explicitly deferred to Prediction 5E.

## Boundary interpretation

- **Regression:** fix the generator change within this scope and rerun the regression gate.
- **Constructor not consumed:** remain at the generator interface boundary.
- **Parameters not consumed:** remain at the generator interface boundary.
- **Struct/custom argument cannot be emitted without semantic information:** record the exact model-to-generator limitation; do not add Group B semantics.
- **All three compile:** Prediction 5D confirmed; next boundary is postcondition semantics (5E).

## Explicitly untouched

- `src/cydra/reasoning.py`
- Evidence schema and provenance model
- Transport/execution machinery
- Classifier logic
- Foundry test execution
- Postcondition semantic modeling
- Initialization lifecycle/deployment-topology modeling
- Benchmark 005 reasoning
