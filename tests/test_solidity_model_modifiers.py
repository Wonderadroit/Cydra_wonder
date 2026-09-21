from cydra.solidity_model import parse_solidity


def test_parser_preserves_arbitrary_function_modifiers(tmp_path):
    source = tmp_path / "Target.sol"
    source.write_text(
        """pragma solidity ^0.8.0;
contract Target {
    uint256 public value;
    modifier onlyKeeper() { _; }
    modifier onlyGuardianOrOperator() { _; }

    // The guardian or operator may update the value.
    function setValue(uint256 next) external onlyKeeper {
        value = next;
    }

    function setOther(uint256 next) external onlyGuardianOrOperator returns (uint256) {
        value = next;
        return next;
    }
}
""",
        encoding="utf-8",
    )

    contracts = parse_solidity(source)
    functions = {f.name: f for f in contracts[0].functions}

    assert functions["setValue"].modifiers == ("onlyKeeper",)
    assert functions["setOther"].modifiers == ("onlyGuardianOrOperator",)
