from pathlib import Path

from cydra.pipeline import default_reasoning_surfaces, investigate
from cydra.structural_callback_state_order import generate_callback_state_order_hypotheses
from cydra.structural_unbounded_iteration import generate_unbounded_iteration_hypotheses


def test_unbounded_iteration_hypotheses_reach_investigation_result(tmp_path: Path):
    source = tmp_path / "Target.sol"
    source.write_text(
        """
        pragma solidity ^0.8.20;
        contract Target {
            address[] public queue;
            function enqueue(address item) external { queue.push(item); }
            function process() external {
                for (uint256 i = 0; i < queue.length; i++) { queue[i]; }
            }
        }
        """,
        encoding="utf-8",
    )

    result = investigate(source)

    matches = [
        hypothesis
        for hypothesis in result.hypotheses
        if hypothesis.invariant_id == "INV-UNBOUNDED-ITERATION-Target"
    ]
    assert any(hypothesis.target_function == "process" for hypothesis in matches)
    assert any(
        experiment.hypothesis_id == hypothesis.hypothesis_id
        for hypothesis in matches
        for experiment in result.experiments
    )


def test_default_reasoning_surfaces_keep_newer_live_capabilities_enabled():
    surfaces = default_reasoning_surfaces()
    assert generate_callback_state_order_hypotheses in surfaces
    assert generate_unbounded_iteration_hypotheses in surfaces
