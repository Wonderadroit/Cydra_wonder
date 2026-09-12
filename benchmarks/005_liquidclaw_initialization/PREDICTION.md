# Benchmark 005 — Prediction 5C: System-Model Enrichment

## Locked prediction

**Prediction 5C-SystemModel-Enrichment:** Extending the Solidity system model to extract constructor signatures, function parameter types (names and declared ABI-facing types), and inline authorization predicates from function bodies will enable the initialization generator to produce Foundry tests that compile against the three LiquidClaw initializers.

This prediction is scoped to **Group A — syntactic extraction** only. It does not predict execution, test success, vulnerability confirmation, or semantic correctness of initialization arguments/post-conditions.

## Regression precondition

The enrichment is additive. It adds new fields to `FunctionModel` and `ContractModel` without removing or renaming existing fields. Existing extraction behavior for `name`, `visibility`, `modifiers`, `writes`, `external_calls`, and `line` must remain unchanged. If any existing field's behavior changes, that is a regression, not an enrichment.

Benchmarks 001–004 are the precondition gate. If any fixture produces a different hypothesis, experiment plan, or classification after enrichment, the run stops before LiquidClaw and the enrichment is treated as regressed.

## Regression result

The available regression fixtures on the authoritative `main` baseline were compared with the enriched branch.

| Benchmark | Hypothesis output | Experiment output | Classification / boundary | Baseline comparison |
|---|---|---|---|---|
| 001 | `H-AUTH-setWhitelist` | `X-H-AUTH-setWhitelist` | confirmed (`FAIL` vulnerable / `PASS` patched) | unchanged |
| 002 | single `INV-INIT-001` initialization hypothesis | `X-H-INIT-initialize` | confirmed (`FAIL` vulnerable / `PASS` patched) | unchanged |
| 003 | arithmetic hypothesis present | arithmetic Foundry experiment | harness boundary; classifier not reached | unchanged expected boundary failure |
| 004 | not present in `Wonderadroit/Cydra_wonder` baseline | not present | no executable 004 fixture exists in this authoritative repository | unavailable; not treated as a regression |

Benchmark 001, Benchmark 002, and their negative controls completed successfully on the enriched branch. Benchmark 003 reached the same intentional harness boundary used by the baseline rather than representing a new enrichment regression.

The existing extraction statements for `name`, `visibility`, `modifiers`, `writes`, `external_calls`, and `line` were left unchanged; the new fields are appended to the models. The regression suite therefore preserves the pre-existing reasoning/generator interface.

## LiquidClaw Group A extraction result

The relevant LiquidClaw source is the Aerodrome-derived Pool/Minter/Voter implementation family. The extractor was exercised against the three established initialization signatures and authorization predicates.

| Contract | Constructor captured | Parameters captured | Inline predicate captured | Generator output | Foundry compile |
|---|---|---|---|---|---|
| Pool | `()` | `address _token0, address _token1, bool _stable` | none | `new Pool()`; `initialize(attacker)`; `target.guardian() != attacker` | not run — generator falsification already decisive |
| Minter | `(address _voter, address _ve, address _rewardsDistributor)` | `AirdropParams memory params` | `msg.sender != team` | `new Minter()`; `initialize(attacker)`; `target.guardian() != attacker` | not run — generator falsification already decisive |
| Voter | `(address _forwarder, address _ve, address _factoryRegistry)` | `address[] calldata _tokens, address _minter` | `_msgSender() != minter` | `new Voter()`; `initialize(attacker)`; `target.guardian() != attacker` | not run — generator falsification already decisive |

The extractor therefore captured all three requested Group A constructs for all three targets. The current generator does not consume those enriched model fields; it remains hard-coded to a no-argument constructor, a one-argument `initialize(attacker)` call, and the `guardian()` postcondition.

The frozen LiquidClaw commit is not present as a fixture inside the authoritative CYDRA repository, and Foundry is not installed in the execution environment used for this run. Therefore no fabricated compile result is recorded. The generator output itself is sufficient to hit the locked falsification conditions before any execution gate.

## Classification

**Prediction 5C: FALSIFIED.**

Falsification conditions reached:

1. **Condition 1 — `target.guardian()` emitted:** reached for Pool, Minter, and Voter.
2. **Condition 2 — `new Minter()` with no constructor arguments:** reached for Minter.
3. **Condition 3 — `initialize(attacker)` wrong arity:** reached for Pool and Voter; Minter also receives the wrong argument type/shape for `AirdropParams`.
4. **Condition 4 — all three generated tests compile:** not reached; the generator boundary is already falsified.

### Interpretation

**Group A extraction succeeded. The prediction that extraction alone would enable the existing generator to compile against LiquidClaw is falsified at the model-to-generator boundary.**

The next boundary is the generator interface/postcondition mapping. That is a separate prediction and change. **Do not implement it in this session.**

## Execution boundary

No generated LiquidClaw test was executed. This session ends at the Group A classification boundary.

## Explicitly untouched

- `src/cydra/reasoning.py`
- `src/cydra/foundry.py`
- Benchmark 005 reasoning
- Group B implementation-vs-clone lifecycle/deployment modeling
- Initialization post-condition semantic modeling
- Semantic interpretation of extracted authorization predicates
