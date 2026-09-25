from __future__ import annotations

from .foundry import ExecutionResult, ExperimentOutcome, classify_experiment_outcome
from .models import Hypothesis
from .state_relation_evidence import StateRelationObservationEvidence


def classify_state_differential(
    hypothesis: Hypothesis,
    vulnerable: ExecutionResult,
    patched: ExecutionResult,
    relation_evidence: tuple[StateRelationObservationEvidence, ...],
) -> ExperimentOutcome:
    """Apply the shared differential classifier only after relation verification.

    State-transition classification is downstream of an independently executed
    source-backed relation. A vulnerable/patched split without that evidence is
    not sufficient to classify a state hypothesis.
    """
    if not relation_evidence:
        raise ValueError(
            "state differential classification requires independently verified relation evidence"
        )
    if any(item.experiment_id not in {
        vulnerable.experiment_id,
        patched.experiment_id,
        vulnerable.experiment_id + "-RELATION",
        patched.experiment_id + "-RELATION",
    } for item in relation_evidence):
        raise ValueError("state relation evidence is not bound to the differential execution")
    return classify_experiment_outcome(hypothesis, vulnerable, patched)
