# Generic prerequisite graph

This document records the execution-readiness consolidation discovered during supervised unfamiliar-target research.

## Boundary

CYDRA must distinguish:

1. prerequisite discovered;
2. prerequisite constructible;
3. setup transition executed;
4. prerequisite postcondition observed;
5. prerequisite verified.

Execution success alone is not verification.

## Generic graph

The graph is target-neutral:

`predicate -> producer -> state dependency -> transition -> execution -> observation -> verification`

`PrerequisiteGraph` is an immutable evidence surface. Unknown or merely discovered nodes remain unresolved. A security experiment must not be entered from a graph containing unresolved prerequisites.

## Setup provenance

Recursive setup actions retain provenance from the consumer function and required state. Sequence rendering now checks that generated setup actions carry that provenance, including nested writer chains.

## Postcondition verification

A constructible setup transition remains blocked until its source-backed postcondition is observed at runtime. State observations are matched to the exact modeled predicate (including the neutral runtime observation kind used by the evidence adapter), and a setup action is promoted only when its provenance state is among the successfully observed predicates. Unrelated setup actions remain constructible and therefore block security-experiment entry.

This preserves the boundary:

`constructible setup -> execute -> observe source-backed postcondition -> verified setup`

If no deterministic observation can be established, CYDRA remains fail-closed rather than treating transaction success as proof.

No target-specific vulnerability answer, selector, severity, or historical finding is encoded here.

Doctrine: **LLMs propose. Tools test. Evidence decides.**
