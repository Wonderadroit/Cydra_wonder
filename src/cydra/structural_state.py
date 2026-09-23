from __future__ import annotations

from collections import defaultdict
import re

from .ast_dataflow import SemanticRelationshipEvidence
from .models import ContractModel, Hypothesis, Invariant
from .pipeline import ReasoningContribution


def _shared_state_writers(
    contract: ContractModel,
    semantic: tuple[SemanticRelationshipEvidence, ...],
) -> dict[str, tuple[str, ...]]:
    """Return externally callable state-transition/read surfaces.

    A state investigation surface may be exposed by one writer plus independent
    readers. Compiler-linked reads are therefore first-class topology evidence;
    they do not imply a vulnerability or a satisfiable sequence.
    """
    externally_callable = {
        f.name
        for f in (*contract.functions, *contract.inherited_functions)
        if f.visibility in {"public", "external"}
    }
    touched: dict[str, set[str]] = defaultdict(set)
    writers: dict[str, set[str]] = defaultdict(set)

    for function in contract.functions:
        if function.visibility not in {"public", "external"}:
            continue
        for state in function.writes:
            touched[state].add(function.name)
            writers[state].add(function.name)
        for state, operation in function.external_calls:
            if operation in {"push", "pop"}:
                touched[state].add(function.name)
                writers[state].add(function.name)
        for predicate in function.state_predicates:
            for match in re.finditer(r"\b([A-Za-z_]\w*)(?:\.length)?\b", predicate):
                state = match.group(1)
                if state not in {"true", "false", "address", "bytes", "uint", "int"}:
                    touched[state].add(function.name)

    for item in semantic:
        if item.contract != contract.name or item.function not in externally_callable:
            continue
        if item.relation in {"reads", "writes", "transition_expression"}:
            touched[item.target].add(item.function)
        if item.relation in {"writes", "transition_expression"}:
            writers[item.target].add(item.function)

    return {
        state: tuple(sorted(functions))
        for state, functions in touched.items()
        if writers.get(state) and len(functions) >= 2
    }


def generate_cross_function_state_hypotheses(
    contract: ContractModel,
    semantic: tuple[SemanticRelationshipEvidence, ...] = (),
) -> ReasoningContribution:
    """Generate class-neutral candidates from shared state-transition topology.

    This surface intentionally does not name a vulnerability class, exploit
    primitive, function convention, or known benchmark. A shared state variable is
    treated as an investigation surface, not as a vulnerability finding.
    """
    shared = _shared_state_writers(contract, semantic)
    invariants: list[Invariant] = []
    hypotheses: list[Hypothesis] = []

    protected_functions = {f.name for f in contract.functions if f.visibility in {"public", "external"} and f.modifiers}

    for state, functions in shared.items():
        invariant_id = f"INV-STATE-{state}"
        confidence = 0.60
        if any(
            item.contract == contract.name
            and item.target == state
            and item.relation in {"writes", "transition_expression"}
            and item.confidence >= 0.95
            for item in semantic
        ):
            confidence = 0.75

        invariants.append(
            Invariant(
                invariant_id,
                f"All externally callable transitions touching {state} must preserve the contract's modeled state consistency.",
                "cross-function state-transition topology",
                confidence,
            )
        )

        for function in functions:
            evidence_ids = (f"E-MODEL-{function}",)
            hypotheses.append(
                Hypothesis(
                    f"H-STATE-{state}-{function}",
                    f"{function} may violate the modeled state consistency of {state} when composed with another externally callable transition.",
                    invariant_id,
                    function,
                    (
                        "authorized caller satisfying the modeled guards"
                        if function in protected_functions
                        else "arbitrary external caller able to invoke the transition"
                    ),
                    f"inconsistent {state} after a valid cross-function transition sequence",
                    evidence_ids=evidence_ids,
                    related_functions=tuple(peer for peer in functions if peer != function),
                )
            )

    return ReasoningContribution(tuple(invariants), tuple(hypotheses))
