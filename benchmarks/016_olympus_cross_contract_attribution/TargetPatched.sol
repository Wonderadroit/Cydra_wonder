// Extracted causal patch corresponding to the historical Olympus M-23 remediation:
// bound the measured balance delta to the caller-requested repayment.
pragma solidity ^0.8.20;

interface IRepayToken {
    function balanceOf(address account) external view returns (uint256);
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
}

contract OlympusTreasury {
    mapping(address => mapping(address => uint256)) public reserveDebt;
    mapping(address => uint256) public totalDebt;

    function repayLoan(IRepayToken token_, uint256 amount_) external {
        uint256 debt = reserveDebt[address(token_)][msg.sender];
        require(debt > 0, "no debt");

        uint256 prevBalance = token_.balanceOf(address(this));
        require(token_.transferFrom(msg.sender, address(this), amount_), "transfer");

        uint256 received = token_.balanceOf(address(this)) - prevBalance;
        if (received > amount_) received = amount_;
        reserveDebt[address(token_)][msg.sender] -= received;
        totalDebt[address(token_)] -= received;
    }

    function seedDebt(IRepayToken token_, address debtor, uint256 amount) external {
        reserveDebt[address(token_)][debtor] = amount;
        totalDebt[address(token_)] = amount;
    }

    function injectRevenue(IRepayToken token_, uint256 amount) external {
        MockHookToken(address(token_)).mint(address(this), amount);
    }
}

contract MockHookToken is IRepayToken {
    mapping(address => uint256) public balanceOf;
    address public hookTarget;
    uint256 public callbackAmount;

    constructor(uint256 initialBalance) {
        balanceOf[msg.sender] = initialBalance;
    }

    function configureHook(address target, uint256 amount) external {
        hookTarget = target;
        callbackAmount = amount;
    }

    function mint(address to, uint256 amount) external {
        balanceOf[to] += amount;
    }

    function transferFrom(address from, address to, uint256 amount) external returns (bool) {
        require(balanceOf[from] >= amount, "balance");
        if (hookTarget != address(0) && callbackAmount != 0) {
            OlympusTreasury(hookTarget).injectRevenue(IRepayToken(address(this)), callbackAmount);
        }
        balanceOf[from] -= amount;
        balanceOf[to] += amount;
        return true;
    }
}
