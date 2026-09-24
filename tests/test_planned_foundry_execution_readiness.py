from pathlib import Path

from cydra.models import ContractModel, Experiment, Hypothesis, FunctionModel, ParameterModel
from cydra.ast_dataflow import SemanticRelationshipEvidence
from cydra.planned_foundry import generate_authorization_test_from_experiment


def test_authorization_renderer_uses_recursive_execution_readiness_setup(tmp_path: Path):
    source = tmp_path / "Target.sol"
    source.write_text("pragma solidity ^0.8.20; contract Target {}\n", encoding="utf-8")
    (tmp_path / "foundry.toml").write_text("[profile.default]\nsrc = '.'\n", encoding="utf-8")
    target = FunctionModel(
        "start", "external", (), (), (), 10,
        state_predicates=("ready > 0",),
        state_predicate_polarities=(("ready > 0", "must_hold"),),
    )
    seed = FunctionModel(
        "seed", "external", (), ("ready",), (), 20,
        parameters=(ParameterModel("value", "uint256"),),
    )
    contract = ContractModel("Target", str(source), (target, seed))
    hypothesis = Hypothesis("H-AUTH-start", "start is unprotected", "INV-AUTH-001", "start", "attacker", "state mutation")
    experiment = Experiment("X-H-AUTH-start", "H-AUTH-start", "call start", ("mutation", "authorization"), 1.0, (), "start")
    output = tmp_path / "test.t.sol"
    generate_authorization_test_from_experiment(hypothesis, experiment, "./Target.sol", "Target", output, contract)
    rendered = output.read_text(encoding="utf-8")
    assert "target.seed(1)" in rendered
    assert "try target.start(" in rendered


def test_authorization_renderer_fails_closed_when_caller_state_writer_is_unconstructible(tmp_path: Path):
    source = tmp_path / "Target.sol"
    source.write_text("pragma solidity ^0.8.20; contract Target {}\n", encoding="utf-8")
    (tmp_path / "foundry.toml").write_text("[profile.default]\nsrc = '.'\n", encoding="utf-8")
    start = FunctionModel(
        "start", "external", (), (), (), 10,
        execution_predicates=("debt == 0",),
        execution_predicate_polarities=(("debt == 0", "must_not_hold"),),
        execution_value_bindings=(("debt", "maxWithdraw(msg.sender)"),),
    )
    borrow = FunctionModel(
        "borrow", "external", (), ("balanceOf",), (), 20,
        parameters=(ParameterModel("account", "address"), ParameterModel("amount", "uint256")),
        execution_predicates=("accountOwner == address(0)",),
        execution_predicate_polarities=(("accountOwner == address(0)", "must_not_hold"),),
        execution_value_bindings=(("accountOwner", "IFactory(FACTORY).ownerOfAccount(account)"),),
    )
    max_withdraw = FunctionModel("maxWithdraw", "public", (), (), (), 30, return_expressions=("convertToAssets(balanceOf(owner))",))
    contract = ContractModel("Target", str(source), (start, borrow, max_withdraw), state_variables=("FACTORY",))
    evidence = (
        SemanticRelationshipEvidence(
            contract="Target", function="borrow", relation="writes", target="balanceOf",
            confidence=0.99, source="solc-json-ast:test",
        ),
    )
    hypothesis = Hypothesis("H-AUTH-start", "start is unprotected", "INV-AUTH-001", "start", "attacker", "state mutation")
    experiment = Experiment("X-H-AUTH-start", "H-AUTH-start", "call start", ("mutation", "authorization"), 1.0, (), "start")
    import pytest
    with pytest.raises(ValueError, match="caller-state setup"):
        generate_authorization_test_from_experiment(hypothesis, experiment, "./Target.sol", "Target", tmp_path / "test.t.sol", contract, semantic_evidence=evidence)
