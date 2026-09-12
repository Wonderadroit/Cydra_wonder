from cydra.contradiction_model import Contradiction, persist_contradiction
from cydra.contradiction_resolution_model import plan_contradiction_resolution, persist_resolution_plan
from cydra.graph_semantics import contradiction_pairs, validate_graph
from cydra.system_model import Node, SystemModel
from cydra.test_planning import ObservationOption


def base_model():
    model = SystemModel()
    model.add_node(Node("hypothesis:h1", "hypothesis", "H1"))
    model.add_node(Node("hypothesis:h2", "hypothesis", "H2"))
    model.add_node(Node("evidence:e1", "evidence", "E1"))
    model.add_node(Node("observation:o1", "observation", "O1"))
    return model


def test_competing_hypotheses_are_persisted_as_explicit_contradiction():
    model = base_model()
    contradiction = Contradiction("contradiction:c1", ("evidence:e1",), ("hypothesis:h1", "hypothesis:h2"))
    persist_contradiction(model, contradiction)
    assert model.nodes["contradiction:c1"].attributes["competing_hypothesis_ids"] == ["hypothesis:h1", "hypothesis:h2"]
    assert contradiction_pairs(model) == [("hypothesis:h1", "hypothesis:h2")]
    assert validate_graph(model) == []


def test_resolution_planner_prefers_distinguishing_observation():
    contradiction = Contradiction("contradiction:c1", ("evidence:e1",), ("hypothesis:h1", "hypothesis:h2"))
    plans = plan_contradiction_resolution(contradiction, (
        ObservationOption("o-neutral", "non-distinguishing", ("same",), 1.0),
        ObservationOption("o-distinguishing", "distinguishing", ("h1", "h2"), 1.0),
    ))
    assert plans[0].observation_id == "o-distinguishing"
    assert plans[0].utility > plans[1].utility


def test_resolution_plan_is_persisted_without_execution():
    model = base_model()
    persist_contradiction(model, Contradiction("contradiction:c1", ("evidence:e1",), ("hypothesis:h1", "hypothesis:h2")))
    plan = plan_contradiction_resolution(Contradiction("contradiction:c1", ("evidence:e1",), ("hypothesis:h1", "hypothesis:h2")), (ObservationOption("observation:o1", "distinguish", ("h1", "h2"), 1.0),))[0]
    persist_resolution_plan(model, plan, "resolution:r1")
    assert model.nodes["resolution:r1"].attributes["executed"] is False
    assert validate_graph(model) == []


def test_contradiction_requires_two_distinct_hypotheses():
    model = base_model()
    try:
        persist_contradiction(model, Contradiction("contradiction:c1", (), ("hypothesis:h1",)))
    except ValueError as exc:
        assert "at least two" in str(exc)
    else:
        raise AssertionError("single-hypothesis contradiction was accepted")
