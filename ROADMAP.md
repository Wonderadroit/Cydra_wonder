# CYDRA Roadmap

## Phase 0 — Foundation

- Project Bible
- architecture contract
- domain/evidence schemas
- configuration and authorization model
- test harness
- CI baseline

**Exit condition:** repository can represent an investigation without unsupported claims.

## Phase 1 — Target Understanding

- source/repository ingestion
- Solidity/compiler routing
- AST and source mapping
- contract/function/state model
- call graph
- modifiers and authorization model
- proxy/implementation mapping
- scope extraction

**Exit condition:** CYDRA can produce a useful system model for a real Solidity target.

## Phase 2 — Invariant and Structural Reasoning

- invariant candidates
- provenance/confidence
- sibling-function comparison
- cross-contract consistency
- privilege-boundary analysis
- state-machine reasoning
- economic/accounting relationships

**Exit condition:** CYDRA can produce code-grounded hypotheses rather than generic vulnerability labels.

## Phase 3 — Hypothesis Engine

- structured hypotheses
- competing hypotheses
- uncertainty model
- assumption tracking
- hypothesis updates
- information-gain scoring
- investigation budget

**Exit condition:** CYDRA can choose the next experiment based on uncertainty rather than blindly scanning.

## Phase 4 — Tool Orchestration

- Slither integration
- Foundry integration
- Echidna/Medusa integration
- symbolic/formal integrations where justified
- sandbox/environment checks
- execution evidence capture

**Exit condition:** hypotheses automatically produce appropriate, reproducible validation experiments.

## Phase 5 — Causal Verification

- execution traces
- state-delta analysis
- attacker capability verification
- impact verification
- economic impact verification where relevant
- reproducibility gate
- adversarial hypothesis challenge

**Exit condition:** unsupported hypotheses cannot become findings.

## Phase 6 — Historical Benchmarking

- curated historical cases
- blind benchmark runner
- PoC replay where permitted
- false-positive corpus
- missed-finding corpus
- reasoning-pattern effectiveness metrics

**Exit condition:** measurable improvement on unseen historical cases without answer matching.

## Phase 7 — Research Workflow

- investigation queue
- evidence package
- researcher review interface/CLI
- verified draft assistance
- regression database
- long-running research metrics

**Exit condition:** CYDRA supports a complete authorized research workflow while preserving the human submission boundary.

## Priority rule

The next task is whichever item most improves demonstrated vulnerability discovery or causal verification. UI, broad integrations, and architecture expansion are lower priority unless they unblock that objective.
