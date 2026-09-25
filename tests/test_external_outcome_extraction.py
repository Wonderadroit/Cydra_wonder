from pathlib import Path

from cydra.models import ContractModel, FunctionModel
from cydra.structural_external_outcome import generate_external_outcome_hypotheses


def _contract(tmp_path: Path, source: str) -> ContractModel:
    path = tmp_path / "Target.sol"
    path.write_text(source, encoding="utf-8")
    return ContractModel(
        name="Target",
        source=str(path),
        functions=(
            FunctionModel(
                name="run",
                visibility="external",
                modifiers=(),
                writes=(),
                external_calls=(),
                line=2,
            ),
        ),
    )


def test_interface_call_is_not_treated_as_ignored_failure_result(tmp_path):
    contract = _contract(
        tmp_path,
        """
contract Target {
    function run() external {
        helper.performSideEffects();
        hook.afterTransact();
    }
}
""",
    )

    result = generate_external_outcome_hypotheses(contract)

    assert result.hypotheses == ()


def test_discarded_low_level_call_is_an_external_outcome_candidate(tmp_path):
    contract = _contract(
        tmp_path,
        """
contract Target {
    function run() external {
        recipient.call(abi.encode(1));
    }
}
""",
    )

    result = generate_external_outcome_hypotheses(contract)

    assert len(result.hypotheses) == 1
    assert result.hypotheses[0].target_function == "run"
