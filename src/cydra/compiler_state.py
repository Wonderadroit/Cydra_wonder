from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .ast_dataflow import SemanticRelationshipEvidence, extract_ast_relationships
from .compiler_constraints import ConstraintEvidence, extract_parameter_constraints


@dataclass(frozen=True)
class CompilerEvidenceResult:
    evidence: tuple[SemanticRelationshipEvidence, ...]
    constraints: tuple[ConstraintEvidence, ...]
    executed: bool
    status: str
    command: tuple[str, ...]
    stdout: str
    stderr: str
    build_info_files: tuple[str, ...] = ()
    compiler_versions: tuple[str, ...] = ()


def _source_keys(payload: dict[str, Any], source: Path, project: Path) -> tuple[tuple[str, dict[str, Any]], ...]:
    output = payload.get("output")
    if not isinstance(output, dict):
        return ()
    sources = output.get("sources")
    if not isinstance(sources, dict):
        return ()
    relative = os.path.relpath(source.resolve(), project.resolve()).replace(os.sep, "/")
    candidates: list[tuple[str, dict[str, Any]]] = []
    for key, value in sources.items():
        if not isinstance(key, str) or not isinstance(value, dict):
            continue
        normalized = key.replace("\\", "/")
        if normalized == relative or normalized.endswith("/" + relative):
            candidates.append((key, value))
    return tuple(candidates)


def extract_state_effects_from_build_info(build_info: Path, source: Path, project: Path) -> tuple[SemanticRelationshipEvidence, ...]:
    payload = json.loads(build_info.read_text(encoding="utf-8"))
    evidence: list[SemanticRelationshipEvidence] = []
    for source_key, source_payload in _source_keys(payload, source, project):
        ast = source_payload.get("ast")
        if isinstance(ast, dict):
            evidence.extend(extract_ast_relationships(ast, source_key))
    return tuple(evidence)


def extract_constraints_from_build_info(build_info: Path, source: Path, project: Path) -> tuple[ConstraintEvidence, ...]:
    payload = json.loads(build_info.read_text(encoding="utf-8"))
    evidence: list[ConstraintEvidence] = []
    for source_key, source_payload in _source_keys(payload, source, project):
        ast = source_payload.get("ast")
        if isinstance(ast, dict):
            evidence.extend(extract_parameter_constraints(ast, source_key))
    return tuple(evidence)


def compile_state_effects(project: str | Path, source: str | Path, *, build_paths: tuple[str | Path, ...] = ()) -> CompilerEvidenceResult:
    """Compile a Foundry project and consume compiler AST evidence when available.

    The selected source is compiled with the target's light profile where available,
    avoiding target-specific optimized/via-IR settings when only AST semantics are needed.
    Compilation failure is a capability gap, not evidence that no state effect exists.
    """
    project_path = Path(project).resolve()
    source_path = Path(source).resolve()
    command = ("forge", "build", "--build-info", "--profile", "lite", "--skip", "test", "--skip", "script", "--threads", "1")
    if not project_path.exists() or not source_path.exists():
        return CompilerEvidenceResult((), (), False, "input_missing", command, "", "project or source missing")

    with tempfile.TemporaryDirectory(prefix="cydra-build-info-", dir=project_path.parent) as temp:
        info_path = Path(temp)
        command = ["forge", "build", "--build-info", "--build-info-path", str(info_path), "--profile", "lite", "--skip", "test", "--skip", "script", "--threads", "1"]
        for build_path in build_paths:
            relative = Path(build_path)
            if relative.is_absolute():
                relative = relative.relative_to(project_path)
            command.append(str(relative))
        command = tuple(command)
        completed = subprocess.run(command, cwd=project_path, text=True, capture_output=True, check=False)
        build_files = tuple(sorted(info_path.rglob("*.json")))
        if completed.returncode != 0:
            return CompilerEvidenceResult((), (), True, "compile_failed", command, completed.stdout, completed.stderr, tuple(map(str, build_files)))

        evidence: list[SemanticRelationshipEvidence] = []
        constraints: list[ConstraintEvidence] = []
        versions: set[str] = set()
        for build_file in build_files:
            try:
                payload = json.loads(build_file.read_text(encoding="utf-8"))
                version = payload.get("solcVersion")
                if isinstance(version, str):
                    versions.add(version)
                evidence.extend(extract_state_effects_from_build_info(build_file, source_path, project_path))
                constraints.extend(extract_constraints_from_build_info(build_file, source_path, project_path))
            except (OSError, json.JSONDecodeError):
                continue
        status = "success" if evidence or constraints else "no_ast_for_source"
        return CompilerEvidenceResult(tuple(evidence), tuple(constraints), True, status, command, completed.stdout, completed.stderr, tuple(map(str, build_files)), tuple(sorted(versions)))
