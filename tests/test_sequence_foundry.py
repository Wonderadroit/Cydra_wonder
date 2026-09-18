from pathlib import Path

from cydra.models import ContractModel, Experiment, ExperimentStep, Hypothesis
from cydra.sequence_foundry import generate_sequence_test_from_experiment


def _model() -> ContractModel:
    from cydra.models import FunctionModel, ParameterModel
    return ContractModel(
        "SequenceFixture",
        "/tmp/SequenceFixture.sol",
        (
            FunctionModel("increase", "external", (), ("counter",), (), 3, (ParameterModel("amount", "uint256"),)),
            FunctionModel("decrease", "external", (), ("counter",), (), 7, (ParameterModel("amount", "uint256"),)),
        ),
    )


def _experiment() -> tuple[Hypothesis, Experiment]:
    hypothesis = Hypothesis(
        "H-STATE-counter-decrease",
        "candidate",
        "INV-STATE-counter",
        "decrease",
        "arbitrary external caller",
        "candidate impact",
        related_functions=("increase",),
    )
    experiment = Experiment(
        "X-H-STATE-counter-decrease",
        hypothesis.hypothesis_id,
        "increase(7) then decrease(7)",
        ("violation", "preservation"),
        2.0,
        steps=(
            ExperimentStep("increase", ("7",)),
            ExperimentStep("decrease", ("7",)),
        ),
    )
    return hypothesis, experiment


def test_sequence_renderer_emits_ordered_calls():
    hypothesis, experiment = _experiment()
    output = generate_sequence_test_from_experiment(
        hypothesis,
        experiment,
        "../SequenceFixture.sol",
        "SequenceFixture",
        Path("/tmp/generated-sequence.t.sol"),
        _model(),
    )
    source = output.read_text(encoding="utf-8")
    assert source.index("target.increase(7);") < source.index("target.decrease(7);")
    assert "vm.prank(attacker);" in source


def test_sequence_renderer_rejects_unknown_step():
    hypothesis, experiment = _experiment()
    bad = Experiment(
        experiment.experiment_id,
        experiment.hypothesis_id,
        experiment.action,
        experiment.discriminates,
        experiment.cost,
        steps=(ExperimentStep("missing", ("7",)),),
    )
    try:
        generate_sequence_test_from_experiment(
            hypothesis, bad, "../SequenceFixture.sol", "SequenceFixture",
            Path("/tmp/generated-sequence-bad.t.sol"), _model()
        )
    except ValueError as exc:
        assert "no sequence function" in str(exc)
    else:
        raise AssertionError("unknown sequence step must fail closed")
