from pathlib import Path

from cydra.models import ContractModel, FunctionModel
from cydra.structural_transfer_accounting import generate_transfer_accounting_hypotheses


def test_safe_transfer_from_wrapper_is_a_transfer_accounting_boundary(tmp_path: Path):
    source = tmp_path / "StakingToken.sol"
    source.write_text(
        """
        contract StakingToken {
            uint256 public balance;
            uint256 public availableRewards;

            function deposit(uint256 amount) external {
                balance = balance + amount;
                availableRewards = availableRewards + amount;
                SafeTransferLib.safeTransferFrom(stakingToken, msg.sender, address(this), amount);
            }
        }
        """,
        encoding="utf-8",
    )
    model = ContractModel(
        "StakingToken",
        str(source),
        (
            FunctionModel(
                "deposit",
                "external",
                (),
                ("availableRewards", "balance"),
                ("SafeTransferLib.safeTransferFrom",),
                5,
                (),
            ),
        ),
        state_variables=("balance", "availableRewards"),
    )

    result = generate_transfer_accounting_hypotheses(model)

    assert len(result.hypotheses) == 1
    assert result.hypotheses[0].target_function == "deposit"
    assert result.hypotheses[0].invariant_id == "INV-TRANSFER-ACCOUNTING-deposit"
