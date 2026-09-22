from pathlib import Path

from cydra.models import ContractModel, FunctionModel
from cydra.structural_aggregation_order import (
    aggregation_order_invariant,
    generate_aggregation_order_hypotheses,
)


def _contract(tmp_path: Path, source: str) -> ContractModel:
    path = tmp_path / "Target.sol"
    path.write_text(source, encoding="utf-8")
    return ContractModel(
        name="Target",
        source=str(path),
        functions=(FunctionModel("compute", "external", (), (), (), 1),),
    )


def test_detects_clamp_before_late_balance(tmp_path):
    contract = _contract(
        tmp_path,
        """
        contract Target {
            function compute() external {
                for (uint256 i = 0; i < 2; i++) {
                    exposure += uint256(Math.max(partial, 0));
                }
                if (!skipBalance) {
                    exposure += token.balanceOf(vault);
                }
            }
        }
        """,
    )

    invariant = aggregation_order_invariant(contract)
    hypotheses = generate_aggregation_order_hypotheses(contract)

    assert invariant is not None
    assert invariant.invariant_id == "INV-AGGREGATION-ORDER-001"
    assert len(hypotheses) == 1
    assert hypotheses[0].target_function == "compute"


def test_does_not_flag_final_clamp_without_late_balance(tmp_path):
    contract = _contract(
        tmp_path,
        """
        contract Target {
            function compute() external {
                for (uint256 i = 0; i < 2; i++) {
                    exposure += partial;
                }
                exposure = uint256(Math.max(exposure, 0));
            }
        }
        """,
    )

    assert aggregation_order_invariant(contract) is None
    assert generate_aggregation_order_hypotheses(contract) == ()
