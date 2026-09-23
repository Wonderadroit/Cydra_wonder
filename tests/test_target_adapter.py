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


def test_unsupported_environment_fails_closed(tmp_path: Path):
    (tmp_path / "src").mkdir()
    source = tmp_path / "src" / "Target.sol"
    source.write_text("pragma solidity ^0.8.20; contract Target {}", encoding="utf-8")
    intake = inspect_target(tmp_path, source)
    assert intake.adapter == "unsupported"
    assert intake.confidence == 0.0
    assert intake.blockers
