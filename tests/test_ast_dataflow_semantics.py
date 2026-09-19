from cydra.ast_dataflow import extract_ast_relationships


def _identifier(node_id, declaration, name):
    return {"nodeType": "Identifier", "id": node_id, "name": name,
            "referencedDeclaration": declaration, "src": f"{node_id}:1:1"}


def _function(function_id, name, body):
    return {"nodeType": "FunctionDefinition", "id": function_id, "name": name,
            "kind": "function", "scope": 2,
            "body": {"nodeType": "Block", "id": function_id + 100, "statements": body}}


def _ast(statements):
    return {"nodeType": "SourceUnit", "id": 1, "children": [
        {"nodeType": "ContractDefinition", "id": 2, "name": "Fixture"},
        {"nodeType": "VariableDeclaration", "id": 10, "name": "value", "stateVariable": True},
        *statements,
    ]}


def _relations(ast):
    return {(item.function, item.relation, item.target) for item in extract_ast_relationships(ast, "Fixture.sol")}


def test_getter_is_reads_not_writes():
    ast = _ast([_function(20, "get", [
        {"nodeType": "Return", "id": 30, "expression": _identifier(31, 10, "value")}
    ])])
    relations = _relations(ast)
    assert ("get", "reads", "value") in relations
    assert ("get", "writes", "value") not in relations
    assert ("get", "transition_expression", "value") not in relations


def test_direct_assignment_is_write():
    ast = _ast([_function(20, "set", [
        {"nodeType": "Assignment", "id": 30, "operator": "=",
         "leftHandSide": _identifier(31, 10, "value"),
         "rightHandSide": {"nodeType": "Literal", "id": 32, "value": "7"}}
    ])])
    relations = _relations(ast)
    assert ("set", "writes", "value") in relations


def test_compound_assignment_is_read_write_context():
    ast = _ast([_function(20, "add", [
        {"nodeType": "Assignment", "id": 30, "operator": "+=",
         "leftHandSide": _identifier(31, 10, "value"),
         "rightHandSide": {"nodeType": "Literal", "id": 32, "value": "1"}}
    ])])
    relations = _relations(ast)
    assert ("add", "transition_expression", "value") in relations


def test_mapping_index_write_is_write_and_index_state_read_is_preserved():
    ast = _ast([_function(20, "set", [
        {"nodeType": "Assignment", "id": 30, "operator": "=",
         "leftHandSide": {"nodeType": "IndexAccess", "id": 31,
                           "baseExpression": _identifier(32, 10, "value"),
                           "indexExpression": _identifier(33, 10, "value")},
         "rightHandSide": {"nodeType": "Literal", "id": 34, "value": "1"}}
    ])])
    relations = _relations(ast)
    assert ("set", "writes", "value") in relations
    assert ("set", "reads", "value") in relations


def test_increment_and_delete_have_write_context():
    ast = _ast([_function(20, "mutate", [
        {"nodeType": "UnaryOperation", "id": 30, "operator": "++",
         "subExpression": _identifier(31, 10, "value")},
        {"nodeType": "UnaryOperation", "id": 32, "operator": "delete",
         "subExpression": _identifier(33, 10, "value")},
    ])])
    relations = _relations(ast)
    assert ("mutate", "transition_expression", "value") in relations
    assert ("mutate", "writes", "value") in relations


def test_ast_semantics_ignore_source_comment_or_string_text():
    ast = _ast([_function(20, "clean", [
        {"nodeType": "ExpressionStatement", "id": 30,
         "expression": {"nodeType": "Literal", "id": 31,
                         "kind": "string", "value": "value = 999;"}}
    ])])
    assert not _relations(ast)


def test_transition_evidence_preserves_operator_semantics():
    ast = _ast([_function(20, "add", [
        {"nodeType": "Assignment", "id": 30, "operator": "+=",
         "leftHandSide": _identifier(31, 10, "value"),
         "rightHandSide": {"nodeType": "Literal", "id": 32, "value": "1"}}
    ])])
    evidence = extract_ast_relationships(ast, "Fixture.sol")
    transition = next(item for item in evidence if item.relation == "transition_expression")
    assert transition.metadata["operator"] == "+="
    assert transition.metadata["semantic_relation"] == "read_write"
