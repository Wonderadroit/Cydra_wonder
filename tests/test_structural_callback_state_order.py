from pathlib import Path

from cydra.pipeline import investigate


def test_callback_state_order_surface_detects_external_transfer_then_write(tmp_path: Path):
    source = tmp_path / "Callback.sol"
    source.write_text(
        """
        pragma solidity ^0.8.20;
        contract Callback {
            mapping(address => uint256) public lastTrade;
            function trade() external payable {
                _trade();
            }
            function _trade() internal {
                payable(msg.sender).transfer(msg.value);
                lastTrade[msg.sender] = block.timestamp;
            }
        }
        """,
        encoding="utf-8",
    )
    result = investigate(source)
    hypothesis = next(item for item in result.hypotheses if item.hypothesis_id == "H-CALLBACK-STATE-ORDER-trade")
    assert hypothesis.invariant_id == "INV-CALLBACK-STATE-ORDER-trade"
    experiment = next(item for item in result.experiments if item.hypothesis_id == hypothesis.hypothesis_id)
    assert "reenters" in experiment.action



def test_callback_state_order_surface_detects_ordinary_external_call_then_write(tmp_path: Path):
    source = tmp_path / "OrdinaryCall.sol"
    source.write_text(
        """
        pragma solidity ^0.8.20;
        interface IHook {
            function beforeAction() external;
        }
        contract OrdinaryCall {
            IHook public hook;
            uint256 public settled;

            function execute() external {
                hook.beforeAction();
                settled = 1;
            }
        }
        """,
        encoding="utf-8",
    )
    result = investigate(source)
    hypothesis = next(
        item for item in result.hypotheses
        if item.hypothesis_id == "H-CALLBACK-STATE-ORDER-execute"
    )
    assert hypothesis.invariant_id == "INV-CALLBACK-STATE-ORDER-execute"


def test_callback_state_order_surface_respects_reentrancy_guard(tmp_path: Path):
    source = tmp_path / "GuardedCall.sol"
    source.write_text(
        """
        pragma solidity ^0.8.20;
        interface IHook {
            function beforeAction() external;
        }
        contract GuardedCall {
            IHook public hook;
            uint256 public settled;

            modifier nonReentrant() {
                _;
            }

            function execute() external nonReentrant {
                hook.beforeAction();
                settled = 1;
            }
        }
        """,
        encoding="utf-8",
    )
    result = investigate(source)
    assert not any(
        item.hypothesis_id == "H-CALLBACK-STATE-ORDER-execute"
        for item in result.hypotheses
    )
