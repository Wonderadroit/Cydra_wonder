from __future__ import annotations

"""Evidence interpretation for Web2 differential authorization experiments.

This layer compares observations against an explicitly modeled expectation. It
does not assign vulnerability severity or declare a finding.
"""

import hashlib
from typing import Sequence

from .execution_adapter import AdapterObservation, AdapterStatus
from .invariants import VerificationEvidence, VerificationRole
from .models import Hypothesis


def authorization_differential_evidence(
    hypothesis: Hypothesis,
    observations: Sequence[AdapterObservation],
) -> tuple[VerificationEvidence, ...]:
    if len(observations) < 2:
        return (
            VerificationEvidence(
                evidence_id=f"{hypothesis.hypothesis_id}:insufficient-observation",
                role=VerificationRole.NEUTRAL,
                confidence=1.0,
                rationale="authorization comparison requires both owner and comparison observations",
            ),
        )

    owner, comparison = observations[0], observations[1]
    if owner.status != AdapterStatus.EXECUTED or comparison.status != AdapterStatus.EXECUTED:
        return (
            VerificationEvidence(
                evidence_id=f"{hypothesis.hypothesis_id}:capability-gap",
                role=VerificationRole.NEUTRAL,
                confidence=1.0,
                rationale="adapter capability/transport failure is not security evidence",
            ),
        )

    owner_value = owner.value if isinstance(owner.value, dict) else {}
    comparison_value = comparison.value if isinstance(comparison.value, dict) else {}

    owner_status = owner_value.get("status_code")
    comparison_status = comparison_value.get("status_code")
    owner_body = owner_value.get("body_sha256")
    comparison_body = comparison_value.get("body_sha256")

    if owner_status is None or comparison_status is None:
        return (
            VerificationEvidence(
                evidence_id=f"{hypothesis.hypothesis_id}:missing-authorization-observation",
                role=VerificationRole.NEUTRAL,
                confidence=1.0,
                rationale="responses did not contain the status information required for comparison",
            ),
        )

    # A different authorization outcome is evidence that the modeled
    # owner/non-owner distinction is observable. It is not proof of a bug.
    if owner_status != comparison_status:
        digest = hashlib.sha256(
            f"{owner_status}:{comparison_status}:{owner_body}:{comparison_body}".encode()
        ).hexdigest()[:16]
        return (
            VerificationEvidence(
                evidence_id=f"{hypothesis.hypothesis_id}:authorization-divergence:{digest}",
                role=VerificationRole.SUPPORTS,
                confidence=0.8,
                rationale=(
                    "owner and comparison identities produced different HTTP authorization "
                    "outcomes for the same modeled resource"
                ),
            ),
        )

    # Equal status and equal response body are stronger evidence that the
    # modeled identity distinction is not reflected by this observation.
    if owner_body and comparison_body and owner_body == comparison_body:
        return (
            VerificationEvidence(
                evidence_id=f"{hypothesis.hypothesis_id}:identical-response",
                role=VerificationRole.CONTRADICTS,
                confidence=0.85,
                rationale=(
                    "owner and comparison identities produced the same status and response "
                    "body for the same modeled resource"
                ),
            ),
        )

    return (
        VerificationEvidence(
            evidence_id=f"{hypothesis.hypothesis_id}:same-status-different-body",
            role=VerificationRole.NEUTRAL,
            confidence=0.7,
            rationale=(
                "owner and comparison identities shared a status code but differed in body; "
                "authorization semantics require further causal investigation"
            ),
        ),
    )
