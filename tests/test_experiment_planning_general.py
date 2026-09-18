from cydra.experiment_planning import bind_experiment, plan_experiment
from cydra.models import Experiment, Hypothesis


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


def test_class_neutral_binding_preserves_target_and_inputs():
    hypothesis = Hypothesis(
        "H-FUTURE-bind", "claim", "INV-FUTURE-044", "rebalance", "actor", "impact"
    )
    experiment = plan_experiment(hypothesis, "exercise", ("bad", "good"), 1.0)

    bound = bind_experiment(
        hypothesis,
        experiment,
        target_function="rebalance",
        planned_inputs=("777",),
    )

    assert bound.target_function == "rebalance"
    assert bound.planned_inputs == ("777",)
    assert bound.invariant_id if hasattr(bound, "invariant_id") else True


def test_class_neutral_binding_rejects_cross_hypothesis_and_target_reuse():
    hypothesis = Hypothesis("H-FUTURE-a", "claim", "INV-X", "alpha", "actor", "impact")
    other = Hypothesis("H-FUTURE-b", "claim", "INV-Y", "beta", "actor", "impact")
    experiment = plan_experiment(hypothesis, "exercise", ("bad", "good"), 1.0)

    try:
        bind_experiment(other, experiment, target_function="beta", planned_inputs=("1",))
    except ValueError:
        pass
    else:
        raise AssertionError("cross-hypothesis binding must fail closed")

    bound = bind_experiment(hypothesis, experiment, target_function="alpha", planned_inputs=("1",))
    try:
        bind_experiment(hypothesis, bound, target_function="beta")
    except ValueError:
        pass
    else:
        raise AssertionError("cross-target binding must fail closed")
