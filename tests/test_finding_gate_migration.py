from cydra.causal_chain import CausalChain, persist_causal_chain
from cydra.causal_verification import CausalVerificationState, verify_persisted_causal_chain
from cydra.finding_gate import FindingCandidate, GateDecision, evaluate_finding_graph
from cydra.impact import ImpactAssessment, ImpactLevel
from cydra.system_model import Edge, Node, SystemModel


def build(support=True):
    model = SystemModel()
    for node_id, kind in (("hypothesis:h1", "hypothesis"), ("observation:o1", "observation"), ("evidence:e1", "evidence"), ("verification:v1", "evidence"), ("belief:b1", "belief")):
        model.add_node(Node(node_id, kind, node_id, {"hypothesis_id": "hypothesis:h1"} if kind == "belief" else {}))
    if support:
        model.add_edge(Edge("evidence:e1", "supports", "hypothesis:h1"))
    persist_causal_chain(model, CausalChain("causal:c1", "hypothesis:h1", "observation:o1", "evidence:e1", "verification:v1", "belief:b1"))
    return model


def test_finding_gate_reaches_ready_only_after_causal_verification():
    model = build(True)
    candidate = FindingCandidate(True, False, True, True, True, True)
    result = evaluate_finding_graph(model, candidate=candidate, finding_id="finding:1", hypothesis_id="hypothesis:h1", evidence_ids=("evidence:e1",), causal_chain_id="causal:c1")
    assert result.decision is GateDecision.READY
    assert verify_persisted_causal_chain(model, "causal:c1").state is CausalVerificationState.VERIFIED


def test_finding_gate_preserves_unresolved_causality():
    model = build(False)
    candidate = FindingCandidate(True, False, True, True, True, True)
    result = evaluate_finding_graph(model, candidate=candidate, finding_id="finding:1", hypothesis_id="hypothesis:h1", evidence_ids=("evidence:e1",), causal_chain_id="causal:c1")
    assert result.decision is GateDecision.UNRESOLVED


def test_impact_assessment_unknown_is_not_assessed():
    assert not ImpactAssessment(ImpactLevel.UNKNOWN, "vault", "").assessed
