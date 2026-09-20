from cydra.models import ContractModel, FunctionModel, ParameterModel
from cydra.structural_transfer_accounting import generate_transfer_accounting_hypotheses


def test_transfer_accounting_recovers_inherited_state_shape(tmp_path):
    source = tmp_path / "InheritedTarget.sol"
    source.write_text(
        """
        contract InheritedTarget {
            function deposit(uint256 amount) external {
                uint256 newBalance = balance + amount;
                uint256 newAvailableRewards = availableRewards + amount;
                balance = newBalance;
                availableRewards = newAvailableRewards;
                SafeTransferLib.safeTransferFrom(stakingToken, msg.sender, address(this), amount);
            }
        }
        """,
        encoding="utf-8",
    )

    contract = ContractModel(
        name="InheritedTarget",
        source=str(source),
        state_variables=(),
        functions=(
            FunctionModel(
                name="deposit",
                visibility="external",
                modifiers=(),
                writes=(),
                external_calls=(),
                line=3,
                parameters=(ParameterModel(name="amount", type="uint256"),),
            ),
        ),
        inherits=("StakingBase",),
    )

    hypotheses = generate_transfer_accounting_hypotheses(contract).hypotheses

    assert len(hypotheses) == 1
    assert hypotheses[0].target_function == "deposit"
