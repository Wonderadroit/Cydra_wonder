from __future__ import annotations
from dataclasses import dataclass
from typing import Sequence
from .execution_adapter import AdapterObservation, AdapterStatus
from .hypotheses import Hypothesis, HypothesisState
from .web2_model import Web2TargetModel

@dataclass(frozen=True)
class Web2CausalVerification:
    state: HypothesisState
    confidence: float
    rationale: str
    evidence_ids: tuple[str,...]

def verify_reproducible_authorization_bypass(
    model: Web2TargetModel,
    *,
    hypothesis: Hypothesis,
    resource_id: str,
    owner_observations: Sequence[AdapterObservation],
    comparison_observations: Sequence[AdapterObservation],
    comparison_identity_id: str | None = None,
) -> Web2CausalVerification:
    resource=model.resources.get(resource_id)
    if resource is None: raise ValueError(f"unknown resource: {resource_id}")
    if resource.owner_identity_id is None: raise ValueError("causal authorization verification requires explicit ownership")
    if comparison_identity_id is not None and comparison_identity_id not in model.identities:
        raise ValueError(f"unknown comparison identity: {comparison_identity_id}")
    if len(owner_observations)<2 or len(comparison_observations)<2:
        return Web2CausalVerification(HypothesisState.UNRESOLVED,0.0,"causal verification requires two independent owner and comparison observations",())
    observations=tuple(owner_observations)+tuple(comparison_observations)
    if any(x.status != AdapterStatus.EXECUTED for x in observations):
        return Web2CausalVerification(HypothesisState.UNRESOLVED,0.0,"adapter capability or transport failure is not security evidence",())

    def value(obs):
        return obs.value if isinstance(obs.value,dict) else {}

    expected_owner=resource.owner_identity_id
    if any(value(x).get("identity_id") not in {None, expected_owner} for x in owner_observations):
        return Web2CausalVerification(HypothesisState.UNRESOLVED,0.0,"owner replay observations are attributed to an unexpected identity",tuple(x.action_id for x in observations))
    if comparison_identity_id is not None and any(value(x).get("identity_id") not in {None, comparison_identity_id} for x in comparison_observations):
        return Web2CausalVerification(HypothesisState.UNRESOLVED,0.0,"comparison replay observations are attributed to an unexpected identity",tuple(x.action_id for x in observations))

    def response(obs):
        v=value(obs)
        return v.get("status_code"),v.get("body_sha256")
    owner=tuple(response(x) for x in owner_observations)
    comparison=tuple(response(x) for x in comparison_observations)
    if any(s is None or b is None for s,b in owner+comparison):
        return Web2CausalVerification(HypothesisState.UNRESOLVED,0.0,"causal verification requires status and response-body fingerprints",())
    owner_success=all(200<=s<300 for s,_ in owner)
    comparison_success=all(200<=s<300 for s,_ in comparison)
    owner_bodies={b for _,b in owner}; comparison_bodies={b for _,b in comparison}
    if owner_success and comparison_success and len(owner_bodies)==1 and owner_bodies==comparison_bodies:
        return Web2CausalVerification(HypothesisState.CAUSALLY_ESTABLISHED,0.95,"two independent owner and non-owner executions reproducibly returned the same successful resource body",tuple(x.action_id for x in observations))
    return Web2CausalVerification(HypothesisState.UNRESOLVED,0.9,"reproducible causal replay did not establish the modeled unauthorized resource access",tuple(x.action_id for x in observations))
