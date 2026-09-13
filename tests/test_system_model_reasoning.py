from pathlib import Path

from cydra.graph_semantics import validate_graph
from cydra.solidity_model import parse_solidity
from cydra.solidity_system_model import project_contracts
from cydra.system_model_reasoning import derive_authorization_reasoning, materialize_authorization_observations, materialize_authorization_reasoning, plan_authorization_observations


def test_system_model_derives_competing_authorization_explanations_without_function_name_rules():
    from cydra.models import ContractModel, FunctionModel

    contract = ContractModel(
        "Fixture",
        "Fixture.sol",
        (
            FunctionModel("rotate", "external", ("onlyAdmin",), ("admin",), (), 10),
            FunctionModel("changeRoute", "external", (), ("route",), (), 20),
        ),
        state_variables=("admin", "route"),
    )
    model = project_contracts((contract,))
    derived = derive_authorization_reasoning(model)

    assert len(derived) == 1
    assert derived[0].protected_functions == ("function:Fixture.sol:Fixture:rotate()",)
    assert derived[0].unprotected_functions == ("function:Fixture.sol:Fixture:changeRoute()",)
    assert "observed on protected sibling operations" in derived[0].invariant.statement
    assert len(derived[0].hypotheses) == 2
    assert derived[0].hypotheses[0].hypothesis_id.startswith("H-SYS-AUTH-Fixture-")
    assert derived[0].hypotheses[1].hypothesis_id.startswith("H-SYS-ALT-Fixture-")
    assert {h.belief for h in derived[0].hypotheses} == {0.5}


def test_system_model_reasoning_selects_and_materializes_information_gain_observation():
    from cydra.models import ContractModel, FunctionModel

    contract = ContractModel(
        "Fixture",
        "Fixture.sol",
        (
            FunctionModel("rotate", "external", ("onlyAdmin",), ("admin",), (), 10),
            FunctionModel("changeRoute", "external", (), ("route",), (), 20),
        ),
    )
    model = project_contracts((contract,))
    reasoning = derive_authorization_reasoning(model)[0]
    plans = plan_authorization_observations(reasoning)

    assert len(plans) == 1
    assert plans[0].observation_id.startswith("OBS-AUTH-")
    assert plans[0].information_gain > 0.0
    assert plans[0].utility > 0.0
    assert "hypothesis-specific outcome predictions" in plans[0].rationale

    materialize_authorization_reasoning(model)
    materialized = materialize_authorization_observations(model, reasoning)
    assert materialized == plans
    assert model.nodes[f"observation:{plans[0].observation_id}"].attributes["status"] == "planned"
    assert sum(1 for edge in model.edges if edge.relation == "tests") == 2
    assert sum(1 for edge in model.edges if edge.relation == "targets") == 1
    assert validate_graph(model) == []


def test_safe_system_model_does_not_emit_boundary_candidate():
    from cydra.models import ContractModel, FunctionModel

    contract = ContractModel(
        "Fixture",
        "Fixture.sol",
        (
            FunctionModel("rotate", "external", ("onlyAdmin",), ("admin",), (), 10),
            FunctionModel("changeRoute", "external", ("onlyAdmin",), ("route",), (), 20),
        ),
        state_variables=("admin", "route"),
    )
    model = project_contracts((contract,))
    assert derive_authorization_reasoning(model) == ()


def test_benchmark_001_real_solidity_model_reaches_canonical_reasoning():
    root = Path(__file__).resolve().parents[1]
    contracts = parse_solidity(root / "benchmarks/alchemix_missing_access_control/Target.sol")
    model = project_contracts(tuple(contracts))
    derived = materialize_authorization_reasoning(model)

    assert len(derived) == 1
    hypotheses = derived[0].hypotheses
    assert any("setWhitelist" in hypothesis.statement for hypothesis in hypotheses)
    assert any("alternate enforcement path" in hypothesis.statement for hypothesis in hypotheses)
    assert any(node.kind == "invariant" and node.attributes.get("provenance") == "system_model_reasoning" for node in model.nodes.values())
    assert any(node.kind == "hypothesis" and node.attributes.get("provenance") == "system_model_reasoning" for node in model.nodes.values())
    assert sum(1 for edge in model.edges if edge.relation == "informs") == 2
    assert validate_graph(model) == []
