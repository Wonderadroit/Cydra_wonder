from pathlib import Path

from cydra.pipeline import investigate


def test_weighted_average_rounding_surface_discovers_internal_library_function(tmp_path: Path):
    source = tmp_path / "MathUtils.sol"
    source.write_text(
        """
        pragma solidity ^0.7.6;
        library ExampleMath {
            function weightedAverage(uint256 valueA, uint256 weightA, uint256 valueB, uint256 weightB)
                internal pure returns (uint256)
            {
                return valueA.mul(weightA).add(valueB.mul(weightB)).div(weightA.add(weightB));
            }
        }
        """,
        encoding="utf-8",
    )
    result = investigate(source)
    hypotheses = [h for h in result.hypotheses if h.invariant_id == "INV-ROUND-001"]
    assert len(hypotheses) == 1
    assert hypotheses[0].target_function == "weightedAverage"
    experiment = next(e for e in result.experiments if e.hypothesis_id == hypotheses[0].hypothesis_id)
    assert experiment.planned_inputs == ("100", "2", "99", "1")
