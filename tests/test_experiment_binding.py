import pytest

from cydra.experiment_binding import bind_experiment, validate_experiment_binding
from cydra.graph_semantics import validate_graph
from cydra.system_model import Edge, Node, SystemModel


def _model() -> SystemModel:
    model = SystemModel()
    model.add_node(Node("function:Fixture.sol:Fixture:rotate()", "function", "rotate", {"visibility": "external"}))
    model.add_node(Node("function:Fixture.sol:Fixture:changeRoute()", "function", "changeRoute", {"visibility": "external"}))
    model.add_node(Node("invariant:INV-1", "invariant", "authorization boundary"))
    model.add_node(Node("hypothesis:H1", "hypothesis", "changeRoute permits unauthorized mutation"))
    model.add_node(Node("hypothesis:H2", "hypothesis", "changeRoute has alternate enforcement"))
    model.add_node(Node("observation:OBS-1", "observation", "observe changeRoute", {"status": "planned", "target_function_id": "function:Fixture.sol:Fixture:changeRoute()"}))
    model.add_edge(Edge("observation:OBS-1", "targets", "invariant:INV-1"))
    model.add_edge(Edge("observation:OBS-1", "tests", "hypothesis:H1"))
    model.add_edge(Edge("observation:OBS-1", "tests", "hypothesis:H2"))
    return model


def test_binding_persists_exact_hypothesis_observation_and_function():
    model = _model()
    source = "// CYDRA-HYPOTHESIS: H1\nfunction testH1() public { target.changeRoute(); }"
    binding = bind_experiment(
        model,
        hypothesis_id="H1",
        observation_id="OBS-1",
        target_function_id="function:Fixture.sol:Fixture:changeRoute()",
        generated_source=source,
    )
    assert validate_experiment_binding(model, binding)
    attrs = model.nodes["observation:OBS-1"].attributes
    assert attrs["bound_hypothesis_id"] == "hypothesis:H1"
    assert attrs["target_function_id"] == "function:Fixture.sol:Fixture:changeRoute()"
    assert attrs["binding_status"] == "bound"
    assert validate_graph(model) == []


def test_binding_rejects_wrong_generated_target_and_does_not_mutate_graph():
    model = _model()
    before = model.export()
    with pytest.raises(ValueError, match="does not invoke target function"):
        bind_experiment(
            model,
            hypothesis_id="H1",
            observation_id="OBS-1",
            target_function_id="function:Fixture.sol:Fixture:changeRoute()",
            generated_source="// CYDRA-HYPOTHESIS: H1\nfunction testH1() public { target.rotate(); }",
        )
    assert model.export() == before


def test_binding_rejects_wrong_hypothesis_even_when_test_calls_correct_function():
    model = _model()
    with pytest.raises(ValueError, match="observation does not test"):
        bind_experiment(
            model,
            hypothesis_id="UNKNOWN",
            observation_id="OBS-1",
            target_function_id="function:Fixture.sol:Fixture:changeRoute()",
            generated_source="// CYDRA-HYPOTHESIS: UNKNOWN\nfunction test() public { target.changeRoute(); }",
        )


def test_conflicting_rebinding_is_fail_closed():
    model = _model()
    bind_experiment(
        model,
        hypothesis_id="H1",
        observation_id="OBS-1",
        target_function_id="function:Fixture.sol:Fixture:changeRoute()",
        generated_source="// CYDRA-HYPOTHESIS: H1\nfunction test() public { target.changeRoute(); }",
    )
    before = model.export()
    with pytest.raises(ValueError, match="conflicting experiment binding"):
        bind_experiment(
            model,
            hypothesis_id="H2",
            observation_id="OBS-1",
            target_function_id="function:Fixture.sol:Fixture:changeRoute()",
            generated_source="// CYDRA-HYPOTHESIS: H2\nfunction test() public { target.changeRoute(); }",
        )
    assert model.export() == before
