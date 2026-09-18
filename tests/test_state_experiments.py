from cydra.models import ExperimentStep, Hypothesis
from cydra.state_experiments import plan_cross_function_state_experiment


def test_cross_function_state_sequence_planner_preserves_ordered_causal_pair():
    hypothesis = Hypothesis(
        "H-STATE-counter-decrease",
        "counter decrease may violate the modeled state consistency when composed with another transition.",
        "INV-STATE-counter",
        "decrease",
        "arbitrary external caller able to invoke the transition",
        "inconsistent counter after a valid cross-function transition sequence",
        related_functions=("increase",),
    )

    experiment = plan_cross_function_state_experiment(
        hypothesis,
        first_input="7",
        second_input="7",
    )

    assert experiment.experiment_id == "X-H-STATE-counter-decrease"
    assert experiment.hypothesis_id == hypothesis.hypothesis_id
    assert experiment.target_function is None
    assert "increase(7) then decrease(7)" in experiment.action
    assert experiment.discriminates == (
        "the ordered composition violates the modeled shared-state relation",
        "the ordered composition preserves the modeled shared-state relation",
    )
    assert experiment.cost == 2.0
    assert experiment.steps == (ExperimentStep("increase", ("7",)), ExperimentStep("decrease", ("7",)))


def test_cross_function_state_sequence_planner_rejects_self_pair():
    hypothesis = Hypothesis(
        "H-STATE-counter-update",
        "candidate",
        "INV-STATE-counter",
        "update",
        "arbitrary external caller",
        "candidate impact",
    )

    try:
        plan_cross_function_state_experiment(hypothesis, "update")
    except ValueError as exc:
        assert "peer function must differ" in str(exc)
    else:
        raise AssertionError("self-pair must not produce a sequence experiment")
