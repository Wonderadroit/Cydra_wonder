# CYDRA Architecture

## Architectural principle

CYDRA is a causal investigation orchestrator above existing security-analysis infrastructure.

```text
Target + Scope
      ↓
Ingestion / Compiler Routing
      ↓
System Model
      ↓
Invariant Extraction
      ↓
Structural & Economic Reasoning
      ↓
Hypothesis Generation
      ↓
Competing Hypotheses
      ↓
Information-Gain Test Planning
      ↓
Tool Orchestration
      ↓
Evidence Collection
      ↓
Hypothesis Updating
      ↓
Causal Verification
      ↓
Finding Gate
      ↓
Human Review / Evidence Package
```

## Layers

### 1. Target layer

Represents program metadata, scope, exclusions, deployed addresses, source repositories, compiler versions, chains, and permitted environments.

### 2. Understanding layer

Normalizes source and compiler output into a language-independent system model. Initial priority is Solidity/EVM, while routing remains extensible to Vyper and other supported ecosystems.

### 3. Evidence layer

Stores observations with provenance. Evidence can originate from source analysis, compiler artifacts, tests, static tools, execution traces, fuzzing, symbolic analysis, or historical benchmark material.

### 4. Reasoning layer

Generates and evaluates invariants, anomalies, hypotheses, competing hypotheses, assumptions, and causal explanations.

### 5. Planning layer

Selects the next action using uncertainty, information gain, cost, authorization, tool capability, and reproducibility.

### 6. Execution layer

Runs approved tools in controlled environments and captures commands, configuration, output, traces, artifacts, and versions.

### 7. Verification layer

Determines whether evidence establishes the hypothesized causal relationship and impact.

### 8. Finding layer

Promotes only sufficiently verified hypotheses to finding candidates. A finding contains evidence references rather than unsupported prose.

### 9. Human boundary

Human review remains the final authority for external disclosure/submission.

## Core objects

The initial domain model should include:

- Target
- ScopeRule
- SourceArtifact
- Contract/Module
- Function
- StateVariable
- CallEdge
- StateTransition
- AssetFlow
- AuthorizationBoundary
- Invariant
- Observation
- Hypothesis
- CompetingHypothesis
- Experiment
- ToolRun
- Evidence
- CausalClaim
- Finding
- BenchmarkCase
- RegressionCase

## State model

A hypothesis should move through explicit states:

`PROPOSED → INVESTIGATING → STRENGTHENED | WEAKENED | REJECTED | CONFIRMED`

`CONFIRMED` is allowed only after the verification gate succeeds.

A finding candidate should not exist independently of the evidence and causal claim that support it.

## Tool routing principle

Tool selection is hypothesis-driven.

Examples:

- structural authorization inconsistency → source/call-graph analysis + targeted execution;
- arithmetic/accounting invariant → Foundry property test/fuzzing;
- complex path feasibility → symbolic execution where appropriate;
- broad candidate generation → Slither/custom static analysis;
- stateful invariant exploration → Echidna/Medusa/Foundry;
- formal property requiring stronger guarantees → Kontrol/KEVM where practical.

The engine must be able to explain why a tool was selected.

## LLM boundary

LLM output enters CYDRA as proposals or interpretations. It is normalized into structured objects and checked against the system model before being trusted for planning.

The LLM cannot directly write a confirmed finding state.

## Evidence graph

Evidence should form a graph:

`source → observation → hypothesis → experiment → tool run → result → causal claim → finding`

Contradictory evidence must remain attached to the hypothesis rather than being overwritten.

## Economic reasoning

For DeFi targets, CYDRA should model assets, balances, shares, prices, debt, collateral, fees, exchange rates, and conservation relationships when the target exposes them. Economic impact must be demonstrated rather than inferred from a suspicious code pattern.

## Proxy reasoning

For EVM targets, proxy-to-implementation relationships must be modeled where discoverable. CYDRA must distinguish proxy storage/context from implementation logic and preserve deployment/version provenance.

## Safety and authorization

Active execution requires a target authorization decision and environment policy. The engine must fail closed when scope or execution permissions are unknown.

## Design constraint

The architecture is intentionally smaller than a generic autonomous-agent platform. New components require demonstrated research value against real benchmark or authorized cases.
