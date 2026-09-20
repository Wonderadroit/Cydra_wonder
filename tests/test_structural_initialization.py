from cydra.solidity_model import parse_solidity
from cydra.structural_initialization import generate_structural_initialization_hypotheses


def _parse(tmp_path, body):
    source = tmp_path / "Target.sol"
    source.write_text(body, encoding="utf-8")
    return parse_solidity(source)[0]


def test_renamed_initializer_is_found_from_lifecycle_modifier(tmp_path):
    contract = _parse(
        tmp_path,
        """pragma solidity ^0.8.20;
contract Target {
    address owner;
    function bootstrap(address account) external initializer { owner = account; }
}
""",
    )
    hypotheses = generate_structural_initialization_hypotheses(contract)
    assert [item.target_function for item in hypotheses] == ["bootstrap"]


def test_non_initializer_function_is_not_flagged(tmp_path):
    contract = _parse(
        tmp_path,
        """pragma solidity ^0.8.20;
contract Target {
    address owner;
    function configure(address account) external { owner = account; }
}
""",
    )
    assert generate_structural_initialization_hypotheses(contract) == ()

def test_initialize_named_entrypoint_is_found_without_initializer_modifier(tmp_path):
    contract = _parse(
        tmp_path,
        """pragma solidity ^0.8.20;
contract Target {
    address owner;
    function initialise(address account) external { owner = account; }
}
""",
    )
    hypotheses = generate_structural_initialization_hypotheses(contract)
    assert [item.target_function for item in hypotheses] == ["initialise"]
    assert hypotheses[0].evidence_ids == ("E-LIFECYCLE-NAME-initialise",)
