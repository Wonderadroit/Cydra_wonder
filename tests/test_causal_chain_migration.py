from cydra.causal_chain import CausalChain, persist_causal_chain
from cydra.causal_reconstruction import reconstruct_causal_chain
from cydra.causal_verification import CausalVerificationState, verify_persisted_causal_chain
from cydra.graph_semantics import validate_graph
from cydra.system_model import Node, SystemModel


def model_with_chain_nodes():
    model = SystemModel()
    for node_id, kind in (("hypothesis:h1", "hypothesis"), ("observation:o1", "observation"), ("evidence:e1", "evidence"), ("verification:v1", "evidence"), ("belief_update:b1", "belief")):
        model.add_node(Node(node_id, kind, node_id, {"hypothesis_id": "hypothesis:h1"} if kind == "belief" else {}))
    return model


def chain():
    return CausalChain("causal:c1", "hypothesis:h1", "observation:o1", "evidence:e1", "verification:v1", "belief_update:b1")


def test_causal_chain_persists_with_canonical_semantics():
    model = model_with_chain_nodes()
    persist_causal_chain(model, chain())
    assert validate_graph(model) == []
    trace = reconstruct_causal_chain(model, "causal:c1")
    assert trace.evidence_ids == ("evidence:e1", "verification:v1")


def test_causal_verification_is_unresolved_without_explicit_support():
    model = model_with_chain_nodes()
    persist_causal_chain(model, chain())
    result = verify_persisted_causal_chain(model, "causal:c1")
    assert result.state is CausalVerificationState.UNRESOLVED


def test_causal_verification_requires_explicit_support_and_matching_belief():
    model = model_with_chain_nodes()
    persist_causal_chain(model, chain())
    model.connect("evidence:e1", "supports", "hypothesis:h1", provenance="test")
    result = verify_persisted_causal_chain(model, "causal:c1")
    assert result.state is CausalVerificationState.VERIFIED


def test_broken_chain_is_rejected():
    model = model_with_chain_nodes()
    persist_causal_chain(model, chain())
    model.edges = [e for e in model.edges if not (e.source == "causal:c1" and e.relation == "plans")]
    result = verify_persisted_causal_chain(model, "causal:c1")
    assert result.state is CausalVerificationState.REJECTED
