from pathlib import Path

import pytest

from cydra.interface_resolver import resolve_interface


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
