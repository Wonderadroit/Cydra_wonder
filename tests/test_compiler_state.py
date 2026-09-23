from __future__ import annotations

import json
from pathlib import Path

from cydra.compiler_state import extract_state_effects_from_build_info


def _build_info(tmp_path: Path) -> tuple[Path, Path, Path]:
    project = tmp_path / "project"
    source = project / "src" / "Fixture.sol"
    source.parent.mkdir(parents=True)
    source.write_text("contract Fixture { uint256 value; function set(uint256 x) external { value = x; } }\n", encoding="utf-8")

    ast = {
        "nodeType": "SourceUnit",
        "id": 1,
        "nodes": [
            {
                "nodeType": "ContractDefinition",
                "id": 2,
                "name": "Fixture",
                "nodes": [
                    {"nodeType": "VariableDeclaration", "id": 3, "name": "value", "stateVariable": True},
                    {
                        "nodeType": "FunctionDefinition",
                        "id": 4,
                        "name": "set",
                        "kind": "function",
                        "scope": 2,
                        "body": {
                            "nodeType": "Block",
                            "statements": [
                                {
                                    "nodeType": "ExpressionStatement",
                                    "expression": {
                                        "nodeType": "Assignment",
                                        "operator": "=",
                                        "leftHandSide": {"nodeType": "Identifier", "id": 5, "referencedDeclaration": 3, "name": "value"},
                                        "rightHandSide": {"nodeType": "Identifier", "id": 6, "referencedDeclaration": 7, "name": "x"},
                                    },
                                }
                            ],
                        },
                    },
                ],
            }
        ],
    }
    build = tmp_path / "build-info.json"
    build.write_text(json.dumps({"solcVersion": "0.8.28", "output": {"sources": {"src/Fixture.sol": {"ast": ast}}}}), encoding="utf-8")
    return project, source, build


def test_extracts_compiler_state_effects_for_selected_source(tmp_path):
    project, source, build = _build_info(tmp_path)

    evidence = extract_state_effects_from_build_info(build, source, project)

    semantic = [item for item in evidence if item.relation == "writes"]
    assert len(semantic) == 1
    assert semantic[0].contract == "Fixture"
    assert semantic[0].function == "set"
    assert semantic[0].target == "value"
    assert semantic[0].metadata["semantic_relation"] == "write"
    assert semantic[0].target_ast_node_id == 3


def test_unmatched_source_does_not_invent_semantic_evidence(tmp_path):
    project, _source, build = _build_info(tmp_path)
    other = project / "src" / "Other.sol"
    other.write_text("contract Other {}\n", encoding="utf-8")

    evidence = extract_state_effects_from_build_info(build, other, project)

    assert evidence == ()



def test_compiler_uses_bounded_lightweight_profile_and_selected_source(tmp_path, monkeypatch):
    project = tmp_path / "project"
    source = project / "src" / "Fixture.sol"
    source.parent.mkdir(parents=True)
    source.write_text("contract Fixture {}\n", encoding="utf-8")
    (project / "foundry.toml").write_text("[profile.lite]\nsolc_version = \"0.8.28\"\n", encoding="utf-8")
    captured = {}

    class Completed:
        returncode = 1
        stdout = "stdout"
        stderr = "stderr"

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return Completed()

    monkeypatch.setattr("cydra.compiler_state.subprocess.run", fake_run)
    from cydra.compiler_state import compile_state_effects
    result = compile_state_effects(project, source)

    assert result.status == "compile_failed"
    assert result.command[0:4] == ("forge", "build", "--build-info", "--build-info-path")
    assert result.command[5:] == (
        "--profile", "lite", "--skip", "test", "--skip", "script", "--threads", "1",
        "src/Fixture.sol",
    )
    assert captured["kwargs"]["cwd"] == project.resolve()
    assert captured["kwargs"]["check"] is False



def test_compiler_does_not_require_lite_profile(tmp_path, monkeypatch):
    project = tmp_path / "project"
    source = project / "contracts" / "Fixture.sol"
    source.parent.mkdir(parents=True)
    source.write_text("contract Fixture {}\n", encoding="utf-8")

    class Completed:
        returncode = 1
        stdout = ""
        stderr = ""

    captured = {}
    def fake_run(command, **kwargs):
        captured["command"] = command
        return Completed()

    monkeypatch.setattr("cydra.compiler_state.subprocess.run", fake_run)
    from cydra.compiler_state import compile_state_effects
    result = compile_state_effects(project, source)

    assert result.status == "compile_failed"
    assert "--profile" not in result.command
    assert result.command[-3:] == ("--threads", "1", "contracts/Fixture.sol")


def test_extracts_selected_source_import_dependencies_without_unrelated_leakage(tmp_path):
    project = tmp_path / "project"
    source = project / "src" / "Fixture.sol"
    imported = project / "src" / "Base.sol"
    source.parent.mkdir(parents=True)
    source.write_text("import \"./Base.sol\"; contract Fixture {}", encoding="utf-8")
    imported.write_text("contract Base { uint256 value; function read() external { uint256 x = value; x; } }", encoding="utf-8")

    base_ast = {
        "nodeType": "SourceUnit",
        "id": 20,
        "nodes": [{
            "nodeType": "ContractDefinition",
            "id": 21,
            "name": "Base",
            "nodes": [
                {"nodeType": "VariableDeclaration", "id": 22, "name": "value", "stateVariable": True},
                {"nodeType": "FunctionDefinition", "id": 23, "name": "read", "kind": "function", "scope": 21,
                 "body": {"nodeType": "Block", "statements": [{
                     "nodeType": "ExpressionStatement",
                     "expression": {"nodeType": "Identifier", "id": 24, "referencedDeclaration": 22, "name": "value"},
                 }]}},
            ],
        }],
    }
    fixture_ast = {
        "nodeType": "SourceUnit",
        "id": 10,
        "nodes": [{
            "nodeType": "ImportDirective",
            "id": 11,
            "absolutePath": "src/Base.sol",
            "sourceUnit": 20,
        }, {
            "nodeType": "ContractDefinition", "id": 12, "name": "Fixture", "nodes": [],
        }],
    }
    unrelated_ast = {
        "nodeType": "SourceUnit",
        "id": 30,
        "nodes": [{
            "nodeType": "ContractDefinition", "id": 31, "name": "Other",
            "nodes": [{"nodeType": "VariableDeclaration", "id": 32, "name": "secret", "stateVariable": True}],
        }],
    }
    build = tmp_path / "build-info.json"
    build.write_text(json.dumps({"output": {"sources": {
        "src/Fixture.sol": {"ast": fixture_ast},
        "src/Base.sol": {"ast": base_ast},
        "src/Other.sol": {"ast": unrelated_ast},
    }}}), encoding="utf-8")

    evidence = extract_compiler = extract_state_effects_from_build_info(build, source, project)
    assert any(item.contract == "Base" and item.function == "read" and item.target == "value" for item in evidence)
    assert not any(item.contract == "Other" for item in evidence)
