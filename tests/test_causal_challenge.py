from cydra.causal_challenge import assess_all_hypothesis_challenges, assess_hypothesis_challenge
from cydra.hypotheses import Hypothesis
from cydra.test_planning import ObservationOption


def test_supported_hypothesis_requires_a_discriminating_competing_explanation():
    primary = Hypothesis(
        "hypothesis:primary",
        "state changes because of the suspected cause",
        belief=0.8,
        planning_predictions={"obs:probe": {"changed": 1.0, "unchanged": 0.0}},
    )
    alternative = Hypothesis(
        "hypothesis:alternative",
        "state changes for an unrelated reason",
        belief=0.2,
        planning_predictions={"obs:probe": {"changed": 0.0, "unchanged": 1.0}},
    )
    result = assess_hypothesis_challenge(
        primary,
        (alternative,),
        (ObservationOption("obs:probe", "repeat the discriminating probe", ("changed", "unchanged")),),
    )
    assert result.challenged is True
    assert result.competing_hypothesis_ids == ("hypothesis:alternative",)
    assert result.discriminating_observations == ("obs:probe",)
    assert result.recommended_observation == "obs:probe"


def test_missing_competing_prediction_fails_closed():
    primary = Hypothesis(
        "hypothesis:primary",
        "suspected cause explains the state",
        planning_predictions={"obs:probe": {"changed": 1.0, "unchanged": 0.0}},
    )
    alternative = Hypothesis("hypothesis:alternative", "another explanation", planning_predictions={})
    result = assess_hypothesis_challenge(
        primary,
        (alternative,),
        (ObservationOption("obs:probe", "probe", ("changed", "unchanged")),),
    )
    assert result.challenged is False
    assert result.recommended_observation is None
    assert "no available observation" in result.rationale


def test_no_competitor_is_not_treated_as_successful_self_challenge():
    primary = Hypothesis(
        "hypothesis:primary",
        "only current explanation",
        planning_predictions={"obs:probe": {"changed": 1.0, "unchanged": 0.0}},
    )
    result = assess_hypothesis_challenge(
        primary,
        (),
        (ObservationOption("obs:probe", "probe", ("changed", "unchanged")),),
    )
    assert result.challenged is False
    assert "no distinct competing hypothesis" in result.rationale


def test_all_hypotheses_are_challenged_against_each_other():
    hypotheses = (
        Hypothesis("hypothesis:a", "A", planning_predictions={"obs:probe": {"yes": 1.0, "no": 0.0}}),
        Hypothesis("hypothesis:b", "B", planning_predictions={"obs:probe": {"yes": 0.0, "no": 1.0}}),
    )
    assessments = assess_all_hypothesis_challenges(
        hypotheses,
        (ObservationOption("obs:probe", "probe", ("yes", "no")),),
    )
    assert len(assessments) == 2
    assert all(item.challenged for item in assessments)
