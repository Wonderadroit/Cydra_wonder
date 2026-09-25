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


def test_sequence_renderer_can_emit_observed_public_state_prerequisite(tmp_path):
    from cydra.models import FunctionModel
    source = tmp_path / "Target.sol"
    source.write_text(
        "pragma solidity ^0.8.20; contract Target { uint256 public epoch; "
        "function seed() external { epoch = 1; } "
        "function use() external { require(epoch > 0); } }",
        encoding="utf-8",
    )
    model = ContractModel(
        "Target",
        str(source),
        (
            FunctionModel("seed", "external", (), ("epoch",), (), 1),
            FunctionModel(
                "use", "external", (), (), (), 2,
                state_predicates=("epoch > 0",),
                state_predicate_polarities=(("epoch > 0", "must_hold"),),
            ),
        ),
    )
    hypothesis = Hypothesis("H-STATE-epoch", "candidate", "INV-STATE-epoch", "use", "attacker", "candidate")
    experiment = Experiment(
        "X-H-STATE-epoch", hypothesis.hypothesis_id, "seed then use", ("violation",), 2.0,
        steps=(ExperimentStep("seed", ()), ExperimentStep("use", ())),
    )
    generated = generate_sequence_test_from_experiment(
        hypothesis, experiment, "../Target.sol", "Target",
        tmp_path / "test" / "generated.t.sol", model,
        verify_state_prerequisites=True,
    )
    rendered = generated.read_text(encoding="utf-8")
    assert 'assertTrue(target.epoch() > 0, "unverified prerequisite: epoch > 0");' in rendered


def test_sequence_renderer_can_stop_before_target_after_observation(tmp_path):
    from cydra.models import FunctionModel
    source = tmp_path / "Target.sol"
    source.write_text(
        "pragma solidity ^0.8.20; contract Target { uint256 public epoch; "
        "function seed() external { epoch = 1; } "
        "function use() external { require(epoch > 0); } }",
        encoding="utf-8",
    )
    model = ContractModel(
        "Target",
        str(source),
        (
            FunctionModel("seed", "external", (), ("epoch",), (), 1),
            FunctionModel(
                "use", "external", (), (), (), 2,
                state_predicates=("epoch > 0",),
                state_predicate_polarities=(("epoch > 0", "must_hold"),),
            ),
        ),
    )
    hypothesis = Hypothesis("H-STATE-epoch-stop", "candidate", "INV-STATE-epoch", "use", "attacker", "candidate")
    experiment = Experiment(
        "X-H-STATE-epoch-stop", hypothesis.hypothesis_id, "seed then use", ("violation",), 2.0,
        steps=(ExperimentStep("seed", ()), ExperimentStep("use", ())),
    )
    generated = generate_sequence_test_from_experiment(
        hypothesis, experiment, "../Target.sol", "Target",
        tmp_path / "test" / "generated.t.sol", model,
        verify_state_prerequisites=True,
        stop_before_target=True,
    )
    rendered = generated.read_text(encoding="utf-8")
    assert "target.seed();" in rendered
    assert 'assertTrue(target.epoch() > 0, "unverified prerequisite: epoch > 0");' in rendered
    assert "target.use();" not in rendered


def test_sequence_renderer_can_verify_source_backed_state_relation(tmp_path):
    from cydra.models import FunctionModel
    source = tmp_path / "Target.sol"
    source.write_text(
        "pragma solidity ^0.8.20; contract Target { uint256 public counter; "
        "function bump() external { counter += 1; } }",
        encoding="utf-8",
    )
    model = ContractModel(
        "Target",
        str(source),
        (FunctionModel("bump", "external", (), ("counter",), (), 2),),
        state_variables=("counter",),
    )
    hypothesis = Hypothesis(
        "H-STATE-counter-bump", "candidate", "INV-STATE-counter",
        "bump", "attacker", "candidate",
    )
    experiment = Experiment(
        "X-H-STATE-counter-bump", hypothesis.hypothesis_id, "bump",
        ("violation", "preservation"), 1.0,
        steps=(ExperimentStep("bump", ()),),
    )
    generated = generate_sequence_test_from_experiment(
        hypothesis, experiment, "../Target.sol", "Target",
        tmp_path / "test" / "generated.t.sol", model,
        verify_state_relations=True,
    )
    rendered = generated.read_text(encoding="utf-8")
    assert "uint256 before_counter = target.counter();" in rendered
    assert "target.bump();" in rendered
    assert "assertEq(target.counter(), before_counter + 1" in rendered



