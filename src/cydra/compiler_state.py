from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .ast_dataflow import SemanticRelationshipEvidence, _walk, extract_ast_relationships
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


def _compiler_declaration_context(
    asts: list[dict[str, Any]],
) -> tuple[dict[int, tuple[str, str, int]], dict[int, set[int]]]:
    """Build one compiler-wide function/inheritance index for all source ASTs."""
    functions: dict[int, tuple[str, str, int]] = {}
    contract_bases: dict[int, set[int]] = {}

    for ast in asts:
        for node in _walk(ast):
            if node.get("nodeType") != "ContractDefinition" or not isinstance(node.get("id"), int):
                continue
            bases: set[int] = set()
            for base in node.get("baseContracts", []) if isinstance(node.get("baseContracts"), list) else []:
                base_name = base.get("baseName") if isinstance(base, dict) else None
                ref = base_name.get("referencedDeclaration") if isinstance(base_name, dict) else None
                if isinstance(ref, int):
                    bases.add(ref)
            contract_bases[node["id"]] = bases

    def ancestors(contract_id: int, seen: set[int] | None = None) -> set[int]:
        seen = set() if seen is None else seen
        for base_id in contract_bases.get(contract_id, set()):
            if base_id in seen:
                continue
            seen.add(base_id)
            ancestors(base_id, seen)
        return seen

    contract_ancestors = {cid: ancestors(cid) for cid in contract_bases}

    for ast in asts:
        declarations = {
            node["id"]: node
            for node in _walk(ast)
            if isinstance(node.get("id"), int)
        }
        for node in _walk(ast):
            if node.get("nodeType") != "FunctionDefinition" or not isinstance(node.get("id"), int):
                continue
            scope = node.get("scope")
            if not isinstance(scope, int):
                continue
            contract_name = declarations.get(scope, {}).get("name", "unknown")
            kind = node.get("kind")
            name = (
                node.get("name")
                if isinstance(node.get("name"), str) and node.get("name")
                else kind if kind in {"constructor", "receive", "fallback"} else "anonymous"
            )
            functions[node["id"]] = (str(contract_name), str(name), scope)

    return functions, contract_ancestors

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


def extract_state_effects_from_all_sources(build_info: Path) -> tuple[SemanticRelationshipEvidence, ...]:
    """Extract compiler-backed state effects from every source in build-info.

    The selected target-source helper above intentionally remains target-scoped
    for callers that need that boundary. Compiler-backed call/state resolution,
    however, needs imported and inherited declarations as evidence too.
    """
    payload = json.loads(build_info.read_text(encoding="utf-8"))
    output = payload.get("output")
    sources = output.get("sources") if isinstance(output, dict) else None
    if not isinstance(sources, dict):
        return ()
    ast_sources: list[tuple[str, dict[str, Any]]] = []
    for source_key, source_payload in sources.items():
        if not isinstance(source_key, str) or not isinstance(source_payload, dict):
            continue
        ast = source_payload.get("ast")
        if isinstance(ast, dict):
            ast_sources.append((source_key, ast))

    functions, contract_ancestors = _compiler_declaration_context([ast for _, ast in ast_sources])
    evidence: list[SemanticRelationshipEvidence] = []
    for source_key, ast in ast_sources:
        evidence.extend(
            extract_ast_relationships(
                ast,
                source_key,
                global_functions=functions,
                global_contract_ancestors=contract_ancestors,
            )
        )
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
                evidence.extend(extract_state_effects_from_all_sources(build_file))
                constraints.extend(extract_constraints_from_build_info(build_file, source_path, project_path))
            except (OSError, json.JSONDecodeError):
                continue
        status = "success" if evidence or constraints else "no_ast_for_source"
        return CompilerEvidenceResult(tuple(evidence), tuple(constraints), True, status, command, completed.stdout, completed.stderr, tuple(map(str, build_files)), tuple(sorted(versions)))
