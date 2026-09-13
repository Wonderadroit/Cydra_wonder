from cydra.models import ContractModel, FunctionModel
from cydra.reasoning import generate_access_control_hypotheses


def test_custom_modifier_is_not_misclassified_as_unprotected(tmp_path):
    source = tmp_path / "Target.sol"
    source.write_text(
        """pragma solidity ^0.8.20;
contract Target {
    function setProtected(uint256 value) external onlyLoanProtocol { value; }
    function setOpen(uint256 value) external { value; }
}
""",
        encoding="utf-8",
    )
    contract = ContractModel(
        name="Target",
        source=str(source),
        functions=(
            FunctionModel("setProtected", "external", (), (), (), 3),
            FunctionModel("setOpen", "external", (), (), (), 4),
        ),
    )

    hypotheses = generate_access_control_hypotheses(contract)

    assert [hypothesis.target_function for hypothesis in hypotheses] == ["setOpen"]


def test_custom_modifier_with_arguments_is_detected(tmp_path):
    source = tmp_path / "Target.sol"
    source.write_text(
        """pragma solidity ^0.8.20;
contract Target {
    function setProtected(uint256 value) external onlyRole(DEFAULT_ADMIN_ROLE) { value; }
    function setOpen(uint256 value) external { value; }
}
""",
        encoding="utf-8",
    )
    contract = ContractModel(
        name="Target",
        source=str(source),
        functions=(
            FunctionModel("setProtected", "external", (), (), (), 3),
            FunctionModel("setOpen", "external", (), (), (), 4),
        ),
    )

    hypotheses = generate_access_control_hypotheses(contract)

    assert [hypothesis.target_function for hypothesis in hypotheses] == ["setOpen"]
