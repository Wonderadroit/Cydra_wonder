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

## Next behavioral gate

The next implementation must connect `postcondition_required` to deterministic runtime observation. It must verify the state/value needed by the experiment before treating a setup sequence as sufficient. The verifier must fail closed when the predicate cannot be observed generically.

No target-specific vulnerability answer, selector, severity, or historical finding is encoded here.

Doctrine: **LLMs propose. Tools test. Evidence decides.**
