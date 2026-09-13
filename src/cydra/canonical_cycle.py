"""Close the canonical reasoning loop from execution evidence to hypothesis state.

This module deliberately accepts only evidence produced by an executed differential
experiment. Benchmark labels are not inputs to the reasoning decision.
"""
from __future__ import annotations

from dataclasses import dataclass

from .belief_persistence import persist_belief_update
from .causal_chain import CausalChain, persist_causal_chain
from .causal_verification import CausalVerificationResult, verify_persisted_causal_chain
from .foundry import ExecutionResult, require_executed
from .hypotheses import BeliefUpdate, Hypothesis, HypothesisState, update_hypothesis
from .invariants import CandidateVerification, VerificationEvidence, VerificationRole, VerificationState
from .observation_outcomes import ObservationOutcome, record_observation_outcome
from .system_model import Edge, Node, SystemModel


@dataclass(frozen=True)
class CanonicalCycleResult:
    hypothesis: Hypothesis
    belief_update: BeliefUpdate
    observation_outcome: ObservationOutcome
    verification: CandidateVerification
    causal_chain: CausalChain
    causal_verification: CausalVerificationResult


def _differential_verification(
    hypothesis_id: str,
    vulnerable: ExecutionResult,
    patched: ExecutionResult,
    outcome_evidence_id: str,
) -> tuple[CandidateVerification, tuple[VerificationEvidence, ...]]:
    vulnerable_supports = vulnerable.status == "FAIL" and patched.status == "PASS"
    contradicted = vulnerable.status == "PASS" and patched.status == "FAIL"
    verification_evidence_id = f"verification:{hypothesis_id}:{vulnerable.experiment_id}:{patched.experiment_id}"
    if vulnerable_supports:
        role, state, rationale = (
            VerificationRole.SUPPORTS,
            VerificationState.SUPPORTED,
            "vulnerable execution failed while the patched differential execution passed",
        )
    elif contradicted:
        role, state, rationale = (
            VerificationRole.CONTRADICTS,
            VerificationState.CONTRADICTED,
            "vulnerable execution passed while the patched differential execution failed",
        )
    else:
        role, state, rationale = (
            VerificationRole.NEUTRAL,
            VerificationState.UNRESOLVED,
            "differential execution did not produce a decisive vulnerable-versus-patched result",
        )
    evidence = (
        VerificationEvidence(outcome_evidence_id, role, 1.0, rationale),
        VerificationEvidence(verification_evidence_id, role, 1.0, rationale),
    )
    verification = CandidateVerification(
        hypothesis_id,
        state,
        tuple(item.evidence_id for item in evidence),
        tuple(item.evidence_id for item in evidence if item.role == VerificationRole.SUPPORTS),
        tuple(item.evidence_id for item in evidence if item.role == VerificationRole.CONTRADICTS),
        1.0 if state != VerificationState.UNRESOLVED else 0.0,
    )
    return verification, evidence


def _persist_verification_evidence(
    model: SystemModel,
    hypothesis_id: str,
    evidence: tuple[VerificationEvidence, ...],
    vulnerable: ExecutionResult,
    patched: ExecutionResult,
) -> None:
    item = evidence[1]
    if item.evidence_id in model.nodes:
        raise ValueError(f"verification evidence already exists: {item.evidence_id}")
    model.add_node(
        Node(
            item.evidence_id,
            "evidence",
            item.rationale,
            {
                "hypothesis_id": hypothesis_id,
                "role": item.role.value,
                "confidence": item.confidence,
                "vulnerable_status": vulnerable.status,
                "patched_status": patched.status,
                "vulnerable_experiment_id": vulnerable.experiment_id,
                "patched_experiment_id": patched.experiment_id,
                "provenance": "executed_differential_experiment",
            },
        )
    )


