from pathlib import Path

from cydra.ast_dataflow import SemanticRelationshipEvidence
from cydra.pipeline import investigate


def test_compiler_coverage_does_not_disable_lexical_auth_reasoning(tmp_path: Path):
    source = tmp_path / "Target.sol"
    source.write_text(
        """pragma solidity ^0.8.20;
contract Target {
    uint256 public value;
    function setValue(uint256 amount) external { value = amount; }
}
""",
        encoding="utf-8",
    )
    semantic = (
        SemanticRelationshipEvidence(
            contract="Target",
            function="setValue",
            relation="writes",
            target="value",
            confidence=0.98,
            source="solc-json-ast:contracts/Target.sol",
        ),
    )

    result = investigate(source, semantic_evidence=semantic)

    assert any(
        hypothesis.hypothesis_id == "H-AUTH-setValue"
        for hypothesis in result.hypotheses
    )
    experiment = next(
        experiment for experiment in result.experiments
        if experiment.hypothesis_id == "H-AUTH-setValue"
    )
    assert experiment.planned_inputs == ("1",)
