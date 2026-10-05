from __future__ import annotations
from dataclasses import dataclass
from typing import Sequence
from .adapter_experiment import AdapterExperiment, execute_adapter_experiment
from .execution_adapter import AdapterObservation, ExecutionAdapter
from .hypotheses import BeliefUpdate, Hypothesis, update_hypothesis
from .invariants import CandidateVerification, InvariantCandidate, VerificationEvidence, verify_candidate
from .web2_evidence import authorization_differential_evidence

@dataclass(frozen=True)
class AdapterCycleResult:
    hypothesis: Hypothesis
    belief_update: BeliefUpdate
    verification: CandidateVerification
    evidence: tuple[VerificationEvidence,...]

def run_web2_authorization_cycle(hypothesis: Hypothesis, experiment: AdapterExperiment, adapter: ExecutionAdapter) -> AdapterCycleResult:
    if experiment.hypothesis_id != hypothesis.hypothesis_id: raise ValueError("experiment is bound to a different hypothesis")
    observations: Sequence[AdapterObservation]=execute_adapter_experiment(experiment,adapter)
    evidence=authorization_differential_evidence(hypothesis,observations)
    candidate=InvariantCandidate(candidate_id=hypothesis.hypothesis_id,statement=hypothesis.statement,source_ids=(f"experiment:{experiment.experiment_id}",),confidence=0.5,evidence_count=1)
    verification=verify_candidate(candidate,evidence)
    updated, belief_update=update_hypothesis(hypothesis,verification,evidence)
    return AdapterCycleResult(updated,belief_update,verification,tuple(evidence))
