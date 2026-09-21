from pathlib import Path

from cydra.models import ContractModel, FunctionModel
from cydra.structural_intent_parity import generate_intent_parity_hypotheses


def _contract(tmp_path: Path, source: str, modifier: str) -> ContractModel:
    path = tmp_path / "Target.sol"
    path.write_text(source, encoding="utf-8")
    return ContractModel(
        name="Target",
        source=str(path),
        functions=(
            FunctionModel(
                name="setValue",
                visibility="external",
                modifiers=(modifier,),
                writes=("value",),
                external_calls=(),
                line=4,
            ),
        ),
    )


def test_role_intent_parity_is_not_hardcoded_to_executor_or_avm(tmp_path):
    contract = _contract(
        tmp_path,
        """contract Target {
    uint256 public value;
    // The guardian or operator may update the value.
    function setValue(uint256 next) external onlyKeeper {
        value = next;
    }
}
""",
        "onlyKeeper",
    )

    invariants, hypotheses = generate_intent_parity_hypotheses(contract)

    assert len(invariants) == 1
    assert len(hypotheses) == 1
    assert hypotheses[0].target_function == "setValue"
    assert "guardian" in hypotheses[0].claim
    assert "operator" in hypotheses[0].claim


def test_role_intent_parity_accepts_modifier_covering_documented_roles(tmp_path):
    contract = _contract(
        tmp_path,
        """contract Target {
    uint256 public value;
    // The guardian or operator may update the value.
    function setValue(uint256 next) external onlyGuardianOrOperator {
        value = next;
    }
}
""",
        "onlyGuardianOrOperator",
    )

    invariants, hypotheses = generate_intent_parity_hypotheses(contract)

    assert invariants == ()
    assert hypotheses == ()
