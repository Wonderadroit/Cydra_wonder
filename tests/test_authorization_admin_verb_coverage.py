from cydra.reasoning import generate_access_control_hypotheses
from cydra.solidity_model import parse_solidity


def _parse(tmp_path, body):
    source = tmp_path / "Target.sol"
    source.write_text(body, encoding="utf-8")
    return parse_solidity(source)[0]


def test_register_and_change_verbs_generate_authorization_candidates(tmp_path):
    contract = _parse(
        tmp_path,
        """pragma solidity ^0.8.20;
contract Target {
    bool policyEnabled;
    address feeRecipient;
    mapping(bytes32 => address) remoteGateways;
    function setPolicy(bool enabled) external onlyOwner { policyEnabled = enabled; }
    function changeFeeRecipient(address next) external { feeRecipient = next; }
    function registerRemoteGateway(bytes32 chain, address gateway) external {
        remoteGateways[chain] = gateway;
    }
}
""",
    )

    hypotheses = generate_access_control_hypotheses(contract)
    assert [item.target_function for item in hypotheses] == [
        "changeFeeRecipient",
        "registerRemoteGateway",
    ]


def test_self_scoped_registration_is_not_an_authorization_candidate(tmp_path):
    contract = _parse(
        tmp_path,
        """pragma solidity ^0.8.20;
contract Target {
    bool policyEnabled;
    mapping(address => bool) registered;
    function setPolicy(bool enabled) external onlyOwner { policyEnabled = enabled; }
    function registerAccount() external { registered[msg.sender] = true; }
}
""",
    )

    assert generate_access_control_hypotheses(contract) == ()


def test_owner_gated_registration_is_not_an_authorization_candidate(tmp_path):
    contract = _parse(
        tmp_path,
        """pragma solidity ^0.8.20;
contract Target {
    bool policyEnabled;
    mapping(bytes32 => address) remoteGateways;
    function setPolicy(bool enabled) external onlyOwner { policyEnabled = enabled; }
    function registerRemoteGateway(bytes32 chain, address gateway) external onlyOwner {
        remoteGateways[chain] = gateway;
    }
}
""",
    )

    assert generate_access_control_hypotheses(contract) == ()


def test_compiler_backed_internal_helper_write_keeps_admin_candidate_visible(tmp_path):
    from cydra.ast_dataflow import SemanticRelationshipEvidence

    contract = _parse(
        tmp_path,
        """pragma solidity ^0.8.20;
contract Target {
    bool policyEnabled;
    address feeRecipient;
    function setPolicy(bool enabled) external onlyOwner { policyEnabled = enabled; }
    function changeFeeRecipient(address next) external { _changeFeeRecipient(next); }
    function _changeFeeRecipient(address next) internal { feeRecipient = next; }
}
""",
    )
    semantic = (
        SemanticRelationshipEvidence(
            contract="Target",
            function="changeFeeRecipient",
            relation="writes",
            target="feeRecipient",
            confidence=1.0,
            source="test:internal-call-write",
        ),
    )

    # The source-only model does not propagate the internal helper's write.
    assert generate_access_control_hypotheses(contract) == ()
    # Compiler-backed effect evidence restores the candidate without weakening the finding gate.
    hypotheses = generate_access_control_hypotheses(contract, semantic)
    assert [item.target_function for item in hypotheses] == ["changeFeeRecipient"]
