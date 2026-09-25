from pathlib import Path

from cydra.pipeline import investigate


def test_unbounded_iteration_hypotheses_survive_unified_pipeline(tmp_path: Path):
    source = tmp_path / "Target.sol"
    source.write_text(
        """
        pragma solidity ^0.8.20;
        contract Target {
            uint256[] public items;

            function add(uint256 value) external {
                items.push(value);
            }

            function process() external {
                for (uint256 i = 0; i < items.length; i++) {
                    uint256 value = items[i];
                    value;
                }
            }
        }
        """,
        encoding="utf-8",
    )

    result = investigate(source)

    assert any(
        item.invariant_id.startswith("INV-UNBOUNDED-ITERATION-")
        for item in result.hypotheses
    )
    assert any(
        item.hypothesis_id == "H-UNBOUNDED-ITERATION-process"
        for item in result.hypotheses
    )
    assert any(
        item.hypothesis_id == "H-UNBOUNDED-ITERATION-process"
        for item in result.experiments
    )
