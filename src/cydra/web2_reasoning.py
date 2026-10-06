from __future__ import annotations
from dataclasses import dataclass
from .hypotheses import Hypothesis, HypothesisState
from .web2_causal import Web2CausalVerification
from .web2_authorization import Web2AuthorizationPlanningResult, generate_executable_ownership_differential_plans
from .web2_model import Web2TargetModel

@dataclass(frozen=True)
class NextWeb2Experiment:
    kind: str
    reason: str

def apply_causal_verification(hypothesis: Hypothesis, verification: Web2CausalVerification) -> Hypothesis:
    if verification.state==HypothesisState.CAUSALLY_ESTABLISHED:
        return Hypothesis(hypothesis.hypothesis_id,hypothesis.statement,max(hypothesis.belief,verification.confidence),HypothesisState.CAUSALLY_ESTABLISHED,dict(hypothesis.planning_predictions))
    if verification.state==HypothesisState.CONTRADICTED:
        return Hypothesis(hypothesis.hypothesis_id,hypothesis.statement,min(hypothesis.belief,1.0-verification.confidence),HypothesisState.CONTRADICTED,dict(hypothesis.planning_predictions))
    return hypothesis

def select_next_web2_experiment(hypothesis: Hypothesis, *, has_differential_support: bool, has_causal_verification: bool, capability_gap: bool) -> NextWeb2Experiment:
    if capability_gap: return NextWeb2Experiment("CAPABILITY_REPAIR","execution capability is missing; repair or materialize the required adapter capability before drawing security conclusions")
    if has_differential_support and not has_causal_verification: return NextWeb2Experiment("CAUSAL_REPLAY","differential evidence exists but has not yet been reproduced causally")
    if hypothesis.state==HypothesisState.CAUSALLY_ESTABLISHED: return NextWeb2Experiment("IMPACT_VERIFICATION","causal behavior is established; independently verify security impact before reporting a finding")
    return NextWeb2Experiment("MODEL_EXPANSION","no decisive evidence exists; expand the target model to choose the highest-information experiment")


@dataclass(frozen=True)
class Web2HypothesisPlanningResult:
    """Model-derived hypotheses and executable experiments, kept evidence-free."""
    plans: tuple
    capability_gaps: tuple[str, ...]


def generate_web2_security_hypotheses(
    model: Web2TargetModel,
) -> Web2HypothesisPlanningResult:
    """Turn explicit model relationships into executable, capability-gated plans.

    This is deliberately conservative: endpoint names, HTTP status codes, and
    generic error fingerprints never create an authorization hypothesis.
    """
    result: Web2AuthorizationPlanningResult = generate_executable_ownership_differential_plans(model)
    return Web2HypothesisPlanningResult(result.plans, result.capability_gaps)
