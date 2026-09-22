from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import json
import re
import subprocess
from typing import Any

from .solidity_model import parse_solidity


@dataclass(frozen=True)
class TargetEnvironment:
    language: str
    framework: str
    compiler: str
    project_root: str
    source_root: str
    test_root: str | None
    config_file: str | None
    remappings_file: str | None
    compiler_version: str | None
    optimizer_enabled: bool | None
    via_ir: bool | None
    dependency_roots: tuple[str, ...]
    import_count: int
    deployable_contracts: tuple[str, ...]
    unresolved_constructor_types: tuple[str, ...]
    adapter: str
    confidence: float
    blockers: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _run(project: Path, *command: str) -> tuple[bool, str, str]:
    try:
        completed = subprocess.run(
            command, cwd=project, text=True, capture_output=True, check=False
        )
    except OSError as error:
        return False, "", str(error)
    return completed.returncode == 0, completed.stdout, completed.stderr


def _foundry_config(project: Path) -> dict[str, Any]:
    ok, stdout, _ = _run(project, "forge", "config", "--json")
    if not ok:
        return {}
    try:
        value = json.loads(stdout)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        return {}


def _imports(source: Path) -> tuple[str, ...]:
    text = source.read_text(encoding="utf-8")
    return tuple(dict.fromkeys(re.findall(r"\bimport\s+(?:[^;]*?\s+from\s+)?[\"']([^\"']+)[\"']", text)))


def _constructor_unresolved(contract) -> tuple[str, ...]:
    if contract.constructor is None:
        return ()
    primitive = {"address", "bool", "string", "bytes"}
    unresolved: list[str] = []
    for parameter in contract.constructor.parameters:
        base = parameter.type.strip().split()[0].rstrip("[]")
        if base in primitive or base.startswith(("uint", "int", "bytes")):
            continue
        if base not in {item.name for item in contract.inherited_resolved_interfaces}:
            unresolved.append(base)
    return tuple(dict.fromkeys(unresolved))


def inspect_target(project: str | Path, source: str | Path) -> TargetEnvironment:
    """Build the deterministic execution/environment snapshot before reasoning.

    This is intentionally security-class neutral: it answers how the target is
    built and executed, not whether the target is vulnerable.
    """
    root = Path(project).resolve()
    source_path = Path(source).resolve()
    if not source_path.is_relative_to(root):
        raise ValueError("target source must be inside target project")

    config = root / "foundry.toml"
    framework = "foundry" if config.exists() else "unknown"
    if framework != "foundry":
        return TargetEnvironment(
            language="solidity",
            framework=framework,
            compiler="unknown",
            project_root=str(root),
            source_root=str(source_path.parent),
            test_root=None,
            config_file=None,
            remappings_file=None,
            compiler_version=None,
            optimizer_enabled=None,
            via_ir=None,
            dependency_roots=(),
            import_count=len(_imports(source_path)),
            deployable_contracts=(),
            unresolved_constructor_types=(),
            adapter="unsupported",
            confidence=0.0,
            blockers=("no supported Solidity project adapter",),
        )

    forge = _foundry_config(root)
    contracts = parse_solidity(source_path)
    deployable = tuple(
        contract.name for contract in contracts
        if contract.constructor is not None or contract.functions
    )
    unresolved = tuple(
        name for contract in contracts for name in _constructor_unresolved(contract)
    )
    import_count = len(_imports(source_path))
    test_dir = forge.get("test") or "test"
    libs = forge.get("libs") or ["lib"]
    if isinstance(libs, str):
        libs = [libs]
    dependency_roots = tuple(str((root / item).resolve()) for item in libs)

    compiler = str(forge.get("solc") or forge.get("solc_version") or "solc")
    optimizer = forge.get("optimizer")
    via_ir = forge.get("via_ir")
    blockers: list[str] = []
    if unresolved:
        blockers.append("constructor custom types require dependency resolution before generated deployment")
    confidence = 0.95 if not blockers else 0.75

    return TargetEnvironment(
        language="solidity",
        framework="foundry",
        compiler=compiler,
        project_root=str(root),
        source_root=str(source_path.parent),
        test_root=str(root / test_dir),
        config_file=str(config),
        remappings_file=str(root / "remappings.txt") if (root / "remappings.txt").exists() else None,
        compiler_version=compiler if compiler != "solc" else None,
        optimizer_enabled=optimizer if isinstance(optimizer, bool) else None,
        via_ir=via_ir if isinstance(via_ir, bool) else None,
        dependency_roots=dependency_roots,
        import_count=import_count,
        deployable_contracts=deployable,
        unresolved_constructor_types=unresolved,
        adapter="solidity-foundry-v1",
        confidence=confidence,
        blockers=tuple(blockers),
    )
