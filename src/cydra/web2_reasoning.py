from __future__ import annotations
from dataclasses import dataclass
from .hypotheses import Hypothesis, HypothesisState
from .web2_causal import Web2CausalVerification
from .web2_authorization import Web2AuthorizationPlanningResult, generate_executable_ownership_differential_plans
from .web2_model import Web2TargetModel
from .web2_discovery import Web2CapabilityState, Web2DiscoveryResult

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




@dataclass(frozen=True)
class Web2CapabilityRepairPlan:
    """Non-security repair work required before executable hypotheses can run."""
    capability: str
    required_capabilities: tuple[str, ...]
    executable: bool
    reason: str
    state: str = "EXHAUSTED"


def generate_web2_capability_repair_plans(
    discovery: Web2DiscoveryResult,
) -> tuple[Web2CapabilityRepairPlan, ...]:
    """Translate discovery capability gaps into explicit, non-security repair plans.

    These plans never authorize requests and never create vulnerability hypotheses.
    They separate capability repair from the executable security-experiment budget.
    """
    plans: list[Web2CapabilityRepairPlan] = []
    state_by_capability = {state.capability: state for state in discovery.capability_states}
    if "RESOURCE_STATE_ACQUISITION" in discovery.capability_gaps:
        state = state_by_capability.get(
            "RESOURCE_STATE_ACQUISITION",
            Web2CapabilityState("RESOURCE_STATE_ACQUISITION", "EXHAUSTED"),
        )
        if state.status == "INCOMPLETE_FRONTIER":
            required = state.remaining_strategies or ("continue_frontier_exploration",)
            reason = (
                "Do not patch resource extraction yet. The evidence frontier is "
                "incomplete; continue the generic discovery frontier before proposing "
                "a capability implementation."
            )
        elif state.status == "BLOCKED_CONTEXT":
            required = state.remaining_strategies or ("authorized_resource_context",)
            reason = (
                "The current target context does not expose concrete resource state. "
                "Acquire an authorized resource context or an independently observed "
                "public state source; never synthesize an identifier."
            )
        else:
            required = (
                "resource_identifier_observation",
                "resource_provenance",
                "dependent_endpoint_materialization",
            )
            reason = (
                "Configured target-independent acquisition strategies produced no "
                "concrete resource identifier; implement the missing generic capability "
                "only after the acquisition strategies are exhausted."
            )
        plans.append(Web2CapabilityRepairPlan(
            capability="RESOURCE_STATE_ACQUISITION",
            required_capabilities=required,
            executable=False,
            reason=reason,
            state=state.status,
        ))
    return tuple(plans)


def _merge_capability_gaps(*gap_sets: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    """Preserve capability failures from every stage of the planning pipeline."""
    return tuple(dict.fromkeys(gap for gaps in gap_sets for gap in gaps))


def generate_web2_security_hypotheses(
    model: Web2TargetModel,
) -> Web2HypothesisPlanningResult:
    """Turn explicit model relationships into executable, capability-gated plans.

    This is deliberately conservative: endpoint names, HTTP status codes, and
    generic error fingerprints never create an authorization hypothesis.
    """
    result: Web2AuthorizationPlanningResult = generate_executable_ownership_differential_plans(model)
    return Web2HypothesisPlanningResult(result.plans, _merge_capability_gaps(tuple(result.capability_gaps)))


def generate_web2_hypotheses_from_discovery(
    discovery: Web2DiscoveryResult,
) -> Web2HypothesisPlanningResult:
    """Project a completed discovery model into executable security plans.

    Discovery observations and response fingerprints remain evidence-free inputs.
    Only explicit model relationships and provenance-backed materialization may
    produce executable hypotheses. External service origins never authorize
    execution.

    Capability gaps discovered upstream are planning inputs too: they must
    survive publication even when the model planner cannot produce a plan yet.
    """
    result = generate_executable_ownership_differential_plans(
        discovery.model,
        provenance=discovery.resource_provenance,
    )
    return Web2HypothesisPlanningResult(
        result.plans,
        _merge_capability_gaps(
            tuple(result.capability_gaps),
            tuple(discovery.capability_gaps),
        ),
    )
