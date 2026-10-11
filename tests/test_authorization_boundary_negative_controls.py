from cydra.reasoning import generate_access_control_hypotheses
from cydra.solidity_model import parse_solidity
from cydra.structural_authorization import generate_structural_access_control_hypotheses


def _parse(tmp_path, source):
    path = tmp_path / "Target.sol"
    path.write_text(source, encoding="utf-8")
    return parse_solidity(path)[0]


def test_caller_funded_permissionless_payout_is_not_an_authorization_finding(tmp_path):
    contract = _parse(
        tmp_path,
        """pragma solidity ^0.8.20;
contract SplitterLike {
    address public feeRecipient;
    function changeFeeRecipient(address next) external onlyOwner {
        feeRecipient = next;
    }
    function payWhitehat(address recipient, uint256 amount) external nonReentrant {
        require(recipient != address(0));
        // Transfers are sourced from msg.sender, not from protocol custody.
    }
}
""",
    )

    payout = next(function for function in contract.functions if function.name == "payWhitehat")
    assert "nonReentrant" in payout.modifiers
    assert generate_access_control_hypotheses(contract) == ()
    assert generate_structural_access_control_hypotheses(contract) == ()


def test_owner_gated_gateway_registration_is_not_flagged_as_unguarded_writer(tmp_path):
    contract = _parse(
        tmp_path,
        """pragma solidity ^0.8.20;
contract GatewayLike {
    mapping(bytes => string) private chainNames;
    mapping(bytes => address) private remoteGateways;
    function registerChain(bytes calldata chain, string calldata name) external onlyOwner {
        chainNames[chain] = name;
    }
    function registerRemote(bytes calldata chain, address remote) external onlyOwner {
        remoteGateways[chain] = remote;
    }
    function sendMessage(bytes calldata payload) external payable {
        // Message submission is permissionless by design.
    }
}
""",
    )

    assert generate_access_control_hypotheses(contract) == ()
    assert generate_structural_access_control_hypotheses(contract) == ()


def test_unguarded_sibling_writer_still_generates_authorization_hypothesis(tmp_path):
    contract = _parse(
        tmp_path,
        """pragma solidity ^0.8.20;
contract Config {
    address public router;
    function setRouter(address next) external onlyOwner { router = next; }
    function replaceRouter(address next) external { router = next; }
}
""",
    )

    hypotheses = generate_structural_access_control_hypotheses(contract)
    assert [item.target_function for item in hypotheses] == ["replaceRouter"]
