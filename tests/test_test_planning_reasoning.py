from cydra.hypotheses import Hypothesis
from cydra.test_planning import ObservationOption, rank_observations


def test_information_gain_respects_relative_hypothesis_beliefs():
    plans = rank_observations(
        (Hypothesis("hypothesis:a", "A", 0.9), Hypothesis("hypothesis:b", "B", 0.1)),
        (ObservationOption("observation:one", "distinguishes", ("A", "B")),),
    )
    assert plans[0].information_gain > 0.0


def test_single_outcome_observation_has_zero_information_gain():
    plans = rank_observations(
        (Hypothesis("hypothesis:a", "A", 0.7), Hypothesis("hypothesis:b", "B", 0.3)),
        (ObservationOption("observation:one", "cannot distinguish", ("same",)),),
    )
    assert plans[0].information_gain == 0.0
    assert plans[0].utility == 0.0
