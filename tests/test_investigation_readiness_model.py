from cydra.investigation_readiness import ReadinessState, assess_system_model_readiness
from cydra.system_model import Edge, Node, SystemModel


def test_model_readiness_detects_unexecuted_hypothesis():
    model = SystemModel()
    model.add_node(Node("hypothesis:h1", "hypothesis", "candidate", {"state": "unresolved", "belief": 0.5}))
    model.add_node(Node("observation:o1", "observation", "probe", {"status": "planned", "executed": False}))
    model.add_edge(Edge("observation:o1", "tests", "hypothesis:h1"))

    result = assess_system_model_readiness(model)

    assert result.state is ReadinessState.BLOCKED
    assert result.evidence_coverage == 0.0
    assert result.hypothesis_coverage == 0.0
    assert result.experiment_validity == 0.0
    assert "evidence coverage is incomplete" in result.unresolved_reasons


def test_model_readiness_requires_bound_externally_produced_execution_evidence():
    model = SystemModel()
    model.add_node(Node("hypothesis:h1", "hypothesis", "candidate", {"state": "supported", "belief": 0.8}))
    model.add_node(Node("observation:o1", "observation", "probe", {
        "status": "completed",
        "executed": True,
        "binding_status": "bound",
        "outcome_id": "run-1",
    }))
    model.add_node(Node("observation_outcome:run-1", "evidence", "execution evidence", {"confidence": 1.0}))
    model.add_node(Node("evidence:e1", "evidence", "hypothesis evidence", {"confidence": 1.0}))
    model.add_node(Node("invariant:i1", "invariant", "property", {"confidence": 1.0}))
    model.add_edge(Edge("observation:o1", "tests", "hypothesis:h1"))
    model.add_edge(Edge("observation:o1", "produced", "observation_outcome:run-1", {"executed_externally": True}))
    model.add_edge(Edge("observation_outcome:run-1", "supports", "hypothesis:h1"))
    model.add_edge(Edge("evidence:e1", "supports", "hypothesis:h1"))

    result = assess_system_model_readiness(model)

    assert result.evidence_coverage == 1.0
    assert result.hypothesis_coverage == 1.0
    assert result.experiment_validity == 1.0
    assert result.model_confidence == 1.0
    assert result.state is ReadinessState.READY


def test_flagged_execution_without_provenance_is_not_ready():
    model = SystemModel()
    model.add_node(Node("hypothesis:h1", "hypothesis", "candidate", {"state": "supported"}))
    model.add_node(Node("observation:o1", "observation", "probe", {"status": "completed", "executed": True}))
    model.add_node(Node("invariant:i1", "invariant", "property", {"confidence": 1.0}))
    model.add_edge(Edge("observation:o1", "tests", "hypothesis:h1"))

    result = assess_system_model_readiness(model)

    assert result.experiment_validity == 0.0
    assert result.hypothesis_coverage == 0.0
    assert result.state is ReadinessState.BLOCKED
    assert "one or more observations lack bound, externally produced execution evidence" in result.unresolved_reasons


def test_unresolved_competing_hypotheses_reduce_contradiction_clearance():
    model = SystemModel()
    model.add_node(Node("hypothesis:h1", "hypothesis", "h1", {"state": "unresolved"}))
    model.add_node(Node("hypothesis:h2", "hypothesis", "h2", {"state": "unresolved"}))
    model.add_node(Node("evidence:c1", "evidence", "contradiction", {
        "contradiction": True,
        "competing_hypothesis_ids": ["hypothesis:h1", "hypothesis:h2"],
    }))

    result = assess_system_model_readiness(model)

    assert result.contradiction_clearance == 0.0
    assert result.state is ReadinessState.BLOCKED
    assert "unresolved contradictions" in result.unresolved_reasons
