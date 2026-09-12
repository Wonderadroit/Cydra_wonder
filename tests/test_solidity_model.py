from pathlib import Path

from cydra.interface_resolver import ResolvedInterface
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
    assert contract.constructor.interface_casts == ()
    assert contract.constructor.resolved_interface_casts == ()
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
