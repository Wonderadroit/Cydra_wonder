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


def test_sequence_renderer_emits_constructor_arguments_for_interface_dependency(tmp_path):
    from cydra.models import ConstructorModel, ParameterModel
    from cydra.interface_resolver import ResolvedInterface
    model = _model()
    model = ContractModel(
        name="SequenceWithConstructor",
        source=str(root / "contracts" / "SequenceWithConstructor.sol"),
        constructor=ConstructorModel(
            (
                ParameterModel("_accountant", "IVaultAccountant"),
                ParameterModel("_fee", "uint256"),
            ),
            2,
        ),
        functions=model.functions,
        inherited_resolved_interfaces=(
            ResolvedInterface(
                name="IVaultAccountant",
                source_path="contracts/interfaces/IVaultAccountant.sol",
                resolution_method="relative_import",
                methods=(),
            ),
        ),
    )
    root = tmp_path
    (root / "foundry.toml").write_text("[profile.default]\n", encoding="utf-8")
    (root / "contracts" / "interfaces").mkdir(parents=True)
    (root / "contracts" / "interfaces" / "IVaultAccountant.sol").write_text(
        "interface IVaultAccountant {}\n", encoding="utf-8"
    )
    output = generate_sequence_test_from_experiment(
        _experiment()[0],
        _experiment()[1],
        "../contracts/SequenceWithConstructor.sol",
        "SequenceWithConstructor",
        root / "test" / "generated.t.sol",
        model,
    )
    source = output.read_text(encoding="utf-8")
    assert "new SequenceWithConstructor(IVaultAccountant(address(0)), 0)" in source
