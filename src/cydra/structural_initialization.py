from __future__ import annotations

from .models import ContractModel, Hypothesis


_INITIALIZER_MODIFIERS = {"initializer", "reinitializer"}
_VISIBILITIES = {"public", "external"}


def generate_structural_initialization_hypotheses(contract: ContractModel) -> tuple[Hypothesis, ...]:
    """Discover lifecycle entry points from initializer semantics, not names."""
    hypotheses: list[Hypothesis] = []
    for function in contract.functions:
        if function.visibility not in _VISIBILITIES:
            continue
        modifiers = {modifier.split("(", 1)[0] for modifier in function.modifiers}
        if not modifiers.intersection(_INITIALIZER_MODIFIERS):
            continue
        hypotheses.append(
            Hypothesis(
                f"H-INIT-{function.name}",
                f"{function.name} may be callable in a deployed uninitialized state by an arbitrary caller, allowing privileged initialization state to be claimed.",
                "INV-INIT-001",
                function.name,
                "arbitrary external caller",
                "attacker-controlled initialization or privileged state",
                evidence_ids=(f"E-MODEL-{function.name}",),
            )
        )
    return tuple(hypotheses)
