from cydra.structural_transfer_accounting import _credits_requested_amount, _transfer_argument


def test_transfer_accounting_recovers_inherited_state_shape():
    body = """
        uint256 newBalance = balance + amount;
        uint256 newAvailableRewards = availableRewards + amount;
        balance = newBalance;
        availableRewards = newAvailableRewards;
        SafeTransferLib.safeTransferFrom(stakingToken, msg.sender, address(this), amount);
    """

    amount = _transfer_argument(body)

    assert amount == "amount"
    assert _credits_requested_amount(body, amount, ()) is True
