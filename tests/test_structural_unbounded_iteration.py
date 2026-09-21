from pathlib import Path

from cydra.models import ContractModel, FunctionModel
from cydra.structural_unbounded_iteration import generate_unbounded_iteration_hypotheses


def test_detects_caller_growable_storage_array_on_critical_path(tmp_path: Path):
    source = tmp_path / "Target.sol"
    source.write_text(
        """
        pragma solidity ^0.8.0;
        contract Target {
            mapping(address => address[]) public entered;
            function enter(address market) external { entered[msg.sender].push(market); }
            function check(address user) public view returns (bool) { return _check(user); }
            function _check(address user) internal view returns (bool) {
                address[] memory markets = entered[user];
                uint256 total;
                for (uint256 i = 0; i < markets.length; i++) { total += i; }
                return total > 100;
            }
        }
        """,
        encoding="utf-8",
    )
    functions = (
        FunctionModel("enter", "external", (), (), (), 5),
        FunctionModel("check", "public", (), (), (), 6),
        FunctionModel("_check", "internal", (), (), (), 7),
    )
    contract = ContractModel("Target", str(source), functions)
    result = generate_unbounded_iteration_hypotheses(contract)
    assert result.hypotheses
    assert result.hypotheses[0].target_function == "check"
    assert result.hypotheses[0].potential_impact == "HIGH"


def test_does_not_flag_fixed_array():
    source = Path("/tmp/cydra-fixed-array-test.sol")
    source.write_text(
        """
        pragma solidity ^0.8.0;
        contract Target {
            address[4] public fixedMarkets;
            function check() external view returns (bool) {
                uint256 total;
                for (uint256 i = 0; i < fixedMarkets.length; i++) { total += i; }
                return total > 100;
            }
        }
        """,
        encoding="utf-8",
    )
    functions = (FunctionModel("check", "external", (), (), (), 5),)
    contract = ContractModel("Target", str(source), functions)
    assert not generate_unbounded_iteration_hypotheses(contract).hypotheses
    source.unlink(missing_ok=True)
