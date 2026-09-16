from cydra.hypotheses import Hypothesis
from cydra.test_planning import ObservationOption, rank_observations


def test_information_gain_prefers_observation_that_separates_competing_hypotheses():
    hypotheses = (
        Hypothesis(
            "hypothesis:h1",
            "state changes",
            belief=0.5,
            planning_predictions={"obs:shared": {"changed": 1.0, "unchanged": 0.0}, "obs:ambiguous": {"changed": 0.5, "unchanged": 0.5}},
        ),
        Hypothesis(
            "hypothesis:h2",
            "state does not change",
            belief=0.5,
            planning_predictions={"obs:shared": {"changed": 0.0, "unchanged": 1.0}, "obs:ambiguous": {"changed": 0.5, "unchanged": 0.5}},
        ),
    )
    observations = (
        ObservationOption("obs:shared", "observe the discriminating state transition", ("changed", "unchanged")),
        ObservationOption("obs:ambiguous", "observe an ambiguous transition", ("changed", "unchanged")),
    )
    ranked = rank_observations(hypotheses, observations)
    assert ranked[0].observation_id == "obs:shared"
    assert ranked[0].information_gain > ranked[1].information_gain


def test_information_gain_fails_closed_when_predictions_are_missing():
    hypotheses = (
        Hypothesis("hypothesis:h1", "one explanation", planning_predictions={}),
        Hypothesis("hypothesis:h2", "another explanation", planning_predictions={}),
    )
    ranked = rank_observations(
        hypotheses,
        (ObservationOption("obs:unknown", "collect missing evidence", ("yes", "no")),),
    )
    assert ranked[0].information_gain == 0.0
    assert "conservatively set to zero" in ranked[0].rationale
