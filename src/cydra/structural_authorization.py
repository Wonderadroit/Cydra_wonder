from __future__ import annotations

from .models import ContractModel, Hypothesis


_VISIBILITIES = {"public", "external"}


def generate_structural_access_control_hypotheses(contract: ContractModel) -> tuple[Hypothesis, ...]:
    """Find unguarded writers to storage also written by protected siblings.

    This deliberately ignores candidate function names. It is a conservative
    structural supplement to the legacy admin-name heuristic: shared storage
    behavior provides the relevance signal, while caller-scoped and explicitly
    authorized functions are excluded.
    """
    protected = {
        write
        for function in contract.functions
        if function.visibility in _VISIBILITIES and function.modifiers
        for write in function.writes
    }
    if not protected:
        return ()

    hypotheses: list[Hypothesis] = []
    for function in contract.functions:
        if function.visibility not in _VISIBILITIES or not function.writes:
            continue
        if function.modifiers or any("msg.sender" in predicate for predicate in function.authorization_predicates):
            continue
        if not protected.intersection(function.writes):
            continue
        hypotheses.append(
            Hypothesis(
                f"H-AUTH-{function.name}",
                f"{function.name} may permit an unauthorized caller to mutate state also controlled by a protected sibling.",
                "INV-AUTH-001",
                function.name,
                "arbitrary external caller",
                "state shared with a protected administrative path can be changed without its authorization mechanism",
                evidence_ids=(f"E-MODEL-{function.name}",),
            )
        )
    return tuple(hypotheses)
