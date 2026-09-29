from pathlib import Path

import pytest

from cydra.interface_resolver import resolve_interface, resolve_struct_fields


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_resolves_interface_through_remapping(tmp_path: Path) -> None:
    root = tmp_path / "target"
    _write(root / "remappings.txt", "@oz/=lib/openzeppelin/\n")
    _write(
        root / "contracts" / "Token.sol",
        'import "@oz/token/ERC20/IERC20.sol";\ncontract Token {}\n',
    )
    _write(
        root / "lib" / "openzeppelin" / "token" / "ERC20" / "IERC20.sol",
        "interface IERC20 {\n"
        "    function decimals() external view returns (uint8);\n"
        "    function symbol() external view returns (string memory);\n"
        "}\n",
    )

    resolved = resolve_interface(root, root / "contracts" / "Token.sol", "IERC20")

    assert resolved.name == "IERC20"
    assert resolved.source_path == "lib/openzeppelin/token/ERC20/IERC20.sol"
    assert resolved.resolution_method == "remapping"
    assert [method.name for method in resolved.methods] == ["decimals", "symbol"]
    assert resolved.declared_types == ()


def test_resolves_interface_through_relative_import(tmp_path: Path) -> None:
    root = tmp_path / "target"
    _write(
        root / "contracts" / "Pool.sol",
        'import "./interfaces/IVotingEscrow.sol";\ncontract Pool {}\n',
    )
    _write(
        root / "contracts" / "interfaces" / "IVotingEscrow.sol",
        "interface IVotingEscrow {\n"
        "    function token() external view returns (address);\n"
        "}\n",
    )

    resolved = resolve_interface(root, root / "contracts" / "Pool.sol", "IVotingEscrow")

    assert resolved.name == "IVotingEscrow"
    assert resolved.source_path == "contracts/interfaces/IVotingEscrow.sol"
    assert resolved.resolution_method == "relative_import"
    assert [method.name for method in resolved.methods] == ["token"]
    assert resolved.declared_types == ()


def test_unresolved_declared_import_raises_instead_of_searching(tmp_path: Path) -> None:
    root = tmp_path / "target"
    _write(
        root / "contracts" / "Pool.sol",
        'import {IVotingEscrow} from "./interfaces/IVotingEscrow.sol";\n'
        "contract Pool {}\n",
    )
    # The declared interface path is intentionally absent.
    # A matching interface exists elsewhere, but it is not the file declared by the target.
    _write(
        root / "unrelated" / "IVotingEscrow.sol",
        "interface IVotingEscrow { function token() external view returns (address); }\n",
    )

    with pytest.raises(
        FileNotFoundError,
        match="declared import ./interfaces/IVotingEscrow\\.sol.*has no remapping or relative target",
    ):
        resolve_interface(root, root / "contracts" / "Pool.sol", "IVotingEscrow")


def test_declared_types_are_scoped_to_resolved_interface_body(tmp_path: Path) -> None:
    root = tmp_path / "target"
    _write(
        root / "contracts" / "Target.sol",
        'import {IMinter} from "./interfaces/IMinter.sol";\ncontract Target {}\n',
    )
    _write(
        root / "contracts" / "interfaces" / "IMinter.sol",
        "interface IMinter {\n"
        "    struct AirdropParams { address[] wallets; }\n"
        "    enum Mode { A, B }\n"
        "    type Amount is uint256;\n"
        "    function initialize(AirdropParams memory params) external returns (bool);\n"
        "}\n"
        "interface IOther {\n"
        "    struct OtherType { uint256 value; }\n"
        "}\n",
    )

    resolved = resolve_interface(root, root / "contracts" / "Target.sol", "IMinter")

    assert resolved.declared_types == ("AirdropParams", "Mode", "Amount")
    assert "OtherType" not in resolved.declared_types
    assert [method.name for method in resolved.methods] == ["initialize"]


def test_preserves_named_imported_signature_types(tmp_path: Path) -> None:
    root = tmp_path / "target"
    _write(
        root / "contracts" / "IAccountManager.sol",
        'import {FeeTiers} from "./FeeTiers.sol";\n'
        "interface IAccountManager {\n"
        "    function getFeeTier(address account) external view returns (FeeTiers);\n"
        "}\n",
    )
    _write(
        root / "contracts" / "FeeTiers.sol",
        "enum FeeTiers { ZERO, ONE }\n",
    )
    _write(
        root / "contracts" / "Target.sol",
        'import {IAccountManager} from "./IAccountManager.sol";\ncontract Target {}\n',
    )
    resolved = resolve_interface(root, root / "contracts" / "Target.sol", "IAccountManager")
    assert resolved.imported_types == (("FeeTiers", "contracts/FeeTiers.sol"),)


def test_preserves_top_level_types_separately_from_interface_types(tmp_path: Path) -> None:
    root = tmp_path / "target"
    _write(
        root / "contracts" / "IManager.sol",
        "struct SettingsParams { uint256 value; }\n"
        "interface IManager { struct Nested { uint256 value; } }\n",
    )
    _write(root / "contracts" / "Target.sol", 'import {IManager} from "./IManager.sol";\ncontract Target {}\n')
    resolved = resolve_interface(root, root / "contracts" / "Target.sol", "IManager")
    assert resolved.declared_types == ("Nested",)
    assert resolved.top_level_types == ("SettingsParams",)


