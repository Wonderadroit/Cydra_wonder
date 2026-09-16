from cydra.models import Hypothesis
from cydra.reasoning import plan_arithmetic_experiment


def test_core_experiment_planner_does_not_require_known_invariant_ids():
    hypothesis = Hypothesis(
        hypothesis_id="H-FUTURE-custom-surface",
        claim="a future reasoning surface has a discriminating behavior",
        invariant_id="INV-FUTURE-042",
        target_function="rebalance",
        attacker_capability="externally callable actor",
        expected_impact="observed behavior violates the modeled invariant",
    )

    experiment = plan_arithmetic_experiment(hypothesis)

    assert experiment.hypothesis_id == hypothesis.hypothesis_id
    assert experiment.experiment_id == "X-H-FUTURE-custom-surface"
    assert experiment.hypothesis_id != "INV-FUTURE-042"
    assert experiment.discriminates
