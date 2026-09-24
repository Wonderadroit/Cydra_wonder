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
    source.write_text("contract Fixture {}\\n", encoding="utf-8")
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


def test_compiler_retries_stack_too_deep_with_bounded_via_ir(tmp_path, monkeypatch):
    project = tmp_path / "project"
    source = project / "contracts" / "Fixture.sol"
    source.parent.mkdir(parents=True)
    source.write_text("contract Fixture {}
", encoding="utf-8")
    calls = []

    class Failed:
        returncode = 1
        stdout = ""
        stderr = "Error: Stack too deep. Try compiling with --via-ir."

    class Succeeded:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def fake_run(command, **kwargs):
        calls.append(command)
        return Failed() if len(calls) == 1 else Succeeded()

    monkeypatch.setattr("cydra.compiler_state.subprocess.run", fake_run)
    from cydra.compiler_state import compile_state_effects

    result = compile_state_effects(project, source)

    assert result.status == "no_ast_for_source"
    assert len(calls) == 2
    assert "--via-ir" in calls[1]
    assert "--optimize" in calls[1]
    assert "--optimizer-runs" in calls[1]
    assert result.command == calls[1]
