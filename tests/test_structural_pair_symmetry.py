from pathlib import Path

from cydra.solidity_model import parse_solidity
from cydra.structural_pair_symmetry import (
    generate_pair_symmetry_hypotheses,
    paired_subtraction_invariant,
)


def test_detects_reversed_operands_in_paired_outputs(tmp_path: Path):
    source = tmp_path / "Pair.sol"
    source.write_text(
        """
        contract Pair {
            function compute(uint256 a, uint256 b) external pure returns (uint256) {
                uint256 value0 = a - b;
                uint256 value1 = b - a;
                return value0 + value1;
            }
        }
        """
    )
    contract = parse_solidity(source)[0]
    invariant = paired_subtraction_invariant(contract)
    hypotheses = generate_pair_symmetry_hypotheses(contract)

    assert invariant is not None
    assert invariant.invariant_id == "INV-PAIR-SYMMETRY-001"
    assert [item.target_function for item in hypotheses] == ["compute"]
    assert hypotheses[0].hypothesis_id == "H-PAIR-SYMMETRY-compute-value"


def test_does_not_flag_same_order_paired_outputs(tmp_path: Path):
    source = tmp_path / "Pair.sol"
    source.write_text(
        """
        contract Pair {
            function compute(uint256 a, uint256 b) external pure returns (uint256) {
                uint256 value0 = a - b;
                uint256 value1 = a - b;
                return value0 + value1;
            }
        }
        """
    )
    contract = parse_solidity(source)[0]

    assert paired_subtraction_invariant(contract) is None
    assert generate_pair_symmetry_hypotheses(contract) == ()
