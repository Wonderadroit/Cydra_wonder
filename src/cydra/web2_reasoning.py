from __future__ import annotations
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .hypotheses import Hypothesis, HypothesisState
from .web2_causal import Web2CausalVerification

if TYPE_CHECKING:
    from .web2_frontier import Web2Frontier


@dataclass(frozen=True)
class NextWeb2Experiment:
    kind: str
    reason: str


def apply_causal_verification(hypothesis: Hypothesis, verification: Web2CausalVerification) -> Hypothesis:
    if verification.state == HypothesisState.CAUSALLY_ESTABLISHED:
        return Hypothesis(
            hypothesis.hypothesis_id,
            hypothesis.statement,
            max(hypothesis.belief, verification.confidence),
            HypothesisState.CAUSALLY_ESTABLISHED,
            dict(hypothesis.planning_predictions),
        )
    if verification.state == HypothesisState.CONTRADICTED:
        return Hypothesis(
            hypothesis.hypothesis_id,
            hypothesis.statement,
            min(hypothesis.belief, 1.0 - verification.confidence),
            HypothesisState.CONTRADICTED,
            dict(hypothesis.planning_predictions),
        )
    return hypothesis


def select_next_web2_experiment(
    hypothesis: Hypothesis,
    *,
    has_differential_support: bool,
    has_causal_verification: bool,
    capability_gap: bool,
    frontier: Web2Frontier | None = None,
) -> NextWeb2Experiment:
    # A capability gap is branch-local.  If another reachable security
    # surface is executable, keep investigating it instead of deadlocking the
    # entire campaign on the missing capability.
    if capability_gap and frontier is not None and frontier.executable:
        return NextWeb2Experiment(
            "SECURITY_FRONTIER",
            "a capability is blocked, but independent reachable security surfaces remain executable",
        )
    if capability_gap:
        return NextWeb2Experiment(
            "CAPABILITY_REPAIR",
            "execution capability is missing and no independent executable security surface remains",
        )
    if has_differential_support and not has_causal_verification:
        return NextWeb2Experiment(
            "CAUSAL_REPLAY",
            "differential evidence exists but has not yet been reproduced causally",
        )
    if hypothesis.state == HypothesisState.CAUSALLY_ESTABLISHED:
        return NextWeb2Experiment(
            "IMPACT_VERIFICATION",
            "causal behavior is established; independently verify security impact before reporting a finding",
        )
    return NextWeb2Experiment(
        "MODEL_EXPANSION",
        "no decisive evidence exists; expand the target model to choose the highest-information experiment",
    )
