from cydra.contradiction_model import Contradiction, persist_contradiction
from cydra.contradiction_re_evaluation import ContradictionDisposition
from cydra.reasoning_loop import run_reasoning_loop
from cydra.graph_semantics import validate_graph
from cydra.system_model import Node, SystemModel


def model():
    m = SystemModel()
    m.add_node(Node("hypothesis:h1", "hypothesis", "H1"))
    m.add_node(Node("hypothesis:h2", "hypothesis", "H2"))
    m.add_node(Node("evidence:e1", "evidence", "E1"))
    persist_contradiction(m, Contradiction("contradiction:c1", ("evidence:e1",), ("hypothesis:h1", "hypothesis:h2")))
    return m


def test_reasoning_loop_preserves_inconclusive_uncertainty():
    m = model()
    result = run_reasoning_loop(m, contradiction_id="contradiction:c1", evidence_id="evidence:e1", belief_id="belief:h1", prior_confidence=0.6, supports_hypothesis=None, re_evaluation_id="reevaluation:r1", belief_update_id="belief_update:b1")
    assert result.re_evaluation.disposition is ContradictionDisposition.INCONCLUSIVE
    assert result.belief_update.posterior_confidence == 0.6
    assert result.current_confidence == 0.6
    assert m.nodes["belief_update:b1"].attributes["disposition"] == "inconclusive"
    assert validate_graph(m) == []


def test_reasoning_loop_moves_belief_only_when_evidence_resolves():
    m = model()
    result = run_reasoning_loop(m, contradiction_id="contradiction:c1", evidence_id="evidence:e1", belief_id="belief:h1", prior_confidence=0.6, supports_hypothesis=True, re_evaluation_id="reevaluation:r1", belief_update_id="belief_update:b1")
    assert result.re_evaluation.disposition is ContradictionDisposition.SUPPORTED
    assert result.current_confidence > 0.6
