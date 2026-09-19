from cydra.ast_dataflow import SemanticRelationshipEvidence
from cydra.models import Experiment
from cydra.pipeline import investigate
from cydra.solidity_model import parse_solidity
from cydra.state_experiments import plan_cross_function_state_experiment
from cydra.structural_state import generate_cross_function_state_hypotheses


def _directional_semantic() -> tuple[SemanticRelationshipEvidence, ...]:
    return (
        SemanticRelationshipEvidence(
            contract="StateSurface",
            function="deposit",
            relation="transition_expression",
            target="balance",
            confidence=0.98,
            source="solc-json-ast:test",
            metadata={"semantic_relation": "read_write", "operator": "+="},
        ),
        SemanticRelationshipEvidence(
            contract="StateSurface",
            function="withdraw",
            relation="transition_expression",
            target="balance",
            confidence=0.98,
            source="solc-json-ast:test",
            metadata={"semantic_relation": "read_write", "operator": "-="},
        ),
    )


def test_cross_function_state_surface_does_not_promote_shared_state_without_semantics(tmp_path):
    source = tmp_path / "StateSurface.sol"
    source.write_text(
        """pragma solidity ^0.8.20;
contract StateSurface {
    uint256 internal balance;
    function deposit(uint256 amount) external { balance += amount; }
    function withdraw(uint256 amount) external { balance -= amount; }
}
""",
        encoding="utf-8",
    )

    result = investigate(source, reasoning_surfaces=(generate_cross_function_state_hypotheses,))
    assert not any(h.hypothesis_id.startswith("H-STATE-") for h in result.hypotheses)
    assert not any(i.invariant_id.startswith("INV-STATE-") for i in result.invariants)


def test_cross_function_state_surface_infers_opposing_transition_relationship(tmp_path):
    source = tmp_path / "StateSurface.sol"
    source.write_text(
        """pragma solidity ^0.8.20;
contract StateSurface {
    uint256 internal balance;
    function deposit(uint256 amount) external { balance += amount; }
    function withdraw(uint256 amount) external { balance -= amount; }
}
""",
        encoding="utf-8",
    )
    contract = parse_solidity(source)[0]
    contribution = generate_cross_function_state_hypotheses(contract, _directional_semantic())

    hypotheses = contribution.hypotheses
    assert {h.target_function for h in hypotheses} == {"deposit", "withdraw"}
    assert {h.invariant_id for h in hypotheses} == {"INV-STATE-balance-OPPOSING"}
    assert contribution.invariants[0].confidence == 0.80
    assert all(h.related_functions for h in hypotheses)
    assert all(h.evidence_ids for h in hypotheses)


def test_cross_function_state_surface_ignores_same_direction_updates(tmp_path):
    source = tmp_path / "SameDirection.sol"
    source.write_text(
        """pragma solidity ^0.8.20;
contract SameDirection {
    uint256 internal total;
    function addA(uint256 amount) external { total += amount; }
    function addB(uint256 amount) external { total += amount; }
}
""",
        encoding="utf-8",
    )
    contract = parse_solidity(source)[0]
    semantic = (
        SemanticRelationshipEvidence(
            contract="SameDirection",
            function="addA",
            relation="transition_expression",
            target="total",
            confidence=0.98,
            source="solc-json-ast:test",
            metadata={"operator": "+="},
        ),
        SemanticRelationshipEvidence(
            contract="SameDirection",
            function="addB",
            relation="transition_expression",
            target="total",
            confidence=0.98,
            source="solc-json-ast:test",
            metadata={"operator": "+="},
        ),
    )

    contribution = generate_cross_function_state_hypotheses(contract, semantic)
    assert not contribution.hypotheses
    assert not contribution.invariants


def test_cross_function_state_surface_reaches_structured_sequence_planner(tmp_path):
    source = tmp_path / "StateSurface.sol"
    source.write_text(
        """pragma solidity ^0.8.20;
contract StateSurface {
    uint256 internal balance;
    function deposit(uint256 amount) external { balance += amount; }
    function withdraw(uint256 amount) external { balance -= amount; }
}
""",
        encoding="utf-8",
    )
    contract = parse_solidity(source)[0]
    result = investigate(
        source,
        reasoning_surfaces=(lambda c, semantic=(): generate_cross_function_state_hypotheses(c, _directional_semantic()),),
        experiment_planner=plan_cross_function_state_experiment,
    )
    experiments = {e.hypothesis_id: e for e in result.experiments if e.hypothesis_id.startswith("H-STATE-")}
    assert set(experiments) == {"H-STATE-balance-deposit", "H-STATE-balance-withdraw"}
    assert tuple(step.function for step in experiments["H-STATE-balance-deposit"].steps) == ("withdraw", "deposit")
    assert tuple(step.function for step in experiments["H-STATE-balance-withdraw"].steps) == ("deposit", "withdraw")
