from pathlib import Path

from cydra.target_adapter import inspect_target


def test_foundry_target_intake_detects_environment_and_dependencies(tmp_path: Path, monkeypatch):
    (tmp_path / "foundry.toml").write_text(
        "[profile.default]\nsrc='src'\ntest='test'\nlibs=['lib']\n"
        "solc='0.8.24'\noptimizer=true\nvia_ir=false\n",
        encoding="utf-8",
    )
    (tmp_path / "src").mkdir()
    source = tmp_path / "src" / "Target.sol"
    source.write_text(
        'pragma solidity ^0.8.24; import "@openzeppelin/contracts/token/ERC20/IERC20.sol"; '
        'contract Target { function ping() external {} }',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "cydra.target_adapter._foundry_config",
        lambda project: {
            "solc": "0.8.24",
            "optimizer": True,
            "via_ir": False,
            "test": "test",
            "libs": ["lib"],
        },
    )
    intake = inspect_target(tmp_path, source)
    assert intake.framework == "foundry"
    assert intake.adapter == "solidity-foundry-v1"
    assert intake.compiler_version == "0.8.24"
    assert intake.optimizer_enabled is True
    assert intake.via_ir is False
    assert intake.import_count == 1
    assert intake.dependency_roots == (str((tmp_path / "lib").resolve()),)


def test_npm_solidity_target_gets_generic_execution_adapter(tmp_path: Path):
    (tmp_path / "contracts").mkdir()
    (tmp_path / "package.json").write_text("{}\\n", encoding="utf-8")
    (tmp_path / "hardhat.config.js").write_text("module.exports = {};\\n", encoding="utf-8")
    source = tmp_path / "contracts" / "Target.sol"
    source.write_text("pragma solidity ^0.8.20; contract Target {}", encoding="utf-8")
    intake = inspect_target(tmp_path, source)
    assert intake.framework == "hardhat"
    assert intake.adapter == "solidity-generic-foundry"
    assert intake.confidence > 0
    assert intake.blockers == ()


def test_foundry_target_intake_resolves_namespaced_interface_struct_constructor(tmp_path, monkeypatch):
    (tmp_path / "foundry.toml").write_text(
        "[profile.default]\nsolc='0.8.24'\nlibs=['lib']\n",
        encoding="utf-8",
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "IMerkle.sol").write_text(
        "interface IMerkle { struct MerkleConstructorArgs { uint128 levels; address poseidon2; } }\n",
        encoding="utf-8",
    )
    source = tmp_path / "src" / "Target.sol"
    source.write_text(
        'pragma solidity ^0.8.24; import "./IMerkle.sol"; '
        'contract Target { constructor(IMerkle.MerkleConstructorArgs memory args) {} }\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "cydra.target_adapter._foundry_config",
        lambda project: {"solc": "0.8.24", "optimizer": False, "via_ir": False, "test": "test", "libs": ["lib"]},
    )
    intake = inspect_target(tmp_path, source)
    assert intake.unresolved_constructor_types == ()
    assert intake.blockers == ()


def test_foundry_target_intake_resolves_transitive_namespaced_interface_struct_constructor(tmp_path, monkeypatch):
    (tmp_path / "foundry.toml").write_text(
        "[profile.default]\nsolc='0.8.24'\nlibs=['lib']\n",
        encoding="utf-8",
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "IMerkle.sol").write_text(
        "interface IMerkle { struct MerkleConstructorArgs { uint128 levels; address poseidon2; } }\n",
        encoding="utf-8",
    )
    (tmp_path / "src" / "Base.sol").write_text(
        'import "./IMerkle.sol"; contract Base {}\n',
        encoding="utf-8",
    )
    source = tmp_path / "src" / "Target.sol"
    source.write_text(
        'pragma solidity ^0.8.24; import "./Base.sol"; '
        'contract Target { constructor(IMerkle.MerkleConstructorArgs memory args) {} }\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "cydra.target_adapter._foundry_config",
        lambda project: {"solc": "0.8.24", "optimizer": False, "via_ir": False, "test": "test", "libs": ["lib"]},
    )
    intake = inspect_target(tmp_path, source)
    assert intake.unresolved_constructor_types == ()
    assert intake.blockers == ()
