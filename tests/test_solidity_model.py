from pathlib import Path

from cydra.solidity_model import parse_solidity


def test_enrichment_is_additive_and_extracts_constructor_parameters_and_auth(tmp_path: Path) -> None:
    source = """
    contract Sample {
        constructor(address _owner, uint256 _limit) {}

        function initialize(address token0, address token1, bool stable) external {
            if (msg.sender != _owner) revert NotOwner();
            value = token0;
            other = 1;
        }
    }
    """
    path = tmp_path / "Sample.sol"
    path.write_text(source, encoding="utf-8")

    contract = parse_solidity(path)[0]
    function = contract.functions[0]

    assert contract.name == "Sample"
    assert contract.constructor is not None
    assert [(p.name, p.type, p.data_location) for p in contract.constructor.parameters] == [
        ("_owner", "address", None),
        ("_limit", "uint256", None),
    ]
    assert [(p.name, p.type, p.data_location) for p in function.parameters] == [
        ("token0", "address", None),
        ("token1", "address", None),
        ("stable", "bool", None),
    ]
    assert function.authorization_predicates == ("msg.sender != _owner",)

    # Existing fields remain populated exactly as before; enrichment is additive.
    assert function.name == "initialize"
    assert function.visibility == "external"
    assert function.modifiers == ()
    assert function.writes == ("other", "value")
    assert function.external_calls == ()
    assert function.line == 5


def test_parameter_locations_and_custom_types_are_preserved(tmp_path: Path) -> None:
    source = """
    contract Sample {
        constructor(address _voter, address _ve, address _registry) {}

        function initialize(AirdropParams memory params) external {
            require(msg.sender != team, "NotTeam");
        }

        function setTokens(address[] calldata tokens, address _minter) external {
            if (_msgSender() != _minter) revert NotMinter();
        }
    }
    """
    path = tmp_path / "Sample.sol"
    path.write_text(source, encoding="utf-8")

    contract = parse_solidity(path)[0]
    initialize = contract.functions[0]
    set_tokens = contract.functions[1]

    assert [(p.name, p.type, p.data_location) for p in contract.constructor.parameters] == [
        ("_voter", "address", None),
        ("_ve", "address", None),
        ("_registry", "address", None),
    ]
    assert [(p.name, p.type, p.data_location) for p in initialize.parameters] == [
        ("params", "AirdropParams", "memory"),
    ]
    assert initialize.authorization_predicates == ("msg.sender != team",)
    assert [(p.name, p.type, p.data_location) for p in set_tokens.parameters] == [
        ("tokens", "address[]", "calldata"),
        ("_minter", "address", None),
    ]
    assert set_tokens.authorization_predicates == ("_msgSender() != _minter",)

# Keep the focused extraction assertions adjacent to the additive regression gate.
