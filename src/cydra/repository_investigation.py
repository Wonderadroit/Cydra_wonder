"""Repository-level blind research orchestration.

This module bridges a repository target and CYDRA's existing contract-level
reasoning surfaces. Discovery is separate from execution: all in-scope
Solidity units are modeled first, then each is investigated through the same
pipeline. No vulnerability class or target-specific answer is injected here.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable

from .models import ContractModel, InvestigationResult
from .solidity_model import parse_solidity
from .solidity_system_model import project_contracts
from .system_model import SystemModel


def _namespace_result(result: InvestigationResult, prefix: str) -> InvestigationResult:
    """Keep generated execution identities unique across source files."""
    hypotheses = tuple(
        replace(item, hypothesis_id=f"{prefix}{item.hypothesis_id}")
        for item in result.hypotheses
    )
    hypothesis_ids = {
        item.hypothesis_id.replace(prefix, "", 1): item.hypothesis_id
        for item in hypotheses
    }
    experiments = tuple(
        replace(
            item,
            experiment_id=f"{prefix}{item.experiment_id}",
            hypothesis_id=hypothesis_ids.get(
                item.hypothesis_id, f"{prefix}{item.hypothesis_id}"
            ),
        )
        for item in result.experiments
    )
    return replace(result, hypotheses=hypotheses, experiments=experiments)


DEFAULT_EXCLUDED_PARTS = frozenset({
    ".git", "lib", "node_modules", "out", "cache",
    "test", "tests", "script", "scripts", "mock", "mocks",
    "deploy", "deployment", "deployments",
})


@dataclass(frozen=True)
class RepositoryInvestigation:
    root: str
    source_files: tuple[str, ...]
    skipped_files: tuple[str, ...]
    contracts: tuple[ContractModel, ...]
    system_model: SystemModel
    results: tuple[InvestigationResult, ...]

    @property
    def invariants(self):
        return tuple(item for result in self.results for item in result.invariants)

    @property
    def hypotheses(self):
        return tuple(item for result in self.results for item in result.hypotheses)

    @property
    def experiments(self):
        return tuple(item for result in self.results for item in result.experiments)

    @property
    def evidence(self):
        return tuple(item for result in self.results for item in result.evidence)


def discover_in_scope_solidity(
    root: str | Path,
    *,
    source_roots: Iterable[str] = ("src", "contracts"),
    excluded_parts: Iterable[str] = DEFAULT_EXCLUDED_PARTS,
) -> tuple[Path, ...]:
    """Inventory Solidity source deterministically without inspecting excluded code."""
    base = Path(root).resolve()
    excluded = set(excluded_parts)
    roots = [base / name for name in source_roots if (base / name).is_dir()]
    candidates: list[Path] = []
    for search_root in roots or [base]:
        for path in search_root.rglob("*.sol"):
            relative = path.relative_to(base)
            if any(part in excluded for part in relative.parts):
                continue
            candidates.append(path)
    return tuple(sorted(set(candidates), key=lambda p: p.as_posix()))


def investigate_repository(
    root: str | Path,
    *,
    semantic_evidence=(),
    constraint_evidence=(),
    target: str | None = None,
    source_files: Iterable[str | Path] | None = None,
    reasoning_surfaces=None,
    experiment_planner=None,
) -> RepositoryInvestigation:
    """Build one repository model, then investigate every parsed source unit."""
    base = Path(root).resolve()
    paths = (
        tuple(Path(item).resolve() for item in source_files)
        if source_files is not None
        else discover_in_scope_solidity(base)
    )

    contracts: list[ContractModel] = []
    skipped: list[str] = []
    parsed_by_path: dict[Path, tuple[ContractModel, ...]] = {}
    for path in paths:
        try:
            parsed = parse_solidity(path)
        except (OSError, UnicodeError, ValueError):
            skipped.append(path.relative_to(base).as_posix())
            continue
        if not parsed:
            skipped.append(path.relative_to(base).as_posix())
            continue
        parsed_by_path[path] = tuple(parsed)
        contracts.extend(parsed)

    # Build the canonical graph from the complete repository before executing
    # any hypothesis. This is the system-understanding boundary.
    canonical = project_contracts(tuple(contracts))

    from .pipeline import investigate
    semantic = tuple(semantic_evidence or ())
    constraints = tuple(constraint_evidence or ())
    results: list[InvestigationResult] = []
    for path in paths:
        if path not in parsed_by_path:
            continue
        result = investigate(
            path,
            target=target or str(path.relative_to(base)),
            semantic_evidence=semantic,
            constraint_evidence=constraints,
            experiment_planner=experiment_planner,
            reasoning_surfaces=reasoning_surfaces,
        )
        results.append(_namespace_result(result, "repo_" + path.stem + "_"))

    return RepositoryInvestigation(
        root=str(base),
        source_files=tuple(path.relative_to(base).as_posix() for path in paths),
        skipped_files=tuple(sorted(skipped)),
        contracts=tuple(contracts),
        system_model=canonical,
        results=tuple(results),
    )
