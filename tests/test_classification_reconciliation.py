from cydra.causal_verification import CausalVerificationState
from cydra.classification_reconciliation import LegacyClassification, ReasoningStage, reconcile_classification
from cydra.hypotheses import HypothesisState


def test_structural_support_does_not_become_confirmed():
    result = reconcile_classification("H1", HypothesisState.SUPPORTED)
    assert result.reasoning_stage is ReasoningStage.SUPPORTED
    assert result.legacy_classification is LegacyClassification.PROPOSED


def test_experimental_support_does_not_become_confirmed():
    result = reconcile_classification("H1", HypothesisState.SUPPORTED, experimentally_supported=True)
    assert result.reasoning_stage is ReasoningStage.EXPERIMENTALLY_SUPPORTED
    assert result.legacy_classification is LegacyClassification.PROPOSED


def test_only_verified_causality_maps_to_confirmed():
    result = reconcile_classification("H1", HypothesisState.SUPPORTED, causal_state=CausalVerificationState.VERIFIED)
    assert result.reasoning_stage is ReasoningStage.CAUSALLY_ESTABLISHED
    assert result.legacy_classification is LegacyClassification.CONFIRMED


def test_rejected_hypothesis_maps_to_rejected():
    result = reconcile_classification("H1", HypothesisState.CONTRADICTED)
    assert result.reasoning_stage is ReasoningStage.REJECTED
    assert result.legacy_classification is LegacyClassification.REJECTED


def test_execution_boundary_is_not_confirmed_and_is_preserved():
    result = reconcile_classification("H1", HypothesisState.UNRESOLVED, execution_boundary="foundry_generation")
    assert result.reasoning_stage is ReasoningStage.UNRESOLVED
    assert result.legacy_classification is LegacyClassification.NOT_CONFIRMED
    assert result.execution_boundary == "foundry_generation"
    assert "epistemic boundary" in result.rationale


def test_causal_rejection_overrides_prior_structural_support():
    result = reconcile_classification("H1", HypothesisState.SUPPORTED, causal_state=CausalVerificationState.REJECTED)
    assert result.reasoning_stage is ReasoningStage.REJECTED
    assert result.legacy_classification is LegacyClassification.REJECTED
