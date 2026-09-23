from cydra.ast_dataflow import SemanticRelationshipEvidence
from cydra.models import ContractModel, Experiment, FunctionModel
from cydra.pipeline import investigate
from cydra.solidity_model import parse_solidity
from cydra.state_experiments import plan_cross_function_state_experiment
from cydra.structural_state import generate_cross_function_state_hypotheses


def test_cross_function_state_surface_generates_candidates_from_shared_state(tmp_path):
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

    def planner(hypothesis):
        return Experiment(
            f"X-{hypothesis.hypothesis_id}",
            hypothesis.hypothesis_id,
            hypothesis.invariant_id,
            hypothesis.target_function,
            hypothesis.claim,
        )

    result = investigate(
        source,
        reasoning_surfaces=(generate_cross_function_state_hypotheses,),
        experiment_planner=planner,
    )
    hypotheses = [h for h in result.hypotheses if h.hypothesis_id.startswith("H-STATE-")]

    assert {h.target_function for h in hypotheses} == {"deposit", "withdraw"}
    assert {h.invariant_id for h in hypotheses} == {"INV-STATE-balance"}
    assert all(h.status == "proposed" for h in hypotheses)
    assert all(h.related_functions for h in hypotheses)
    assert any(i.invariant_id == "INV-STATE-balance" for i in result.invariants)


def test_cross_function_state_surface_uses_compiler_linked_write_evidence(tmp_path):
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

    semantic = (
        SemanticRelationshipEvidence(
            contract="StateSurface",
            function="deposit",
            relation="writes",
            target="balance",
            confidence=0.98,
            source="solc-json-ast:test",
        ),
        SemanticRelationshipEvidence(
            contract="StateSurface",
            function="withdraw",
            relation="transition_expression",
            target="balance",
            confidence=0.98,
            source="solc-json-ast:test",
        ),
    )
    contract = parse_solidity(source)[0]
    contribution = generate_cross_function_state_hypotheses(contract, semantic)

    assert len(contribution.hypotheses) == 2
    assert contribution.hypotheses[0].invariant_id == "INV-STATE-balance"
    assert contribution.invariants[0].confidence == 0.75


def test_cross_function_state_surface_has_no_candidate_when_state_is_not_shared(tmp_path):
    source = tmp_path / "Negative.sol"
    source.write_text(
        """pragma solidity ^0.8.20;
contract Negative {
    uint256 internal deposits;
    uint256 internal withdrawals;
    function deposit(uint256 amount) external { deposits += amount; }
    function withdraw(uint256 amount) external { withdrawals += amount; }
}
""",
        encoding="utf-8",
    )

    result = investigate(source, reasoning_surfaces=(generate_cross_function_state_hypotheses,))

    assert not any(h.hypothesis_id.startswith("H-STATE-") for h in result.hypotheses)


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
    result = investigate(
        source,
        reasoning_surfaces=(generate_cross_function_state_hypotheses,),
        experiment_planner=plan_cross_function_state_experiment,
    )
    experiments = {e.hypothesis_id: e for e in result.experiments if e.hypothesis_id.startswith("H-STATE-")}
    assert set(experiments) == {"H-STATE-balance-deposit", "H-STATE-balance-withdraw"}
    assert tuple(step.function for step in experiments["H-STATE-balance-deposit"].steps) == ("withdraw", "deposit")
    assert tuple(step.function for step in experiments["H-STATE-balance-withdraw"].steps) == ("deposit", "withdraw")


def test_state_surface_retains_modifier_protected_entries_with_authorized_capability():
    contract = ContractModel(
        name="Target",
        source="Target.sol",
        functions=(
            FunctionModel("open", "external", (), ("shared",), (), 1),
            FunctionModel("admin", "external", ("onlyOwner",), ("shared",), (), 2),
            FunctionModel("peer", "external", (), ("shared",), (), 3),
        ),
    )
    result = generate_cross_function_state_hypotheses(contract)
    assert {h.target_function for h in result.hypotheses} == {"open", "admin", "peer"}
    assert next(h for h in result.hypotheses if h.target_function == "admin").attacker_capability == "authorized caller satisfying the modeled guards"


def test_compiler_backed_reader_writer_topology_generates_state_surface(tmp_path):
    source = tmp_path / "Target.sol"
    source.write_text("""
    pragma solidity ^0.8.20;
    contract Target {
        uint256 public value;
        function seed(uint256 next) external { value = next; }
        function consume() external view returns (uint256) { return value; }
    }
    """, encoding="utf-8")
    contract = parse_solidity(source)[0]
    semantic = (
        SemanticRelationshipEvidence("Target", "seed", "writes", "value", 0.98, "test"),
        SemanticRelationshipEvidence("Target", "consume", "reads", "value", 0.90, "test"),
    )
    result = generate_cross_function_state_hypotheses(contract, semantic)
    assert {h.target_function for h in result.hypotheses} == {"seed", "consume"}
    assert all(h.invariant_id == "INV-STATE-value" for h in result.hypotheses)


def test_cross_function_state_surface_does_not_reintroduce_modifier_protected_semantic_writers():
    contract = ContractModel(
        name="Target",
        source="Target.sol",
        functions=(
            FunctionModel("open", "external", (), ("shared",), (), 1),
            FunctionModel("admin", "external", ("onlyOwner",), ("shared",), (), 2),
            FunctionModel("peer", "external", (), ("shared",), (), 3),
        ),
    )
    semantic = (
        SemanticRelationshipEvidence(
            contract="Target",
            function="admin",
            relation="writes",
            target="shared",
            confidence=0.98,
            source="solc-json-ast:test",
        ),
    )
    result = generate_cross_function_state_hypotheses(contract, semantic)
    assert {h.target_function for h in result.hypotheses} == {"open", "admin", "peer"}
