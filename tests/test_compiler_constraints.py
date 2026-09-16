from cydra.compiler_constraints import extract_parameter_constraints


def _identifier(node_id, name, ref):
    return {"nodeType": "Identifier", "id": node_id, "name": name, "referencedDeclaration": ref}


def _literal(node_id, value):
    return {"nodeType": "Literal", "id": node_id, "kind": "number", "value": value}


def test_extracts_require_predicate_linked_to_parameter():
    ast = {
        "nodeType": "SourceUnit", "id": 1,
        "nodes": [{
            "nodeType": "ContractDefinition", "id": 2, "name": "Target",
            "nodes": [{
                "nodeType": "FunctionDefinition", "id": 3, "name": "setLimit", "kind": "function", "scope": 2,
                "parameters": {"nodeType": "ParameterList", "parameters": [
                    {"nodeType": "VariableDeclaration", "id": 10, "name": "limit", "typeDescriptions": {"typeString": "uint256"}}
                ]},
                "body": {"nodeType": "Block", "id": 4, "statements": [{
                    "nodeType": "ExpressionStatement", "id": 5,
                    "expression": {"nodeType": "FunctionCall", "id": 6,
                        "expression": {"nodeType": "Identifier", "id": 7, "name": "require"},
                        "arguments": [{"nodeType": "BinaryOperation", "id": 8, "operator": ">", 
                            "leftExpression": _identifier(11, "limit", 10), "rightExpression": _literal(12, "0")}]
                    }
                }]}
            }]
        }]
    }

    evidence = extract_parameter_constraints(ast, "Target.sol")

    assert len(evidence) == 1
    assert evidence[0].contract == "Target"
    assert evidence[0].function == "setLimit"
    assert evidence[0].parameter == "limit"
    assert evidence[0].parameter_index == 0
    assert evidence[0].predicate == "limit > 0"
    assert evidence[0].kind == "require"


def test_extracts_revert_guard_and_preserves_address_expression():
    ast = {
        "nodeType": "SourceUnit", "id": 1,
        "nodes": [{
            "nodeType": "ContractDefinition", "id": 2, "name": "Target",
            "nodes": [{
                "nodeType": "FunctionDefinition", "id": 3, "name": "initialize", "kind": "function", "scope": 2,
                "parameters": {"nodeType": "ParameterList", "parameters": [
                    {"nodeType": "VariableDeclaration", "id": 10, "name": "protocol", "typeDescriptions": {"typeString": "address"}}
                ]},
                "body": {"nodeType": "Block", "id": 4, "statements": [{
                    "nodeType": "IfStatement", "id": 5,
                    "condition": {"nodeType": "BinaryOperation", "id": 8, "operator": "==",
                        "leftExpression": _identifier(11, "protocol", 10),
                        "rightExpression": {"nodeType": "FunctionCall", "id": 12,
                            "expression": {"nodeType": "Identifier", "id": 13, "name": "address"},
                            "arguments": [_literal(14, "0")]}},
                    "trueBody": {"nodeType": "Block", "id": 15, "statements": [
                        {"nodeType": "RevertStatement", "id": 16}
                    ]}
                }]}
            }]
        }]
    }

    evidence = extract_parameter_constraints(ast, "Target.sol")

    assert len(evidence) == 1
    assert evidence[0].parameter == "protocol"
    assert evidence[0].predicate == "protocol == address(0)"
    assert evidence[0].kind == "revert_guard"


def test_ignores_constraints_that_do_not_reference_parameters():
    ast = {
        "nodeType": "SourceUnit", "id": 1,
        "nodes": [{
            "nodeType": "ContractDefinition", "id": 2, "name": "Target",
            "nodes": [{
                "nodeType": "FunctionDefinition", "id": 3, "name": "setLimit", "kind": "function", "scope": 2,
                "parameters": {"nodeType": "ParameterList", "parameters": [
                    {"nodeType": "VariableDeclaration", "id": 10, "name": "limit", "typeDescriptions": {"typeString": "uint256"}}
                ]},
                "body": {"nodeType": "Block", "id": 4, "statements": [{
                    "nodeType": "ExpressionStatement", "id": 5,
                    "expression": {"nodeType": "FunctionCall", "id": 6,
                        "expression": {"nodeType": "Identifier", "id": 7, "name": "require"},
                        "arguments": [{"nodeType": "BinaryOperation", "id": 8, "operator": ">",
                            "leftExpression": _literal(11, "1"), "rightExpression": _literal(12, "0")}]
                    }
                }]}
            }]
        }]
    }

    assert extract_parameter_constraints(ast, "Target.sol") == ()
