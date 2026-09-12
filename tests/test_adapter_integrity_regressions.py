from cydra.ast_dataflow import extract_ast_relationships
from cydra.models import ContractModel, FunctionModel, ParameterModel
from cydra.solidity_system_model import project_contracts


def fn(name, line, params=(), writes=(), external_calls=()):
    return FunctionModel(name, "external", (), tuple(writes), tuple(external_calls), line, tuple(params))


def test_solidity_projection_preserves_source_and_overloads_and_data_flow():
    contracts = (
        ContractModel(
            "Pool", "src/A.sol",
            (fn("set", 10, (ParameterModel("x", "uint256"),), writes=("value",), external_calls=("oracle",)),
             fn("set", 11, (ParameterModel("x", "address"),))),
            state_variables=("value",),
        ),
        ContractModel("Pool", "src/B.sol", (fn("set", 12),)),
    )
    model = project_contracts(contracts)
    assert len([n for n in model.nodes if n.startswith("function:")]) == 3
    assert any(e.relation == "writes" for e in model.edges)
    assert any(e.relation == "external_call" for e in model.edges)


def test_receive_and_fallback_keep_distinct_ast_kinds_when_state_evidence_exists():
    ast = {
        "nodeType": "SourceUnit",
        "nodes": [{
            "nodeType": "ContractDefinition",
            "id": 1,
            "name": "C",
            "nodes": [
                {"nodeType": "VariableDeclaration", "id": 10, "name": "value", "stateVariable": True},
                {"nodeType": "FunctionDefinition", "id": 2, "name": "", "kind": "receive", "scope": 1,
                 "body": {"nodeType": "Block", "statements": [{"nodeType": "Identifier", "id": 20, "referencedDeclaration": 10}]}},
                {"nodeType": "FunctionDefinition", "id": 3, "name": "", "kind": "fallback", "scope": 1,
                 "body": {"nodeType": "Block", "statements": [{"nodeType": "Identifier", "id": 30, "referencedDeclaration": 10}]}},
            ],
        }],
    }
    evidence = extract_ast_relationships(ast, "src/C.sol")
    assert [item.function for item in evidence] == ["receive", "fallback"]
    assert [item.metadata["function_kind"] for item in evidence] == ["receive", "fallback"]
