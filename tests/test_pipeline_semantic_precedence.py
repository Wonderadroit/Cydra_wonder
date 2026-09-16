from pathlib import Path

from cydra.ast_dataflow import SemanticRelationshipEvidence
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
