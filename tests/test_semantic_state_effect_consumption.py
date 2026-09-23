from cydra.ast_dataflow import SemanticRelationshipEvidence
from cydra.models import ContractModel, FunctionModel
from cydra.semantic_state_effects import build_state_effect_index, state_reads_for_function, state_writes_for_function
from cydra.structural_authorization import generate_structural_access_control_hypotheses


def _evidence(function: str, relation: str, target: str) -> SemanticRelationshipEvidence:
    return SemanticRelationshipEvidence(contract="Target", function=function, relation=relation, target=target, confidence=0.98, source="solc-json-ast:test.sol")


def test_index_preserves_write_and_compound_transition_semantics():
    index = build_state_effect_index([
        _evidence("guarded", "writes", "adminState"),
        _evidence("mutator", "transition_expression", "adminState"),
        _evidence("mutator", "reads", "balance"),
        _evidence("ignored", "reference", "adminState"),
    ])
    assert state_writes_for_function(index, "guarded", "Target") == ("adminState",)
    assert state_writes_for_function(index, "mutator", "Target") == ("adminState",)
    assert state_reads_for_function(index, "mutator", "Target") == ("adminState", "balance")
    assert state_writes_for_function(index, "ignored", "Target") is None


def test_compiler_read_only_effect_overrides_lying_model_write(tmp_path):
    source = tmp_path / "Target.sol"
    source.write_text("pragma solidity ^0.8.20;\ncontract Target {\nuint256 public adminState;\nfunction guarded() external onlyOwner { adminState = 1; }\nfunction getter() external { uint256 x = adminState; x; }\n}\n", encoding="utf-8")
    contract = ContractModel("Target", str(source), (
        FunctionModel("guarded", "external", ("onlyOwner",), ("adminState",), (), 4),
        FunctionModel("getter", "external", (), ("adminState",), (), 5),
    ), state_variables=("adminState",))
    evidence = [_evidence("guarded", "writes", "adminState"), _evidence("getter", "reads", "adminState")]
    assert generate_structural_access_control_hypotheses(contract, evidence) == ()


def test_missing_compiler_effects_fall_back_without_inventing_semantics(tmp_path):
    source = tmp_path / "Target.sol"
    source.write_text("pragma solidity ^0.8.20;\ncontract Target {\nuint256 public adminState;\nfunction guarded() external onlyOwner { adminState = 1; }\nfunction mutator() external { adminState = 2; }\n}\n", encoding="utf-8")
    contract = ContractModel("Target", str(source), (
        FunctionModel("guarded", "external", ("onlyOwner",), (), (), 4),
        FunctionModel("mutator", "external", (), (), (), 5),
    ), state_variables=("adminState",))
    hypotheses = generate_structural_access_control_hypotheses(contract, [_evidence("guarded", "writes", "adminState")])
    assert [h.target_function for h in hypotheses] == ["mutator"]
    assert hypotheses[0].evidence_ids == ("E-MODEL-mutator",)


def test_compiler_backed_candidate_records_ast_provenance(tmp_path):
    source = tmp_path / "Target.sol"
    source.write_text("pragma solidity ^0.8.20;\ncontract Target {\nuint256 public adminState;\nfunction guarded() external onlyOwner { adminState = 1; }\nfunction mutator() external { adminState = 2; }\n}\n", encoding="utf-8")
    contract = ContractModel("Target", str(source), (
        FunctionModel("guarded", "external", ("onlyOwner",), (), (), 4),
        FunctionModel("mutator", "external", (), (), (), 5),
    ), state_variables=("adminState",))
    evidence = [_evidence("guarded", "writes", "adminState"), _evidence("mutator", "writes", "adminState")]
    hypotheses = generate_structural_access_control_hypotheses(contract, evidence)
    assert [h.target_function for h in hypotheses] == ["mutator"]
    assert hypotheses[0].evidence_ids == ("E-AST-STATE-mutator",)

def test_contract_qualification_prevents_cross_contract_state_leakage():
    index = build_state_effect_index([
        SemanticRelationshipEvidence(
            contract="BaseA",
            function="balanceOf",
            relation="writes",
            target="balance",
            confidence=0.98,
            source="solc-json-ast:basea.sol",
        ),
        SemanticRelationshipEvidence(
            contract="BaseB",
            function="balanceOf",
            relation="writes",
            target="balance",
            confidence=0.98,
            source="solc-json-ast:baseb.sol",
        ),
    ])
    assert state_writes_for_function(index, "balanceOf", "Target") is None
    assert state_writes_for_function(index, "balanceOf", "BaseA") == ("balance",)
    assert state_writes_for_function(index, "balanceOf", "BaseB") == ("balance",)
