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
    root = tmp_path
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


def test_sequence_renderer_resolves_indirect_contract_constructor_type(tmp_path):
    from cydra.models import ConstructorModel, ParameterModel
    model = ContractModel(
        name="SequenceWithToken",
        source=str(tmp_path / "Target.sol"),
        constructor=ConstructorModel(
            (ParameterModel("token", "ERC20"),),
            1,
        ),
        functions=_model().functions,
    )
    (tmp_path / "foundry.toml").write_text("[profile.default]\n", encoding="utf-8")
    (tmp_path / "interfaces").mkdir()
    (tmp_path / "interfaces" / "Token.sol").write_text(
        "contract ERC20 { constructor(string memory, string memory, uint8) {} }\n", encoding="utf-8"
    )
    (tmp_path / "Target.sol").write_text(
        'pragma solidity ^0.8.20;\nimport { ERC20 } from "./interfaces/Token.sol";\n'
        'contract SequenceWithToken { constructor(ERC20 token) {} }\n',
        encoding="utf-8",
    )
    generated = generate_sequence_test_from_experiment(
        _experiment()[0],
        _experiment()[1],
        "../Target.sol",
        "SequenceWithToken",
        tmp_path / "test" / "generated.t.sol",
        model,
    )
    source = generated.read_text(encoding="utf-8")
    assert 'import { ERC20 } from "../interfaces/Token.sol";' in source
    assert "new SequenceWithToken(ERC20(address(constructorAsset)))" in source


def test_sequence_renderer_satisfies_owner_role_and_binds_owner_constructor(tmp_path):
    from cydra.models import ConstructorModel, ParameterModel, FunctionModel
    model = ContractModel(
        name="OwnedSequence",
        source=str(tmp_path / "Target.sol"),
        constructor=ConstructorModel((ParameterModel("owner_", "address"),), 1),
        functions=(
            FunctionModel("configure", "external", ("onlyOwner",), ("value",), (), 3),
        ),
    )
    (tmp_path / "foundry.toml").write_text("[profile.default]\n", encoding="utf-8")
    hypothesis = Hypothesis("H-STATE-owned", "candidate", "INV-STATE-owned", "configure", "owner", "candidate")
    experiment = Experiment(
        "X-H-STATE-owned", hypothesis.hypothesis_id, "configure", ("violation",), 1.0,
        steps=(ExperimentStep("configure", ()),),
    )
    generated = generate_sequence_test_from_experiment(
        hypothesis, experiment, "../Target.sol", "OwnedSequence",
        tmp_path / "test" / "generated.t.sol", model,
    )
    source = generated.read_text(encoding="utf-8")
    assert "target = new OwnedSequence(address(0x1001));" in source
    assert "vm.prank(owner);" in source



def test_sequence_renderer_emits_real_newline_for_constructible_setup(tmp_path):
    from cydra.models import FunctionModel, ParameterModel
    model = ContractModel(
        name="SetupSequence",
        source=str(tmp_path / "Target.sol"),
        functions=(
            FunctionModel(
                "target", "external", (), (), (), 3,
                state_predicates=("items.length > 0",),
                state_predicate_polarities=(("items.length > 0", "must_hold"),),
            ),
            FunctionModel(
                "seed", "external", (), ("items",), (), 4,
                parameters=(ParameterModel("item", "address"),),
            ),
        ),
    )
    hypothesis = Hypothesis("H-STATE-items-target", "candidate", "INV-STATE-items", "target", "arbitrary external caller", "candidate")
    experiment = Experiment(
        "X-H-STATE-items-target", hypothesis.hypothesis_id, "seed then target", ("violation",), 1.0,
        steps=(ExperimentStep("target", ()),),
    )
    generated = generate_sequence_test_from_experiment(
        hypothesis, experiment, "../Target.sol", "SetupSequence",
        tmp_path / "test" / "generated.t.sol", model,
    )
    source = generated.read_text(encoding="utf-8")
    assert "vm.prank(attacker);\n        target.seed(address(0xCAFE));" in source
    assert "vm.prank(attacker);\\n        target.seed" not in source
