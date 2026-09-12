from cydra.contradiction_model import Contradiction, persist_contradiction
from cydra.contradiction_re_evaluation import ContradictionDisposition, reevaluate_contradiction
from cydra.contradiction_re_evaluation_model import persist_re_evaluation
from cydra.graph_semantics import validate_graph
from cydra.system_model import Node, SystemModel


def model_with_contradiction():
    model = SystemModel()
    model.add_node(Node("hypothesis:h1", "hypothesis", "H1"))
    model.add_node(Node("hypothesis:h2", "hypothesis", "H2"))
    model.add_node(Node("evidence:e1", "evidence", "E1"))
    persist_contradiction(model, Contradiction("contradiction:c1", ("evidence:e1",), ("hypothesis:h1", "hypothesis:h2")))
    return model


def test_inconclusive_re_evaluation_is_persisted_without_resolving_contradiction():
    model = model_with_contradiction()
    result = reevaluate_contradiction("contradiction:c1", "evidence:e1", supports_hypothesis=None)
    assert result.disposition is ContradictionDisposition.INCONCLUSIVE
    persist_re_evaluation(model, result, "reevaluation:r1")
    assert model.nodes["reevaluation:r1"].attributes["disposition"] == "inconclusive"
    assert model.nodes["contradiction:c1"].attributes["contradiction"] is True
    assert validate_graph(model) == []


def test_re_evaluation_cannot_overwrite_existing_record():
    model = model_with_contradiction()
    result = reevaluate_contradiction("contradiction:c1", "evidence:e1", supports_hypothesis=True)
    persist_re_evaluation(model, result, "reevaluation:r1")
    try:
        persist_re_evaluation(model, result, "reevaluation:r1")
    except ValueError as exc:
        assert "already exists" in str(exc)
    else:
        raise AssertionError("re-evaluation record was overwritten")
