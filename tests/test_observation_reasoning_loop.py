from cydra.system_model import Node, SystemModel
from cydra.observation_outcomes import record_observation_outcome
from cydra.contradiction_re_evaluation import ContradictionDisposition, reevaluate_contradiction
from cydra.causal_reconstruction import reconstruct_causal_chain


def test_external_observation_outcome_is_recorded_as_evidence():
    model = SystemModel()
    model.add_node(Node("observation:obs-1", "observation", "probe", {"status": "planned"}))
    outcome = record_observation_outcome(model, observation_id="obs-1", outcome_id="out-1", result="PASS", source="foundry", confidence=0.9)
    assert outcome.outcome_id == "out-1"
    assert model.nodes["observation:obs-1"].attributes["status"] == "completed"
    assert model.nodes["observation_outcome:out-1"].kind == "evidence"
    assert model.neighbors("observation:obs-1", "produced") == ["observation_outcome:out-1"]


def test_contradiction_re_evaluation_preserves_inconclusive_state():
    result = reevaluate_contradiction("c-1", "e-1", supports_hypothesis=None)
    assert result.disposition is ContradictionDisposition.INCONCLUSIVE


def test_causal_reconstruction_rejects_missing_link():
    model = SystemModel()
    model.add_node(Node("hypothesis:h1", "hypothesis", "h1"))
    model.add_node(Node("chain:1", "causal_chain", "chain"))
    model.connect("hypothesis:h1", "motivates", "chain:1", causal_chain_id="chain:1")
    try:
        reconstruct_causal_chain(model, "chain:1")
    except ValueError as exc:
        assert "plans" in str(exc)
    else:
        raise AssertionError("broken causal chain was accepted")
