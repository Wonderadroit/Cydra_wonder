from __future__ import annotations

from collections import defaultdict

from .ast_dataflow import SemanticRelationshipEvidence
from .models import ContractModel, Hypothesis, Invariant
from .pipeline import ReasoningContribution


def _shared_state_writers(
    contract: ContractModel,
    semantic: tuple[SemanticRelationshipEvidence, ...],
) -> dict[str, tuple[str, ...]]:
    """Return externally callable functions that share a state transition surface.

    The relation is deliberately descriptive: sharing a state variable does not
    prove a bug. It only identifies a place where independent transitions can
    interact and therefore deserves an experiment.
    """
    writers: dict[str, set[str]] = defaultdict(set)

    for function in contract.functions:
        if function.visibility not in {"public", "external"}:
            continue
        for state in function.writes:
            writers[state].add(function.name)

    # Compiler-linked evidence can recover/strengthen the model when the parser's
    # write projection is incomplete. It is still evidence, never proof.
    for item in semantic:
        if item.contract != contract.name:
            continue
        if item.relation not in {"writes", "transition_expression"}:
            continue
        if item.function in {f.name for f in contract.functions if f.visibility in {"public", "external"}}:
            writers[item.target].add(item.function)

    return {
        state: tuple(sorted(functions))
        for state, functions in writers.items()
        if len(functions) >= 2
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
                    "arbitrary external caller able to invoke the transition",
                    f"inconsistent {state} after a valid cross-function transition sequence",
                    evidence_ids=evidence_ids,
                )
            )

    return ReasoningContribution(tuple(invariants), tuple(hypotheses))
