from pathlib import Path

from cydra.ast_dataflow import SemanticRelationshipEvidence
from cydra.compiler_constraints import ConstraintEvidence
from cydra.pipeline import investigate


FIXTURE = Path(__file__).parents[1] / "benchmarks/alchemix_missing_access_control/Target.sol"


def test_compiler_coverage_does_not_suppress_independent_auth_reasoning():
    evidence = [
        SemanticRelationshipEvidence(
            contract="AlchemixAccessControlFixture",
            function="setWhitelist",
            relation="reads",
            target="whitelist",
            confidence=0.98,
            source="solc-json-ast:test",
        )
    ]

    result = investigate(FIXTURE, semantic_evidence=evidence)

    assert any(h.hypothesis_id == "H-AUTH-setWhitelist" for h in result.hypotheses)


def test_missing_compiler_effects_keep_existing_fallback():
    result = investigate(FIXTURE, semantic_evidence=[])

    assert any(h.hypothesis_id == "H-AUTH-setWhitelist" for h in result.hypotheses)


def test_partial_compiler_coverage_does_not_disable_uncovered_fallback():
    evidence = [
        SemanticRelationshipEvidence(
            contract="AlchemixAccessControlFixture",
            function="setGovernance",
            relation="writes",
            target="governance",
            confidence=0.98,
            source="solc-json-ast:test",
        )
    ]

    result = investigate(FIXTURE, semantic_evidence=evidence)

    assert any(h.hypothesis_id == "H-AUTH-setWhitelist" for h in result.hypotheses)


def test_compiler_constraint_reaches_canonical_experiment_vector():
    constraints = (
        ConstraintEvidence(
            contract="AlchemixAccessControlFixture",
            function="setWhitelist",
            parameter="account",
            parameter_index=0,
            predicate="account != address(0)",
            source="solc-json-ast:test",
        ),
    )

    result = investigate(FIXTURE, constraint_evidence=constraints)

    experiment = next(
        item for item in result.experiments if item.hypothesis_id == "H-AUTH-setWhitelist"
    )
    assert experiment.planned_inputs == ("address(0xCAFE)", "false")


def test_foreign_function_constraint_cannot_reach_target_experiment():
    constraints = (
        ConstraintEvidence(
            contract="AlchemixAccessControlFixture",
            function="setGovernance",
            parameter="next",
            parameter_index=0,
            predicate="next != address(0)",
            source="solc-json-ast:test",
        ),
    )

    result = investigate(FIXTURE, constraint_evidence=constraints)

    experiment = next(
        item for item in result.experiments if item.hypothesis_id == "H-AUTH-setWhitelist"
    )
    assert experiment.planned_inputs == ("address(0xCAFE)", "false")
