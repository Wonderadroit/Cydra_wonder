from cydra.solidity_model import parse_solidity
from cydra.structural_authorization import generate_structural_access_control_hypotheses


def _parse(tmp_path, body):
    source = tmp_path / "Target.sol"
    source.write_text(body, encoding="utf-8")
    return parse_solidity(source)[0]


def test_renamed_unprotected_writer_is_found_from_shared_protected_state(tmp_path):
    contract = _parse(
        tmp_path,
        """pragma solidity ^0.8.20;
contract Target {
    bool globalConfig;
    function guardedLifecycle() external onlyGuardian { globalConfig = true; }
    function configure(bool value) external { globalConfig = value; }
}
""",
    )
    hypotheses = generate_structural_access_control_hypotheses(contract)
    assert [item.target_function for item in hypotheses] == ["configure"]


def test_unrelated_unprotected_writer_is_not_flagged(tmp_path):
    contract = _parse(
        tmp_path,
        """pragma solidity ^0.8.20;
contract Target {
    bool globalConfig;
    uint256 userValue;
    function guardedLifecycle() external onlyGuardian { globalConfig = true; }
    function setUserValue(uint256 value) external { userValue = value; }
}
""",
    )
    assert generate_structural_access_control_hypotheses(contract) == ()


def test_read_only_function_is_not_flagged_even_when_model_marks_state_related_expression(tmp_path):
    contract = _parse(
        tmp_path,
        """pragma solidity ^0.8.20;
contract Target {
    bool globalConfig;
    function guardedLifecycle() external onlyGuardian { globalConfig = true; }
    function currentConfig() external view returns (bool) { return globalConfig; }
}
""",
    )
    assert generate_structural_access_control_hypotheses(contract) == ()


def test_comment_only_state_write_does_not_create_protected_or_candidate_state(tmp_path):
    contract = _parse(
        tmp_path,
        """pragma solidity ^0.8.20;
contract Target {
    bool globalConfig;
    function guardedLifecycle() external onlyGuardian {
        // globalConfig = true;
    }
    function configure(bool value) external {
        // globalConfig = value;
    }
}
""",
    )
    assert generate_structural_access_control_hypotheses(contract) == ()


def test_nested_mapping_and_struct_member_mutation_is_recognized(tmp_path):
    contract = _parse(
        tmp_path,
        """pragma solidity ^0.8.20;
contract Target {
    struct Config { bool enabled; }
    mapping(address => Config) configs;
    function guardedLifecycle(address account) external onlyGuardian { configs[account].enabled = true; }
    function configure(address account, bool value) external { configs[account].enabled = value; }
}
""",
    )
    hypotheses = generate_structural_access_control_hypotheses(contract)
    assert [item.target_function for item in hypotheses] == ["configure"]