def test_sequence_renderer_can_verify_inherited_state_relation(tmp_path):
    from cydra.models import FunctionModel
    source = tmp_path / "Target.sol"
    source.write_text(
        "pragma solidity ^0.8.20; contract Base { uint256 public counter; "
        "function bump() external { counter += 1; } } "
        "contract Target is Base {}",
        encoding="utf-8",
    )
    inherited = FunctionModel("bump", "external", (), ("counter",), (), 1)
    model = ContractModel(
        "Target",
        str(source),
        (),
        state_variables=("counter",),
        inherited_functions=(inherited,),
    )
    hypothesis = Hypothesis(
        "H-STATE-inherited-bump", "candidate", "INV-STATE-inherited",
        "bump", "attacker", "candidate",
    )
    experiment = Experiment(
        "X-H-STATE-inherited-bump", hypothesis.hypothesis_id, "bump", ("violation",), 1.0,
        steps=(ExperimentStep("bump", ()),),
    )
    generated = generate_sequence_test_from_experiment(
        hypothesis, experiment, "../Target.sol", "Target",
        tmp_path / "test" / "generated.t.sol", model,
        verify_state_relations=True,
    )
    rendered = generated.read_text(encoding="utf-8")
    assert "target.bump();" in rendered
    assert "assertEq(target.counter(), before_counter + 1" in rendered


def test_sequence_renderer_verifies_keyed_state_relation(tmp_path):
    source = tmp_path / "Target.sol"
    source.write_text(
        "pragma solidity ^0.8.20; contract Target { "
        "mapping(address => mapping(uint256 => uint256)) public queued; "
        "function execute(address user, uint256 epoch) external { queued[user][epoch] += 1; } }",
        encoding="utf-8",
    )
    from cydra.models import FunctionModel, ParameterModel
    model = ContractModel(
        "Target",
        str(source),
        (
            FunctionModel(
                "execute", "external", (), ("queued",), (), 2,
                parameters=(ParameterModel("user", "address"), ParameterModel("epoch", "uint256")),
            ),
        ),
        state_variables=("queued",),
    )
    hypothesis = Hypothesis(
        "H-STATE-queued-execute", "candidate", "INV-STATE-queued",
        "execute", "attacker", "candidate",
    )
    experiment = Experiment(
        "X-H-STATE-queued-execute", hypothesis.hypothesis_id, "execute",
        ("violation",), 1.0,
        steps=(ExperimentStep("execute", ("attacker", "1")),),
    )
    generated = generate_sequence_test_from_experiment(
        hypothesis, experiment, "../Target.sol", "Target",
        tmp_path / "test" / "generated.t.sol", model,
        verify_state_relations=True,
    )
    rendered = generated.read_text(encoding="utf-8")
    assert "uint256 before_queued_user_epoch = target.queued(attacker, 1);" in rendered
    assert "target.execute(attacker, 1);" in rendered
    assert "assertEq(target.queued(attacker, 1), before_queued_user_epoch + 1" in rendered


def test_sequence_renderer_binds_parameter_state_delta(tmp_path):
    source = tmp_path / "Target.sol"
    source.write_text(
        "pragma solidity ^0.8.20; contract Target { "
        "uint256 public counter; "
        "function bump(uint256 amount) external { counter += amount; } }",
        encoding="utf-8",
    )
    from cydra.models import FunctionModel, ParameterModel
    model = ContractModel(
        "Target",
        str(source),
        (
            FunctionModel(
                "bump", "external", (), ("counter",), (), 2,
                parameters=(ParameterModel("amount", "uint256"),),
            ),
        ),
        state_variables=("counter",),
    )
    hypothesis = Hypothesis(
        "H-STATE-counter-bump", "candidate", "INV-STATE-counter",
        "bump", "attacker", "candidate",
    )
    experiment = Experiment(
        "X-H-STATE-counter-bump", hypothesis.hypothesis_id, "bump",
        ("violation",), 1.0,
        steps=(ExperimentStep("bump", ("7",)),),
    )
    generated = generate_sequence_test_from_experiment(
        hypothesis, experiment, "../Target.sol", "Target",
        tmp_path / "test" / "generated.t.sol", model,
        verify_state_relations=True,
    )
    rendered = generated.read_text(encoding="utf-8")
    assert "uint256 before_counter = target.counter();" in rendered
    assert "target.bump(7);" in rendered
    assert "assertEq(target.counter(), before_counter + 7" in rendered


