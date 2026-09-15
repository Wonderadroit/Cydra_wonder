from cydra.ast_dataflow import SemanticRelationshipEvidence
from cydra.system_model import SystemModel


def test_semantic_state_relations_project_to_state_variable_nodes():
    model = SystemModel()
    edge = model.add_ast_evidence(SemanticRelationshipEvidence(
        contract="Fixture",
        function="mutate",
        relation="transition_expression",
        target="value",
        confidence=0.98,
        source="solc-json-ast:Fixture.sol",
        ast_node_id=31,
        source_location=(31, 1, 1),
        function_ast_node_id=20,
        target_ast_node_id=10,
        metadata={"semantic_relation": "read_write"},
    ))
    assert model.nodes[edge.target].kind == "state_variable"
    assert edge.attributes["semantic_relation"] == "read_write"


def test_compiler_relation_preserves_declaration_identity_and_provenance():
    model = SystemModel()
    edge = model.add_ast_evidence(SemanticRelationshipEvidence(
        contract="Fixture",
        function="get",
        relation="reads",
        target="value",
        confidence=0.98,
        source="solc-json-ast:Fixture.sol",
        ast_node_id=31,
        source_location=(31, 1, 1),
        function_ast_node_id=20,
        target_ast_node_id=10,
    ))
    target = model.nodes[edge.target]
    assert target.kind == "state_variable"
    assert target.attributes["ast_node_id"] == 10
    assert target.attributes["identity_status"] == "compiler_declaration"
    assert target.attributes["provenance"] == "solc-json-ast:Fixture.sol"
