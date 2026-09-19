from __future__ import annotations

from collections import defaultdict

from .ast_dataflow import SemanticRelationshipEvidence
from .models import ContractModel, Hypothesis, Invariant
from .pipeline import ReasoningContribution


_INCREASE_OPERATORS = {"+=", "++"}
_DECREASE_OPERATORS = {"-=", "--"}


def _shared_state_writers(
    contract: ContractModel,
    semantic: tuple[SemanticRelationshipEvidence, ...],
) -> dict[str, tuple[str, ...]]:
    """Return externally callable functions that share a state transition surface.

    Sharing is only topology. It is not sufficient to create an invariant or
    hypothesis; callers must derive a stronger semantic relationship below.
    """
    writers: dict[str, set[str]] = defaultdict(set)
    public_functions = {f.name for f in contract.functions if f.visibility in {"public", "external"}}

    for function in contract.functions:
        if function.visibility not in {"public", "external"}:
            continue
        for state in function.writes:
            writers[state].add(function.name)

    for item in semantic:
        if item.contract == contract.name and item.relation in {"writes", "transition_expression"}:
            if item.function in public_functions:
                writers[item.target].add(item.function)

    return {
        state: tuple(sorted(functions))
        for state, functions in writers.items()
        if len(functions) >= 2
    }


def _state_transition_directions(
    contract: ContractModel,
    semantic: tuple[SemanticRelationshipEvidence, ...],
) -> dict[str, dict[str, str]]:
    """Extract only compiler-backed directional state transitions.

    This is deliberately narrower than shared-state detection. A directional
    relationship is emitted only when the compiler AST records an increment or
    decrement operator on an externally callable function. Unknown assignments
    remain unknown instead of being guessed.
    """
    public_functions = {f.name for f in contract.functions if f.visibility in {"public", "external"}}
    directions: dict[str, dict[str, str]] = defaultdict(dict)

    for item in semantic:
        if item.contract != contract.name or item.function not in public_functions:
            continue
        if item.relation != "transition_expression" or not item.metadata:
            continue
        operator = item.metadata.get("operator")
        if operator in _INCREASE_OPERATORS:
            directions[item.target][item.function] = "increase"
        elif operator in _DECREASE_OPERATORS:
            directions[item.target][item.function] = "decrease"

    return {state: dict(functions) for state, functions in directions.items()}


def generate_cross_function_state_hypotheses(
    contract: ContractModel,
    semantic: tuple[SemanticRelationshipEvidence, ...] = (),
) -> ReasoningContribution:
    """Generate class-neutral candidates from an observed state relationship.

    Shared state alone creates no hypothesis. A candidate requires compiler-backed
    evidence that at least one public/external transition increases a state value
    and another decreases that same state. This is a system-behavior relationship,
    not a vulnerability-class detector.
    """
    shared = _shared_state_writers(contract, semantic)
    directions = _state_transition_directions(contract, semantic)
    invariants: list[Invariant] = []
    hypotheses: list[Hypothesis] = []

    for state, functions in shared.items():
        state_directions = directions.get(state, {})
        increasing = tuple(sorted(function for function in functions if state_directions.get(function) == "increase"))
        decreasing = tuple(sorted(function for function in functions if state_directions.get(function) == "decrease"))

        if not increasing or not decreasing:
            continue

        invariant_id = f"INV-STATE-{state}-OPPOSING"
        invariants.append(
            Invariant(
                invariant_id,
                f"Observed externally callable transitions include both increases and decreases of {state}; valid compositions should preserve the system's modeled relationship for that state.",
                "compiler-backed state transition semantics",
                0.80,
            )
        )

        for function in functions:
            peers = tuple(peer for peer in functions if peer != function and (
                state_directions.get(peer) != state_directions.get(function)
            ))
            if not peers:
                continue
            direction = state_directions[function]
            hypotheses.append(
                Hypothesis(
                    f"H-STATE-{state}-{function}",
                    f"{function} may compose incorrectly with an opposing {state} transition, violating the observed state relationship.",
                    invariant_id,
                    function,
                    "arbitrary external caller able to invoke the transition",
                    f"the composed transition produces an unexpected {state} state relationship",
                    evidence_ids=(f"E-AST-STATE-{state}-{function}",),
                    related_functions=peers,
                )
            )

    return ReasoningContribution(tuple(invariants), tuple(hypotheses))
