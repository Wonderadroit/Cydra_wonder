from cydra.experiment_planning import plan_experiment
from cydra.models import Hypothesis


def test_class_neutral_experiment_envelope_accepts_future_invariant():
    hypothesis = Hypothesis(
        hypothesis_id="H-FUTURE-custom-surface",
        claim="a future reasoning surface has a discriminating behavior",
        invariant_id="INV-FUTURE-042",
        target_function="rebalance",
        attacker_capability="externally callable actor",
        expected_impact="observed behavior violates the modeled invariant",
    )

    experiment = plan_experiment(
        hypothesis,
        action="Call the observed target under the modeled precondition and compare the result with the invariant.",
        discriminates=("invariant violated", "invariant preserved"),
        cost=1.0,
    )

    assert experiment.experiment_id == "X-H-FUTURE-custom-surface"
    assert experiment.hypothesis_id == hypothesis.hypothesis_id
    assert experiment.action.startswith("Call the observed target")
    assert experiment.discriminates == ("invariant violated", "invariant preserved")


def test_class_neutral_experiment_envelope_fails_closed_on_invalid_metadata():
    hypothesis = Hypothesis(
        "H-FUTURE-invalid", "claim", "INV-FUTURE-043", "rebalance", "actor", "impact"
    )

    for action, discriminates, cost in (("", ("x",), 1.0), ("call", (), 1.0), ("call", ("x",), -1.0)):
        try:
            plan_experiment(hypothesis, action, discriminates, cost)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid generic experiment metadata must fail closed")
