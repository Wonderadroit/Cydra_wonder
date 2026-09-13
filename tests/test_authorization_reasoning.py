from pathlib import Path

from cydra.reasoning import generate_access_control_hypotheses
from cydra.solidity_model import parse_solidity


def _parse(tmp_path: Path, body: str):
    source = tmp_path / "Target.sol"
    source.write_text(
        "pragma solidity ^0.8.20;\n"
        "contract Target {\n"
        "    mapping(address => mapping(address => bool)) operatorApprovals;\n"
        "    mapping(address => bool) globalApprovals;\n"
        "    bool config;\n"
        "    function setConfig(bool value) external onlyGov { config = value; }\n"
        f"    {body}\n"
        "}\n",
        encoding="utf-8",
    )
    return parse_solidity(source)[0]


def test_self_scoped_msg_sender_mapping_is_not_admin_hypothesis(tmp_path):
    contract = _parse(
        tmp_path,
        "function setOperatorApproval(address operator, bool approved) external { operatorApprovals[msg.sender][operator] = approved; }",
    )
    hypotheses = generate_access_control_hypotheses(contract)
    assert hypotheses == ()


def test_self_scoped_msg_sender_mapping_does_not_hide_real_unprotected_admin(tmp_path):
    contract = _parse(
        tmp_path,
        "function setOperatorApproval(address operator, bool approved) external { operatorApprovals[msg.sender][operator] = approved; }\n"
        "function setGlobalApproval(address operator, bool approved) external { globalApprovals[operator] = approved; }",
    )
    hypotheses = generate_access_control_hypotheses(contract)
    assert [item.hypothesis_id for item in hypotheses] == ["H-AUTH-setGlobalApproval"]


def test_msg_sender_detection_is_not_triggered_by_caller_independent_mapping_key(tmp_path):
    contract = _parse(
        tmp_path,
        "function setGlobalApproval(address operator, bool approved) external { globalApprovals[operator] = approved; }",
    )
    hypotheses = generate_access_control_hypotheses(contract)
    assert [item.hypothesis_id for item in hypotheses] == ["H-AUTH-setGlobalApproval"]
