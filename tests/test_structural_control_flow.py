from pathlib import Path

from cydra.solidity_model import parse_solidity
from cydra.structural_control_flow import generate_control_flow_hypotheses


def test_control_flow_surface_detects_continue_bypassing_progress(tmp_path: Path):
    source = tmp_path / "Target.sol"
    source.write_text(
        """pragma solidity ^0.8.20;
        contract Target {
            mapping(address => bool) public done;
            function process(address[] calldata users) external {
                for (uint256 i = 0; i < users.length; ) {
                    if (done[users[i]]) continue;
                    done[users[i]] = true;
                    unchecked { i++; }
                }
            }
        }""",
        encoding="utf-8",
    )
    contract = parse_solidity(source)[0]
    result = generate_control_flow_hypotheses(contract)
    assert len(result.hypotheses) == 1
    assert result.hypotheses[0].hypothesis_id == "H-CONTROL-FLOW-process"


def test_control_flow_surface_rejects_progress_before_continue(tmp_path: Path):
    source = tmp_path / "Target.sol"
    source.write_text(
        """pragma solidity ^0.8.20;
        contract Target {
            mapping(address => bool) public done;
            function process(address[] calldata users) external {
                for (uint256 i = 0; i < users.length; ) {
                    if (done[users[i]]) {
                        unchecked { i++; }
                        continue;
                    }
                    done[users[i]] = true;
                    unchecked { i++; }
                }
            }
        }""",
        encoding="utf-8",
    )
    contract = parse_solidity(source)[0]
    result = generate_control_flow_hypotheses(contract)
    assert not result.hypotheses


def test_control_flow_surface_rejects_loop_without_continue(tmp_path: Path):
    source = tmp_path / "Target.sol"
    source.write_text(
        """pragma solidity ^0.8.20;
        contract Target {
            function process(uint256[] calldata values) external {
                for (uint256 i = 0; i < values.length; ) {
                    values[i];
                    unchecked { i++; }
                }
            }
        }""",
        encoding="utf-8",
    )
    contract = parse_solidity(source)[0]
    result = generate_control_flow_hypotheses(contract)
    assert not result.hypotheses