def _canonicalize_belief_update(
    updated: Hypothesis,
    belief_update: BeliefUpdate,
    verification: CandidateVerification,
) -> tuple[Hypothesis, BeliefUpdate]:
    """Make the persisted transition exactly match the canonical causal result."""
    if verification.state is not VerificationState.SUPPORTED:
        return updated, belief_update
    established = Hypothesis(
        updated.hypothesis_id,
        updated.statement,
        updated.belief,
        HypothesisState.CAUSALLY_ESTABLISHED,
        dict(updated.planning_predictions),
    )
    established_update = BeliefUpdate(
        belief_update.hypothesis_id,
        belief_update.prior_belief,
        belief_update.posterior_belief,
        belief_update.prior_state,
        HypothesisState.CAUSALLY_ESTABLISHED,
        belief_update.evidence_ids,
        "executed differential evidence causally established the hypothesis",
    )
    return established, established_update


def run_canonical_differential_cycle(
    model: SystemModel,
    *,
    hypothesis: Hypothesis,
    observation_id: str,
    vulnerable: ExecutionResult,
    patched: ExecutionResult,
    outcome_id: str,
) -> CanonicalCycleResult:
    """Persist one executed differential cycle and return its verified state."""
    require_executed(vulnerable)
    require_executed(patched)

    expected_hypothesis_node = (
        f"hypothesis:{hypothesis.hypothesis_id}"
        if not hypothesis.hypothesis_id.startswith("hypothesis:")
        else hypothesis.hypothesis_id
    )
    graph_hypothesis = (
        hypothesis
        if hypothesis.hypothesis_id == expected_hypothesis_node
        else Hypothesis(
            expected_hypothesis_node,
            hypothesis.statement,
            hypothesis.belief,
            hypothesis.state,
            dict(hypothesis.planning_predictions),
        )
    )

    outcome = record_observation_outcome(
        model,
        observation_id=observation_id,
        outcome_id=outcome_id,
        result=f"vulnerable={vulnerable.status}; patched={patched.status}",
        source="foundry:differential-execution",
        confidence=1.0,
        metadata={
            "vulnerable_experiment_id": vulnerable.experiment_id,
            "patched_experiment_id": patched.experiment_id,
        },
    )
    if outcome.hypothesis_id != expected_hypothesis_node:
        raise ValueError("executed outcome is bound to a different hypothesis")

    verification, evidence = _differential_verification(
        graph_hypothesis.hypothesis_id,
        vulnerable,
        patched,
        outcome.evidence_id,
    )
    _persist_verification_evidence(model, graph_hypothesis.hypothesis_id, evidence, vulnerable, patched)

    relation = (
        "supports"
        if verification.state == VerificationState.SUPPORTED
        else "contradicts"
        if verification.state == VerificationState.CONTRADICTED
        else "informs"
    )
    model.add_edge(
        Edge(
            outcome.evidence_id,
            relation,
            expected_hypothesis_node,
            {"provenance": "executed_differential_experiment"},
        )
    )

    updated, belief_update = update_hypothesis(graph_hypothesis, verification, evidence)
    updated, belief_update = _canonicalize_belief_update(updated, belief_update, verification)
    persist_belief_update(
        model,
        graph_hypothesis,
        belief_update,
        update_id=f"belief:{outcome_id}",
    )

    causal_chain = CausalChain(
        chain_id=f"causal:{outcome_id}",
        hypothesis_id=expected_hypothesis_node,
        observation_id=f"observation:{observation_id}",
        outcome_evidence_id=outcome.evidence_id,
        verification_id=evidence[1].evidence_id,
        belief_update_id=f"belief:{outcome_id}",
    )
    persist_causal_chain(model, causal_chain)
    causal_verification = verify_persisted_causal_chain(model, causal_chain.chain_id)

    if verification.state != VerificationState.UNRESOLVED and causal_verification.state.name != "VERIFIED":
        raise ValueError(
            "canonical causal cycle did not verify: "
            + "; ".join(causal_verification.reasons)
        )

    return CanonicalCycleResult(
        updated,
        belief_update,
        outcome,
        verification,
        causal_chain,
        causal_verification,
    )
