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


def _walk_ast_nodes(node: Any):
    if isinstance(node, dict):
        if isinstance(node.get("nodeType"), str):
            yield node
        for value in node.values():
            yield from _walk_ast_nodes(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk_ast_nodes(value)


def _dependency_source_keys(payload: dict[str, Any], source: Path, project: Path) -> tuple[tuple[str, dict[str, Any]], ...]:
    """Return the selected source plus compiler-resolved import dependencies.

    Unrelated source units in build-info must not leak semantic evidence into a
    target model. ImportDirective paths and source-unit IDs define the dependency
    closure used for inherited/helper analysis.
    """
    output = payload.get("output")
    if not isinstance(output, dict):
        return ()
    sources = output.get("sources")
    if not isinstance(sources, dict):
        return ()

    entries = {
        key: value for key, value in sources.items()
        if isinstance(key, str) and isinstance(value, dict)
    }
    relative = os.path.relpath(source.resolve(), project.resolve()).replace(os.sep, "/")
    selected = [
        key for key in entries
        if key.replace("\\", "/") == relative
        or key.replace("\\", "/").endswith("/" + relative)
    ]
    if not selected:
        return ()

    source_unit_ids = {}
    for key, value in entries.items():
        ast = value.get("ast")
        if isinstance(ast, dict) and isinstance(ast.get("id"), int):
            source_unit_ids[ast["id"]] = key

    queue = list(selected)
    seen: set[str] = set()
    while queue:
        key = queue.pop(0)
        if key in seen:
            continue
        seen.add(key)
        ast = entries[key].get("ast")
        if not isinstance(ast, dict):
            continue
        for node in _walk_ast_nodes(ast):
            if node.get("nodeType") != "ImportDirective":
                continue
            candidates: list[str] = []
            for field in ("absolutePath", "file"):
                value = node.get(field)
                if isinstance(value, str):
                    candidates.append(value.replace("\\", "/"))
            source_unit = node.get("sourceUnit")
            if isinstance(source_unit, int) and source_unit in source_unit_ids:
                candidates.append(source_unit_ids[source_unit])
            for candidate in candidates:
                for match in entries:
                    normalized = match.replace("\\", "/")
                    if normalized == candidate or normalized.endswith("/" + candidate):
                        if match not in seen:
                            queue.append(match)

    return tuple((key, entries[key]) for key in seen)


def extract_state_effects_from_build_info(build_info: Path, source: Path, project: Path) -> tuple[SemanticRelationshipEvidence, ...]:
    payload = json.loads(build_info.read_text(encoding="utf-8"))
    evidence: list[SemanticRelationshipEvidence] = []
    # Build-info for a compiled target contains imported/inherited source ASTs.
    # State-effect extraction intentionally consumes that complete semantic
    # surface; constraints remain scoped to the selected target source below.
    for source_key, source_payload in _dependency_source_keys(payload, source, project):
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


def _has_lite_profile(project: Path) -> bool:
    config = project / "foundry.toml"
    try:
        return "[profile.lite]" in config.read_text(encoding="utf-8")
    except OSError:
        return False


def compile_state_effects(project: str | Path, source: str | Path) -> CompilerEvidenceResult:
    """Compile a Foundry project and consume compiler AST evidence when available.

    Compilation failure is a capability gap, not evidence that no state effect exists.
    """
    project_path = Path(project).resolve()
    source_path = Path(source).resolve()
    command = ("forge", "build", "--build-info")
    if not project_path.exists() or not source_path.exists():
        return CompilerEvidenceResult((), (), False, "input_missing", command, "", "project or source missing")

    with tempfile.TemporaryDirectory(prefix="cydra-build-info-", dir=project_path.parent) as temp:
        info_path = Path(temp)
        relative_source = os.path.relpath(source_path, project_path).replace(os.sep, "/")
        profile = ("--profile", "lite") if _has_lite_profile(project_path) else ()
        command = (
            "forge", "build", "--build-info", "--build-info-path", str(info_path),
            *profile, "--skip", "test", "--skip", "script", "--threads", "1", relative_source,
        )
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
