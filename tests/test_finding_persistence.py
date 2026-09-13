import pytest
from cydra.causal_chain import CausalChain, persist_causal_chain
from cydra.finding import Finding
from cydra.finding_gate import FindingCandidate
from cydra.finding_persistence import persist_finding
from cydra.impact import ImpactAssessment, ImpactLevel
from cydra.system_model import Edge, Node, SystemModel


def build(support=True):
    model=SystemModel()
    for node_id,kind in (("hypothesis:h1","hypothesis"),("observation:o1","observation"),("evidence:e1","evidence"),("verification:v1","evidence"),("belief:b1","belief")):
        attributes={}
        if kind=="hypothesis": attributes={"hypothesis_id":"hypothesis:h1","state":"supported","belief":0.9}
        if kind=="belief": attributes={"hypothesis_id":"hypothesis:h1"}
        model.add_node(Node(node_id,kind,node_id,attributes))
    if support: model.add_edge(Edge("evidence:e1","supports","hypothesis:h1"))
    persist_causal_chain(model,CausalChain("causal:c1","hypothesis:h1","observation:o1","evidence:e1","verification:v1","belief:b1"))
    return model


def finding():
    return Finding("finding:1","Unauthorized state transition","causally verified", "HIGH", ImpactAssessment(ImpactLevel.HIGH,"vault","protected funds can be altered"),("contract:Vault",),("evidence:e1",),"hypothesis:h1",causal_chain_id="causal:c1")


def test_ready_finding_is_persisted_and_model_remains_valid():
    model=build(True)
    persist_finding(model,candidate=FindingCandidate(True,False,True,True,True,True),finding=finding())
    assert model.nodes["finding:1"].attributes["persisted"] is True
    assert model.validate() == []


def test_unresolved_causal_finding_cannot_be_persisted():
    model=build(False)
    with pytest.raises(ValueError,match="explicitly support"):
        persist_finding(model,candidate=FindingCandidate(True,False,True,True,True,True),finding=finding())