def test_resolves_interface_through_transitive_import_graph(tmp_path: Path) -> None:
    root = tmp_path / "target"
    _write(
        root / "contracts" / "Target.sol",
        'import "./Base.sol";\ncontract Target {}\n',
    )
    _write(
        root / "contracts" / "Base.sol",
        'import "./types/IMerkle.sol";\ncontract Base {}\n',
    )
    _write(
        root / "contracts" / "types" / "IMerkle.sol",
        "interface IMerkle {\n"
        "    struct MerkleConstructorArgs { uint128 levels; address poseidon2; }\n"
        "}\n",
    )

    resolved = resolve_interface(root, root / "contracts" / "Target.sol", "IMerkle")

    assert resolved.name == "IMerkle"
    assert resolved.source_path == "contracts/types/IMerkle.sol"
    assert resolved.resolution_method == "relative_import"
    assert resolved.declared_types == ("MerkleConstructorArgs",)


def test_resolves_import_through_foundry_toml_remapping(tmp_path: Path) -> None:
    root = tmp_path / "target"
    _write(
        root / "foundry.toml",
        '[profile.default]\nremappings = ["@oz/=lib/openzeppelin/contracts/"]\n',
    )
    _write(
        root / "contracts" / "Token.sol",
        'import "@oz/token/IERC20.sol";\ncontract Token {}\n',
    )
    _write(
        root / "lib" / "openzeppelin" / "contracts" / "token" / "IERC20.sol",
        "interface IERC20 { function decimals() external view returns (uint8); }\n",
    )

    resolved = resolve_interface(root, root / "contracts" / "Token.sol", "IERC20")

    assert resolved.source_path == "lib/openzeppelin/contracts/token/IERC20.sol"
    assert resolved.resolution_method == "remapping"


def test_resolves_import_through_bounded_foundry_dependency_path(tmp_path: Path) -> None:
    root = tmp_path / "target"
    _write(
        root / "contracts" / "Token.sol",
        'import "@openzeppelin/contracts/access/IAccessControl.sol";\ncontract Token {}\n',
    )
    _write(
        root / "lib" / "openzeppelin-contracts" / "contracts" / "access" / "IAccessControl.sol",
        "interface IAccessControl { function hasRole(bytes32, address) external view returns (bool); }\n",
    )

    resolved = resolve_interface(root, root / "contracts" / "Token.sol", "IAccessControl")

    assert resolved.source_path == "lib/openzeppelin-contracts/contracts/access/IAccessControl.sol"
    assert resolved.resolution_method == "dependency_path"


def test_resolves_scoped_npm_dependency_path(tmp_path: Path) -> None:
    root = tmp_path / "target"
    source = root / "contracts" / "Target.sol"
    access = root / "node_modules" / "@openzeppelin" / "contracts" / "access" / "AccessControl.sol"
    _write(
        source,
        'import "@openzeppelin/contracts/access/AccessControl.sol";\ncontract Target is AccessControl {}\n',
    )
    _write(
        access,
        "abstract contract AccessControl { modifier onlyRole(bytes32 role) { _; } }\n",
    )

    resolved = resolve_import(root, source, "@openzeppelin/contracts/access/AccessControl.sol")

    assert resolved is not None
    assert resolved[0] == access


def test_ambiguous_dependency_path_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "target"
    _write(
        root / "contracts" / "Token.sol",
        'import "@vendor/contracts/access/IAccessControl.sol";\ncontract Token {}\n',
    )
    for name in ("one", "two"):
        _write(
            root / "lib" / name / "contracts" / "access" / "IAccessControl.sol",
            "interface IAccessControl {}\n",
        )

    with pytest.raises(FileNotFoundError):
        resolve_interface(root, root / "contracts" / "Token.sol", "IAccessControl")


def test_resolves_source_defined_struct_fields(tmp_path: Path) -> None:
    root = tmp_path / "target"
    source = root / "contracts" / "types" / "IMerkle.sol"
    _write(
        source,
        "interface IMerkle {\n"
        "    struct MerkleConstructorArgs {\n"
        "        uint128 levels;\n"
        "        address poseidon2;\n"
        "        address poseidon4;\n"
        "        address poseidon5;\n"
        "    }\n"
        "}\n",
    )

    fields = resolve_struct_fields(root, "contracts/types/IMerkle.sol", "MerkleConstructorArgs")

    assert fields == (
        ("levels", "uint128"),
        ("poseidon2", "address"),
        ("poseidon4", "address"),
        ("poseidon5", "address"),
    )


def test_resolves_exact_declared_nested_type_import(tmp_path: Path) -> None:
    root = tmp_path / "target"
    source = root / "contracts" / "types" / "CircomData.sol"
    nested = root / "contracts" / "types" / "StealthAddressStructure.sol"
    _write(
        source,
        'import {StealthAddressStructure} from "./StealthAddressStructure.sol";\n'
        "struct CircomData { StealthAddressStructure stealthAddressStructure; }\n",
    )
    _write(
        nested,
        "struct StealthAddressStructure { uint256 H0x; uint256 H0y; uint256 H1x; uint256 H1y; uint256 stealthAddress; }\n",
    )

    from cydra.interface_resolver import resolve_named_type_source

    resolved = resolve_named_type_source(
        root,
        "contracts/types/CircomData.sol",
        "StealthAddressStructure",
    )

    assert resolved == (
        "contracts/types/StealthAddressStructure.sol",
        "direct_declared_import",
    )
