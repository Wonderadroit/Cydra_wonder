// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.20;

contract IdempotencyToken {
    mapping(address => uint256) public balanceOf;

    constructor(address holder, uint256 amount) {
        balanceOf[holder] = amount;
    }

    function transfer(address to, uint256 amount) external returns (bool) {
        require(balanceOf[msg.sender] >= amount, "insufficient");
        balanceOf[msg.sender] -= amount;
        balanceOf[to] += amount;
        return true;
    }
}

contract IdempotencyTargetPatched {
    enum Decision { ON_HOLD, CANCEL }

    struct OnHoldTransfer {
        IdempotencyToken token;
        Decision decision;
        address from;
        uint256 amount;
    }

    IdempotencyToken public token;
    uint256 public amount;
    mapping(uint256 => OnHoldTransfer) public onHoldTransfers;

    constructor() {
        amount = 100;
        token = new IdempotencyToken(address(this), amount * 2);
        onHoldTransfers[0] = OnHoldTransfer(token, Decision.ON_HOLD, address(this), amount);
    }

    function cancelOnHoldTransfers(
        address trustedIntermediary,
        uint256[] calldata transfers,
        bool skipMinBoundaryUpdate
    ) external {
        trustedIntermediary;
        skipMinBoundaryUpdate;
        for (uint256 i = 0; i < transfers.length; i++) {
            OnHoldTransfer memory transferRecord = onHoldTransfers[transfers[i]];
            require(transferRecord.from == address(this), "UR07");
            require(
                transferRecord.decision == Decision.ON_HOLD,
                "already processed"
            );
            onHoldTransfers[transfers[i]].decision = Decision.CANCEL;
            require(transferRecord.token.transfer(msg.sender, transferRecord.amount), "UR08");
        }
    }
}
