from pathlib import Path

from cydra.interface_resolver import ResolvedInterface
from cydra.solidity_model import parse_solidity


def test_enrichment_is_additive_and_extracts_constructor_parameters_and_auth(tmp_path: Path) -> None:
    source = """
    contract Sample { uint256 value; uint256 other;

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
    assert contract.constructor.interface_casts == ()
    assert contract.constructor.resolved_interface_casts == ()
    assert contract.constructor.derived_interface_casts == ()
    assert contract.state_variables == ("value", "other")
    assert [(p.name, p.type, p.data_location) for p in function.parameters] == [
        ("token0", "address", None),
        ("token1", "address", None),
        ("stable", "bool", None),
    ]
    assert function.authorization_predicates == ("msg.sender != _owner",)
    assert function.state_predicates == ()

    # Existing fields remain populated exactly as before; enrichment is additive.
    assert function.name == "initialize"
    assert function.visibility == "external"
    assert function.modifiers == ()
    assert function.writes == ("other", "value")
    assert function.external_calls == ()
    assert function.line == 6


def test_constructor_interface_cast_relative_import_is_resolved(tmp_path: Path) -> None:
    (tmp_path / "interfaces").mkdir()
    (tmp_path / "interfaces" / "IVotingEscrow.sol").write_text(
        "interface IVotingEscrow {\n"
        "    function token() external view returns (address);\n"
        "    function tokenId() external view returns (uint256);\n"
        "}\n",
        encoding="utf-8",
    )
    path = tmp_path / "Sample.sol"
    path.write_text(
        "import {IVotingEscrow} from \"./interfaces/IVotingEscrow.sol\";\n"
        "contract Sample {\n"
        "    constructor(address _ve) { IVotingEscrow(_ve).token(); }\n"
        "}\n",
        encoding="utf-8",
    )

    contract = parse_solidity(path)[0]
    assert contract.constructor is not None
    assert contract.constructor.interface_casts == (("_ve", "IVotingEscrow"),)
    resolved = contract.constructor.resolved_interface_casts[0][1]

    assert isinstance(resolved, ResolvedInterface)
    assert resolved.name == "IVotingEscrow"
    assert resolved.source_path == "interfaces/IVotingEscrow.sol"
    assert resolved.resolution_method == "relative_import"
    assert [(m.name, m.parameters, m.returns) for m in resolved.methods] == [
        ("token", (), ("address",)),
        ("tokenId", (), ("uint256",)),
    ]


def test_constructor_interface_cast_remapping_is_resolved(tmp_path: Path) -> None:
    (tmp_path / "lib" / "openzeppelin" / "contracts" / "token" / "ERC20").mkdir(parents=True)
    (tmp_path / "remappings.txt").write_text(
        "@openzeppelin/contracts/=lib/openzeppelin/contracts/\n",
        encoding="utf-8",
    )
    (tmp_path / "lib" / "openzeppelin" / "contracts" / "token" / "ERC20" / "IERC20.sol").write_text(
        "interface IERC20 {\n"
        "    function totalSupply() external view returns (uint256);\n"
        "    function balanceOf(address account) external view returns (uint256);\n"
        "}\n",
        encoding="utf-8",
    )
    path = tmp_path / "Pool.sol"
    path.write_text(
        "import {IERC20} from \"@openzeppelin/contracts/token/ERC20/IERC20.sol\";\n"
        "contract Pool {\n"
        "    constructor(address _token) { IERC20(_token).totalSupply(); }\n"
        "}\n",
        encoding="utf-8",
    )

    contract = parse_solidity(path)[0]
    assert contract.constructor is not None
    assert contract.constructor.interface_casts == (("_token", "IERC20"),)
    resolved = contract.constructor.resolved_interface_casts[0][1]

    assert isinstance(resolved, ResolvedInterface)
    assert resolved.name == "IERC20"
    assert resolved.source_path == "lib/openzeppelin/contracts/token/ERC20/IERC20.sol"
    assert resolved.resolution_method == "remapping"
    assert [(m.name, m.parameters, m.returns) for m in resolved.methods] == [
        ("totalSupply", (), ("uint256",)),
        ("balanceOf", ("address account",), ("uint256",)),
    ]


def test_constructor_interface_casts_are_deduplicated_and_filtered_to_parameters(tmp_path: Path) -> None:
    (tmp_path / "interfaces").mkdir()
    (tmp_path / "interfaces" / "IVotingEscrow.sol").write_text(
        "interface IVotingEscrow { function token() external view returns (address); }\n",
        encoding="utf-8",
    )
    (tmp_path / "interfaces" / "IOther.sol").write_text(
        "interface IOther { function value() external view returns (uint256); }\n",
        encoding="utf-8",
    )
    source = """
    import {IVotingEscrow} from "./interfaces/IVotingEscrow.sol";
    import {IOther} from "./interfaces/IOther.sol";
    contract Sample {
        constructor(address _ve, address _other) {
            IVotingEscrow(_ve).token();
            IVotingEscrow(_ve).token();
            IOther(_other).value();
            INotAParameter(other).value();
        }
    }
    """
    path = tmp_path / "Sample.sol"
    path.write_text(source, encoding="utf-8")

    contract = parse_solidity(path)[0]
    assert contract.constructor is not None
    assert contract.constructor.interface_casts == (
        ("_ve", "IVotingEscrow"),
        ("_other", "IOther"),
    )
    assert [name for name, _ in contract.constructor.resolved_interface_casts] == ["_ve", "_other"]
    assert [resolved.name for _, resolved in contract.constructor.resolved_interface_casts] == [
        "IVotingEscrow",
        "IOther",
    ]


def test_constructor_nested_cast_derives_and_resolves_target_interface(tmp_path: Path) -> None:
    (tmp_path / "interfaces").mkdir()
    (tmp_path / "interfaces" / "IVotingEscrow.sol").write_text(
        "interface IVotingEscrow {\n"
        "    function token() external view returns (address);\n"
        "}\n",
        encoding="utf-8",
    )
    (tmp_path / "interfaces" / "IAero.sol").write_text(
        "interface IAero {\n"
        "    function mint(address to, uint256 amount) external returns (bool);\n"
        "    function minter() external view returns (address);\n"
        "}\n",
        encoding="utf-8",
    )
    path = tmp_path / "Minter.sol"
    path.write_text(
        "import {IVotingEscrow} from \"./interfaces/IVotingEscrow.sol\";\n"
        "import {IAero} from \"./interfaces/IAero.sol\";\n"
        "contract Minter {\n"
        "    constructor(address _ve) {\n"
        "        IAero(IVotingEscrow(_ve).token());\n"
        "        IVotingEscrow(_ve);\n"
        "    }\n"
        "}\n",
        encoding="utf-8",
    )

    contract = parse_solidity(path)[0]
    assert contract.constructor is not None

    # The inner cast remains a constructor-argument dependency.
    assert contract.constructor.interface_casts == (("_ve", "IVotingEscrow"),)
    resolved_constructor = contract.constructor.resolved_interface_casts
    assert len(resolved_constructor) == 1
    assert resolved_constructor[0][0] == "_ve"
    assert resolved_constructor[0][1].name == "IVotingEscrow"

    # The outer cast is represented as a resolved derived relationship.
    derived = contract.constructor.derived_interface_casts
    assert len(derived) == 1
    source_interface, source_method, target = derived[0]
    assert (source_interface, source_method) == ("IVotingEscrow", "token")
    assert isinstance(target, ResolvedInterface)
    assert target.name == "IAero"
    assert target.source_path == "interfaces/IAero.sol"
    assert target.resolution_method == "relative_import"
    assert [(m.name, m.parameters, m.returns) for m in target.methods] == [
        ("mint", ("address to", "uint256 amount"), ("bool",)),
        ("minter", (), ("address",)),
    ]


def test_state_predicates_caller_only_regression(tmp_path: Path) -> None:
    path = tmp_path / "CallerOnly.sol"
    path.write_text(
        """
        contract CallerOnly {
            address public owner;
            function initialize() external {
                require(msg.sender == owner);
            }
        }
        """,
        encoding="utf-8",
    )

    contract = parse_solidity(path)[0]
    function = contract.functions[0]
    assert contract.state_variables == ("owner",)
    assert function.authorization_predicates == ("msg.sender == owner",)
    assert function.state_predicates == ()


def test_state_predicates_state_only_regression(tmp_path: Path) -> None:
    path = tmp_path / "StateOnly.sol"
    path.write_text(
        """
        contract StateOnly {
            address public factory;
            function initialize() external {
                require(factory == address(0));
                factory = msg.sender;
            }
        }
        """,
        encoding="utf-8",
    )

    contract = parse_solidity(path)[0]
    function = contract.functions[0]
    assert contract.state_variables == ("factory",)
    assert function.authorization_predicates == ()
    assert function.state_predicates == ("factory == address(0)",)


def test_state_predicates_neither_regression(tmp_path: Path) -> None:
    path = tmp_path / "Neither.sol"
    path.write_text(
        """
        contract Neither {
            address public owner;
            function initialize(address token) external {
                require(token != address(0));
                uint256 localValue = 1;
                localValue = 2;
            }
        }
        """,
        encoding="utf-8",
    )

    contract = parse_solidity(path)[0]
    function = contract.functions[0]
    assert contract.state_variables == ("owner",)
    assert function.authorization_predicates == ()
    assert function.state_predicates == ()


def test_state_predicates_both_regression(tmp_path: Path) -> None:
    path = tmp_path / "Both.sol"
    path.write_text(
        """
        contract Both {
            address public owner;
            address public factory;
            function initialize() external {
                require(msg.sender == owner);
                require(factory != address(0));
            }
        }
        """,
        encoding="utf-8",
    )

    contract = parse_solidity(path)[0]
    function = contract.functions[0]
    assert contract.state_variables == ("owner", "factory")
    assert function.authorization_predicates == ("msg.sender == owner",)
    assert function.state_predicates == ("factory != address(0)",)


def test_contract_inheritance_and_declared_types_are_extracted_without_usages(tmp_path: Path) -> None:
    path = tmp_path / "Sample.sol"
    path.write_text(
        """
        contract Base {}
        contract Other {}
        contract Sample is Base, Other(0x1234) {
            struct LocalStruct { uint256 value; }
            enum LocalEnum { A, B }
            type LocalValue is uint256;

            function initialize(LocalStruct memory value) external {
                LocalStruct memory localValue = value;
                uint256 other = 1;
                localValue.value = other;
            }
        }
        """,
        encoding="utf-8",
    )

    contracts = parse_solidity(path)
    sample = next(contract for contract in contracts if contract.name == "Sample")
    function = sample.functions[0]

    assert sample.inherits == ("Base", "Other")
    assert sample.declared_types == ("LocalStruct", "LocalEnum", "LocalValue")
    assert function.parameters[0].type == "LocalStruct"
    assert "LocalStruct" not in sample.inherits
    assert sample.inherited_resolved_interfaces == ()


def test_contract_inheritance_strips_sparse_base_constructor_arguments(tmp_path: Path) -> None:
    path = tmp_path / "Sample.sol"
    path.write_text(
        """
        contract Sample is A, B(1), C, D(address(0x1234)) {}
        contract A {}
        contract B {}
        contract C {}
        contract D {}
        """,
        encoding="utf-8",
    )

    sample = next(contract for contract in parse_solidity(path) if contract.name == "Sample")
    assert sample.inherits == ("A", "B", "C", "D")


def test_inherited_interface_resolved_types_are_preserved_in_contract_model(tmp_path: Path) -> None:
    (tmp_path / "interfaces").mkdir()
    (tmp_path / "interfaces" / "IMinter.sol").write_text(
        "interface IMinter {\n"
        "    struct AirdropParams { address[] wallets; }\n"
        "    enum Mode { A, B }\n"
        "    type Amount is uint256;\n"
        "}\n",
        encoding="utf-8",
    )
    path = tmp_path / "Minter.sol"
    path.write_text(
        "import {IMinter} from \"./interfaces/IMinter.sol\";\n"
        "contract Minter is IMinter {\n"
        "    function initialize(AirdropParams memory params) external {}\n"
        "}\n",
        encoding="utf-8",
    )

    minter = parse_solidity(path)[0]

    assert minter.inherits == ("IMinter",)
    assert minter.declared_types == ()
    assert len(minter.inherited_resolved_interfaces) == 1
    inherited = minter.inherited_resolved_interfaces[0]
    assert isinstance(inherited, ResolvedInterface)
    assert inherited.name == "IMinter"
    assert inherited.source_path == "interfaces/IMinter.sol"
    assert inherited.resolution_method == "relative_import"
    assert inherited.declared_types == ("AirdropParams", "Mode", "Amount")
