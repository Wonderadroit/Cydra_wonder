from pathlib import Path

from cydra.pipeline import investigate


def test_authorization_invariant_uses_observed_only_owner_modifier(tmp_path: Path):
    source = tmp_path / "Target.sol"
    source.write_text(
        "pragma solidity ^0.8.20;\n"
        "contract Target {\n"
        "    bool config;\n"
        "    mapping(address => bool) globalApprovals;\n"
        "    function setConfig(bool value) external onlyOwner { config = value; }\n"
        "    function setGlobalApproval(address operator, bool approved) external { globalApprovals[operator] = approved; }\n"
        "}\n",
        encoding="utf-8",
    )
    result = investigate(source)
    auth = next(item for item in result.invariants if item.invariant_id == "INV-AUTH-001")
    assert "onlyOwner" in auth.statement
    assert "onlyGov" not in auth.statement

# Regression remains intentionally source/model based; no target oracle is imported.
