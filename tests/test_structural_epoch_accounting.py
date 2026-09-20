from pathlib import Path

from cydra.pipeline import investigate
from cydra.epoch_accounting_planning import plan_epoch_accounting_experiment
from cydra.structural_epoch_accounting import generate_epoch_accounting_hypotheses


def test_epoch_boundary_surface_discovers_unaligned_segment_bug(tmp_path: Path):
    source = tmp_path / "Target.sol"
    source.write_text(
        """
pragma solidity ^0.8.20;
contract Target {
    uint256 public constant BLOCK_EPOCH = 100000;
    mapping(uint256 => uint256) public rate;
    function update(uint256 start, uint256 end) external {
        uint256 i = start;
        while (i < end) {
            uint256 epoch = (i / BLOCK_EPOCH) * BLOCK_EPOCH;
            uint256 nextEpoch = i + BLOCK_EPOCH;
            uint256 delta = Math.min(nextEpoch, end) - i;
            rate[epoch] += delta;
            i += delta;
        }
    }
}
library Math {
    function min(uint256 a, uint256 b) internal pure returns (uint256) { return a < b ? a : b; }
}
""",
        encoding="utf-8",
    )
    result = investigate(
        source,
        reasoning_surfaces=(generate_epoch_accounting_hypotheses,),
        experiment_planner=plan_epoch_accounting_experiment,
    )
    assert any(h.hypothesis_id == "H-EPOCH-ACCOUNTING-update" for h in result.hypotheses)
    experiment = next(e for e in result.experiments if e.hypothesis_id == "H-EPOCH-ACCOUNTING-update")
    assert "epoch boundary" in experiment.action
