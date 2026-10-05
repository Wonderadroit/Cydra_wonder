from __future__ import annotations

"""Evidence-driven authorization experiment planning for Web2.

This planner does not label a response as an IDOR/BOLA finding. It creates a
differential experiment only when ownership and endpoint/resource relationships
are explicit in the target model.
"""

from dataclasses import dataclass

from .adapter_experiment import AdapterExperiment, ExperimentAction, bind_adapter_experiment
from .models import Hypothesis
from .web2_model import Web2TargetModel


@dataclass(frozen=True)
class AuthorizationExperimentPlan:
    hypothesis: Hypothesis
    experiment: AdapterExperiment


def plan_ownership_differential(
    model: Web2TargetModel,
    *,
    owner_identity_id: str,
    other_identity_id: str,
    resource_id: str,
    endpoint_id: str,
) -> AuthorizationExperimentPlan:
    resource = model.resources.get(resource_id)
    endpoint = model.endpoints.get(endpoint_id)

    if resource is None:
        raise ValueError(f"unknown resource: {resource_id}")
    if endpoint is None:
        raise ValueError(f"unknown endpoint: {endpoint_id}")
    if resource.owner_identity_id != owner_identity_id:
        raise ValueError("owner identity does not match explicit resource ownership")
    if other_identity_id not in model.identities:
        raise ValueError(f"unknown comparison identity: {other_identity_id}")
    if resource_id not in endpoint.resource_ids:
        raise ValueError("endpoint is not modeled as operating on the resource")

    hypothesis = Hypothesis(
        hypothesis_id=f"web2-auth:{resource_id}:{endpoint_id}",
        claim=(
            f"{endpoint.method} {endpoint.path} should authorize {owner_identity_id} "
            f"and apply a distinct authorization outcome to {other_identity_id} "
            f"for resource {resource_id}"
        ),
        invariant_id=f"ownership:{resource_id}",
        target_function=f"{endpoint.method} {endpoint.path}",
        attacker_capability="authenticated_non_owner_identity",
        expected_impact="UNAUTHORIZED_RESOURCE_ACCESS",
    )

    path = endpoint.path
    if resource.identifier is not None:
        path = path.replace("{id}", resource.identifier)

    actions = (
        ExperimentAction(
            action_id=f"{hypothesis.hypothesis_id}:owner",
            operation="http_request",
            inputs={"method": endpoint.method, "path": path, "identity_id": owner_identity_id},
            metadata={"role": "owner", "resource_id": resource_id, "endpoint_id": endpoint_id},
        ),
        ExperimentAction(
            action_id=f"{hypothesis.hypothesis_id}:comparison",
            operation="http_request",
            inputs={"method": endpoint.method, "path": path, "identity_id": other_identity_id},
            metadata={"role": "comparison", "resource_id": resource_id, "endpoint_id": endpoint_id},
        ),
    )

    experiment = bind_adapter_experiment(
        hypothesis,
        target=model.target,
        actions=actions,
        discriminates=(
            "owner_vs_non_owner_authorization_outcome",
            "owner_vs_non_owner_response_observation",
        ),
    )
    return AuthorizationExperimentPlan(hypothesis, experiment)
