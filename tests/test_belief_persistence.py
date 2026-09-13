from cydra.belief_persistence import persist_belief_update
from cydra.hypotheses import BeliefUpdate, Hypothesis, HypothesisState
from cydra.system_model import Node, SystemModel


def test_belief_transition_is_persisted_with_provenance():
    model=SystemModel()
    model.add_node(Node("hypothesis:h1","hypothesis","h1"))
    model.add_node(Node("evidence:e1","evidence","e1"))
    hypothesis=Hypothesis("hypothesis:h1","unauthorized mutation",0.5)
    update=BeliefUpdate("hypothesis:h1",0.5,0.8,HypothesisState.UNRESOLVED,HypothesisState.SUPPORTED,("evidence:e1",),"supporting evidence")
    persist_belief_update(model,hypothesis,update,update_id="belief:b1")
    assert model.nodes["belief:b1"].attributes["posterior_belief"] == 0.8
    assert model.neighbors("hypothesis:h1","updated_to") == ["belief:b1"]
    assert model.neighbors("evidence:e1","updates") == ["belief:b1"]
