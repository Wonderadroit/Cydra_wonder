from cydra.solidity_model import parse_solidity
from cydra.structural_arithmetic import arithmetic_rounding_invariant, generate_arithmetic_hypotheses


def _parse(tmp_path, name, body):
    source = tmp_path / name
    source.write_text(body, encoding="utf-8")
    return parse_solidity(source)[0]


def test_arithmetic_detector_survives_function_and_constant_renaming(tmp_path):
    contract = _parse(
        tmp_path,
        "Renamed.sol",
        """pragma solidity ^0.8.20;
contract Renamed {
    function calculateShares(uint256 amount, uint256 divisor) external pure returns (uint256) {
        return (amount * 10 + 9) / divisor;
    }
}
""",
    )
    hypotheses = generate_arithmetic_hypotheses(contract)
    assert [item.target_function for item in hypotheses] == ["calculateShares"]
    assert arithmetic_rounding_invariant(contract) is not None


def test_arithmetic_detector_preserves_original_benchmark_shape(tmp_path):
    contract = _parse(
        tmp_path,
        "Target.sol",
        """pragma solidity ^0.8.20;
contract Target {
    uint256 internal constant SCALE = 1e18;
    function quoteMint(uint256 assets) external pure returns (uint256) {
        return (assets * SCALE + 996) / 997;
    }
}
""",
    )
    assert [item.target_function for item in generate_arithmetic_hypotheses(contract)] == ["quoteMint"]


def test_plain_floor_division_is_not_flagged(tmp_path):
    contract = _parse(
        tmp_path,
        "Safe.sol",
        """pragma solidity ^0.8.20;
contract Safe {
    function calculate(uint256 amount, uint256 divisor) external pure returns (uint256) {
        return amount / divisor;
    }
}
""",
    )
    assert generate_arithmetic_hypotheses(contract) == ()
    assert arithmetic_rounding_invariant(contract) is None


def test_comment_text_does_not_create_arithmetic_hypothesis(tmp_path):
    contract = _parse(
        tmp_path,
        "CommentOnly.sol",
        """pragma solidity ^0.8.20;
contract CommentOnly {
    // (amount + 99) / divisor is only documentation.
    function calculate(uint256 amount, uint256 divisor) external pure returns (uint256) {
        return amount / divisor;
    }
}
""",
    )
    assert generate_arithmetic_hypotheses(contract) == ()
