from cydra.causal_chain import CausalChain, persist_causal_chain
from cydra.finding import Finding
from cydra.finding_gate import FindingCandidate
from cydra.finding_persistence import persist_finding
from cydra.impact import ImpactAssessment, ImpactLevel
from cydra.system_model import Edge, Node, SystemModel


def test_reasoning_artifacts_survive_canonical_export_roundtrip():
    model=SystemModel()
    for node_id,kind in (("hypothesis:h1","hypothesis"),("observation:o1","observation"),("evidence:e1","evidence"),("verification:v1","evidence"),("belief:b1","belief")):
        attributes={}
        if kind=="hypothesis": attributes={"state":"causally_established","belief":0.9}
        if kind=="belief": attributes={"hypothesis_id":"hypothesis:h1"}
        model.add_node(Node(node_id,kind,node_id,attributes))
    model.add_edge(Edge("evidence:e1","supports","hypothesis:h1"))
    persist_causal_chain(model,CausalChain("causal:c1","hypothesis:h1","observation:o1","evidence:e1","verification:v1","belief:b1"))
    finding=Finding("finding:1","Verified finding","Evidence-backed causal result","HIGH",ImpactAssessment(ImpactLevel.HIGH,"vault","funds can be altered"),("contract:Vault",),("evidence:e1",),"hypothesis:h1",causal_chain_id="causal:c1")
    persist_finding(model,candidate=FindingCandidate(True,False,True,True,True,True),finding=finding)
    restored=SystemModel.from_dict(model.export())
    assert restored.export()==model.export()
