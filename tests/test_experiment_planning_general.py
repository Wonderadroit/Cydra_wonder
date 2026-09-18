from cydra.experiment_planning import bind_experiment, plan_experiment
from cydra.models import FunctionModel, Hypothesis, ParameterModel
from cydra.planned_call import render_function_call


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

    assert bound.hypothesis_id == hypothesis.hypothesis_id
    assert bound.target_function == "rebalance"
    assert bound.planned_inputs == ("777",)


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


def test_generic_binding_flows_into_canonical_call_renderer():
    hypothesis = Hypothesis(
        "H-FUTURE-render", "claim", "INV-FUTURE-045", "rebalance", "actor", "impact"
    )
    experiment = plan_experiment(hypothesis, "exercise", ("changed", "unchanged"), 1.0)
    bound = bind_experiment(
        hypothesis,
        experiment,
        target_function="rebalance",
        planned_inputs=("777",),
    )
    function = FunctionModel(
        name="rebalance",
        visibility="external",
        modifiers=(),
        writes=("position",),
        external_calls=(),
        line=1,
        parameters=(ParameterModel("amount", "uint256"),),
    )

    assert render_function_call(bound, function) == "target.rebalance(777);"


def test_actual_pipeline_accepts_future_reasoning_planner_without_class_branch(monkeypatch, tmp_path):
    source = tmp_path / "Target.sol"
    source.write_text("contract Target {}\n", encoding="utf-8")
    function = FunctionModel(
        name="rebalance",
        visibility="external",
        modifiers=(),
        writes=("position",),
        external_calls=(),
        line=1,
        parameters=(ParameterModel("amount", "uint256"),),
    )
    from cydra.models import ContractModel
    contract = ContractModel(name="Target", source=str(source), functions=(function,))
    hypothesis = Hypothesis(
        "H-FUTURE-pipeline",
        "rebalance may violate the modeled invariant under a boundary input",
        "INV-FUTURE-046",
        "rebalance",
        "externally callable actor",
        "incorrect position state",
    )

    monkeypatch.setattr("cydra.pipeline.parse_solidity", lambda path: (contract,))
    monkeypatch.setattr("cydra.pipeline.generate_access_control_hypotheses", lambda c: (hypothesis,))
    monkeypatch.setattr("cydra.pipeline.generate_structural_access_control_hypotheses", lambda c, evidence=(): ())
    monkeypatch.setattr("cydra.pipeline.generate_initialization_hypotheses", lambda c: ())
    monkeypatch.setattr("cydra.pipeline.generate_structural_initialization_hypotheses", lambda c: ())
    monkeypatch.setattr("cydra.pipeline.generate_arithmetic_hypotheses", lambda c: ())

    def future_planner(candidate):
        assert candidate.invariant_id == "INV-FUTURE-046"
        return plan_experiment(
            candidate,
            "Call rebalance with the modeled boundary input and compare the resulting position.",
            ("invariant violated", "invariant preserved"),
            1.0,
        )

    from cydra.pipeline import investigate

    result = investigate(source, experiment_planner=future_planner)
    assert result.hypotheses == (hypothesis,)
    assert len(result.experiments) == 1
    experiment = result.experiments[0]
    assert experiment.hypothesis_id == hypothesis.hypothesis_id
    assert experiment.target_function == "rebalance"
    assert render_function_call(experiment, function) == "target.rebalance(1);"