def test_sequence_renderer_binds_caller_and_state_mapping_indexes(tmp_path):
    source = tmp_path / "Target.sol"
    source.write_text(
        "pragma solidity ^0.8.20; contract Target { "
        "uint128 public depositEpoch; "
        "mapping(address => mapping(uint256 => uint128)) public queuedDeposit; "
        "function requestDeposit(uint128 assets) external { "
        "queuedDeposit[msg.sender][depositEpoch] += assets; } }",
        encoding="utf-8",
    )
    from cydra.models import FunctionModel, ParameterModel
    model = ContractModel(
        "Target", str(source),
        (
            FunctionModel(
                "requestDeposit", "external", (), ("queuedDeposit",), (), 4,
                parameters=(ParameterModel("assets", "uint128"),),
            ),
        ),
        state_variables=("depositEpoch", "queuedDeposit"),
    )
    hypothesis = Hypothesis(
        "H-STATE-queuedDeposit-requestDeposit", "candidate",
        "INV-STATE-queuedDeposit", "requestDeposit", "attacker", "candidate",
    )
    experiment = Experiment(
        "X-H-STATE-queuedDeposit-requestDeposit", hypothesis.hypothesis_id,
        "requestDeposit", ("violation",), 1.0,
        steps=(ExperimentStep("requestDeposit", ("7",)),),
    )
    generated = generate_sequence_test_from_experiment(
        hypothesis, experiment, "../Target.sol", "Target",
        tmp_path / "test" / "generated.t.sol", model,
        verify_state_relations=True,
    )
    rendered = generated.read_text(encoding="utf-8")
    assert "uint128 before_index_depositEpoch = target.depositEpoch();" in rendered
    assert "uint128 before_queuedDeposit_msg_sender_depositEpoch = target.queuedDeposit(attacker, before_index_depositEpoch);" in rendered
    assert "target.requestDeposit(7);" in rendered
    assert "assertEq(target.queuedDeposit(attacker, before_index_depositEpoch), before_queuedDeposit_msg_sender_depositEpoch + 7" in rendered

    
def test_sequence_renderer_freezes_state_mapping_index_when_transition_changes_index(tmp_path):
    source = tmp_path / "Target.sol"
    source.write_text(
        "pragma solidity ^0.8.20; contract Target { "
        "uint128 public epoch; "
        "mapping(uint256 => uint256) public queued; "
        "function advanceAndQueue(uint256 amount) external { "
        "queued[epoch] += amount; epoch += 1; } }",
        encoding="utf-8",
    )
    from cydra.models import FunctionModel, ParameterModel
    model = ContractModel(
        "Target",
        str(source),
        (
            FunctionModel(
                "advanceAndQueue", "external", (), ("queued", "epoch"), (), 4,
                parameters=(ParameterModel("amount", "uint256"),),
            ),
        ),
        state_variables=("epoch", "queued"),
    )
    hypothesis = Hypothesis(
        "H-STATE-queued-advance", "candidate", "INV-STATE-queued",
        "advanceAndQueue", "attacker", "candidate",
    )
    experiment = Experiment(
        "X-H-STATE-queued-advance", hypothesis.hypothesis_id,
        "advanceAndQueue", ("violation",), 1.0,
        steps=(ExperimentStep("advanceAndQueue", ("7",)),),
    )
    generated = generate_sequence_test_from_experiment(
        hypothesis, experiment, "../Target.sol", "Target",
        tmp_path / "test" / "generated.t.sol", model,
        verify_state_relations=True,
    )
    rendered = generated.read_text(encoding="utf-8")
    assert "uint128 before_index_epoch = target.epoch();" in rendered
    assert "uint256 before_queued_epoch = target.queued(before_index_epoch);" in rendered
    assert "target.advanceAndQueue(7);" in rendered
    assert "assertEq(target.queued(before_index_epoch), before_queued_epoch + 7" in rendered
