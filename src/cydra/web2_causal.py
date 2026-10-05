from __future__ import annotations

"""Causal replay verification for Web2 authorization discrepancies.

A first differential response is only a lead. This verifier requires
reproducible owner/non-owner observations against an explicitly owned resource
before allowing the hypothesis to become causally established.
"""

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
    evidence_ids: tuple[str, ...]


def verify_reproducible_authorization_bypass(
    model: Web2TargetModel,
    *,
    hypothesis: Hypothesis,
    resource_id: str,
    owner_observations: Sequence[AdapterObservation],
    comparison_observations: Sequence[AdapterObservation],
) -> Web2CausalVerification:
    resource = model.resources.get(resource_id)
    if resource is None:
        raise ValueError(f"unknown resource: {resource_id}")
    if resource.owner_identity_id is None:
        raise ValueError("causal authorization verification requires explicit ownership")
    if len(owner_observations) < 2 or len(comparison_observations) < 2:
        return Web2CausalVerification(
            HypothesisState.UNRESOLVED, 0.0,
            "causal verification requires two independent owner and comparison observations",
            tuple(),
        )

    observations = tuple(owner_observations) + tuple(comparison_observations)
    if any(item.status != AdapterStatus.EXECUTED for item in observations):
        return Web2CausalVerification(
            HypothesisState.UNRESOLVED, 0.0,
            "adapter capability or transport failure is not security evidence",
            tuple(),
        )

    def response(obs: AdapterObservation) -> tuple[int | None, str | None]:
        value = obs.value if isinstance(obs.value, dict) else {}
        return value.get("status_code"), value.get("body_sha256")

    owner = tuple(response(x) for x in owner_observations)
    comparison = tuple(response(x) for x in comparison_observations)

    if any(status is None or body is None for status, body in owner + comparison):
        return Web2CausalVerification(
            HypothesisState.UNRESOLVED, 0.0,
            "causal verification requires status and response-body fingerprints",
            tuple(),
        )

    owner_success = all(200 <= status < 300 for status, _ in owner)
    comparison_success = all(200 <= status < 300 for status, _ in comparison)
    owner_bodies = {body for _, body in owner}
    comparison_bodies = {body for _, body in comparison}

    if owner_success and comparison_success and len(owner_bodies) == 1 and owner_bodies == comparison_bodies:
        ids = tuple(x.action_id for x in observations)
        return Web2CausalVerification(
            HypothesisState.CAUSALLY_ESTABLISHED,
            0.95,
            "two independent owner and non-owner executions reproducibly returned the same successful resource body",
            ids,
        )

    return Web2CausalVerification(
        HypothesisState.UNRESOLVED,
        0.9,
        "reproducible causal replay did not establish the modeled unauthorized resource access",
        tuple(x.action_id for x in observations),
    )
