import pytest

from cydra.investigation_readiness import ReadinessState, assess_investigation_readiness


def test_complete_evidence_and_model_are_ready():
    result = assess_investigation_readiness(
        evidence_coverage=1.0,
        model_confidence=1.0,
        hypothesis_coverage=1.0,
        contradiction_clearance=1.0,
        experiment_validity=1.0,
    )
    assert result.state is ReadinessState.READY
    assert result.score == 1.0
    assert result.unresolved_reasons == ()


def test_uncertainty_is_conditional_and_actionable():
    result = assess_investigation_readiness(
        evidence_coverage=0.8,
        model_confidence=0.8,
        hypothesis_coverage=0.7,
        contradiction_clearance=0.8,
        experiment_validity=1.0,
    )
    assert result.state is ReadinessState.CONDITIONAL
    assert "evidence coverage is incomplete" in result.unresolved_reasons
    assert "relevant behavior remains untested" in result.unresolved_reasons
    assert "challenge competing system explanations" in result.recommended_next_tests


def test_serious_model_or_contradiction_gap_blocks_claim_readiness():
    result = assess_investigation_readiness(
        evidence_coverage=1.0,
        model_confidence=0.4,
        hypothesis_coverage=1.0,
        contradiction_clearance=0.4,
        experiment_validity=1.0,
    )
    assert result.state is ReadinessState.BLOCKED
    assert "system model remains uncertain" in result.unresolved_reasons
    assert "unresolved contradictions" in result.unresolved_reasons


def test_invalid_dimensions_fail_closed():
    with pytest.raises(ValueError, match="between 0 and 1"):
        assess_investigation_readiness(
            evidence_coverage=1.1,
            model_confidence=1.0,
            hypothesis_coverage=1.0,
            contradiction_clearance=1.0,
            experiment_validity=1.0,
        )


def test_readiness_is_not_vulnerability_probability():
    result = assess_investigation_readiness(
        evidence_coverage=0.5,
        model_confidence=0.5,
        hypothesis_coverage=0.5,
        contradiction_clearance=0.5,
        experiment_validity=1.0,
    )
    assert result.score == 0.6
    assert not hasattr(result, "vulnerability_probability")
