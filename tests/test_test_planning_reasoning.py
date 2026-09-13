from cydra.hypotheses import Hypothesis
from cydra.test_planning import ObservationOption, rank_observations


def test_information_gain_respects_relative_hypothesis_beliefs_and_predictions():
    plans = rank_observations(
        (
            Hypothesis("hypothesis:a", "A", 0.9, planning_predictions={"observation:one": {"A": 1.0, "B": 0.0}}),
            Hypothesis("hypothesis:b", "B", 0.1, planning_predictions={"observation:one": {"A": 0.0, "B": 1.0}}),
        ),
        (ObservationOption("observation:one", "distinguishes", ("A", "B")),),
    )
    assert plans[0].information_gain > 0.0


def test_missing_predictions_are_not_treated_as_information():
    plans = rank_observations(
        (Hypothesis("hypothesis:a", "A", 0.7), Hypothesis("hypothesis:b", "B", 0.3)),
        (ObservationOption("observation:one", "distinguishes", ("A", "B")),),
    )
    assert plans[0].information_gain == 0.0
    assert plans[0].utility == 0.0
    assert "predictions are incomplete" in plans[0].rationale


def test_single_outcome_observation_has_zero_information_gain():
    plans = rank_observations(
        (Hypothesis("hypothesis:a", "A", 0.7, planning_predictions={"observation:one": {"same": 1.0}}), Hypothesis("hypothesis:b", "B", 0.3, planning_predictions={"observation:one": {"same": 1.0}})),
        (ObservationOption("observation:one", "cannot distinguish", ("same",)),),
    )
    assert plans[0].information_gain == 0.0
    assert plans[0].utility == 0.0
