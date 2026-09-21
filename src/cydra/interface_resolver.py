from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


@dataclass(frozen=True)
class InterfaceMethod:
    name: str
    parameters: tuple[str, ...]
    returns: tuple[str, ...]


@dataclass(frozen=True)
class ResolvedInterface:
    name: str
    source_path: str
    resolution_method: str
    methods: tuple[InterfaceMethod, ...]
    declared_types: tuple[str, ...] = ()


_INTERFACE_RE = re.compile(r"\binterface\s+(\w+)")
_FUNCTION_RE = re.compile(
    r"\bfunction\s+(\w+)\s*\(([^)]*)\)\s*([^;{]*)\breturns\s*\(([^)]*)\)\s*;",
    re.MULTILINE,
)
_IMPORT_RE = re.compile(r"\bimport\s+(?:[^\"]*from\s+)?\"([^\"]+)\"\s*;", re.MULTILINE)
_REMAP_RE = re.compile(r"^\s*([^=\s]+)\s*=\s*(\S+)\s*$")
_DECLARED_TYPE_RE = re.compile(
    r"^\s*(?:struct\s+(?P<struct>[A-Za-z_]\w*)\s*\{|"
    r"enum\s+(?P<enum>[A-Za-z_]\w*)\s*\{|"
    r"type\s+(?P<type>[A-Za-z_]\w*)\s+is\b)",
    re.MULTILINE,
)


def _strip_comments(source: str) -> str:
    result = list(source)
    i = 0
    quote: str | None = None
    while i < len(source):
        ch = source[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in {"'", '"'}:
            quote = ch
            i += 1
            continue
        if source.startswith("//", i):
            result[i:i + 2] = [" ", " "]
            i += 2
            while i < len(source) and source[i] != "\n":
                result[i] = " "
                i += 1
            continue
        if source.startswith("/*", i):
            result[i:i + 2] = [" ", " "]
            i += 2
            while i < len(source) and not source.startswith("*/", i):
                if source[i] != "\n":
                    result[i] = " "
                i += 1
            if i < len(source):
                result[i:i + 2] = [" ", " "]
                i += 2
            continue
        i += 1
    return "".join(result)


def _split_parameters(text: str) -> tuple[str, ...]:
    parts: list[str] = []
    start = 0
    depth = 0
    for i, ch in enumerate(text):
        if ch in "([{<":
            depth += 1
        elif ch in ")]}>" and depth:
            depth -= 1
        elif ch == "," and depth == 0:
            value = text[start:i].strip()
            if value:
                parts.append(value)
            start = i + 1
    value = text[start:].strip()
    if value:
        parts.append(value)
    return tuple(parts)


def parse_remappings(root: str | Path) -> tuple[tuple[str, str], ...]:
    root = Path(root)
    path = root / "remappings.txt"
    if not path.exists():
        return ()
    result: list[tuple[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = _REMAP_RE.match(line)
        if match:
            result.append(match.groups())
    return tuple(result)


def resolve_import(root: str | Path, importer: str | Path, import_path: str) -> tuple[Path, str] | None:
    root = Path(root).resolve()
    importer = Path(importer).resolve()
    remappings = parse_remappings(root)

    for prefix, destination in sorted(remappings, key=lambda item: len(item[0]), reverse=True):
        if import_path.startswith(prefix):
            candidate = root / destination / import_path[len(prefix):]
            if candidate.is_file():
                return candidate, "remapping"

    if import_path.startswith(("./", "../")):
        relative = (importer.parent / import_path).resolve()
        if relative.is_file():
            return relative, "relative_import"

    # Foundry also permits project-root-relative imports in generated/source
    # contexts. Treat an existing repository-relative path as authoritative
    # after remappings and explicit relative imports have been checked.
    repository_relative = (root / import_path).resolve()
    if repository_relative.is_file():
        return repository_relative, "project_relative"

    return None


def _imports_for(path: Path) -> tuple[str, ...]:
    source = _strip_comments(path.read_text(encoding="utf-8"))
    return tuple(match.group(1) for match in _IMPORT_RE.finditer(source))


def resolve_interface(root: str | Path, importer: str | Path, name: str) -> ResolvedInterface:
    root = Path(root).resolve()
    importer = Path(importer).resolve()
    for import_path in _imports_for(importer):
        if Path(import_path).name != f"{name}.sol" and not import_path.endswith(f"/{name}.sol"):
            continue
        resolved = resolve_import(root, importer, import_path)
        if resolved is None:
            raise FileNotFoundError(
                f"Unable to resolve interface {name}: declared import {import_path} "
                f"from {importer} has no remapping or relative target"
            )
        path, method = resolved
        return _extract_interface(name, path, method, root)

    raise FileNotFoundError(
        f"Unable to resolve interface {name}: no declared import matching {name}.sol in {importer}"
    )


def _extract_interface(
    name: str, path: Path, resolution_method: str, root: Path
) -> ResolvedInterface:
    source = _strip_comments(path.read_text(encoding="utf-8"))
    match = re.search(rf"\binterface\s+{re.escape(name)}\b", source)
    if not match:
        raise ValueError(f"Interface {name} not found at resolved path {path}")
    body_start = source.find("{", match.end())
    if body_start < 0:
        raise ValueError(f"Interface {name} has no body at resolved path {path}")
    depth = 0
    body_end = len(source)
    for index in range(body_start, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                body_end = index
                break
    body = source[body_start + 1:body_end]
    methods: list[InterfaceMethod] = []
    for function in _FUNCTION_RE.finditer(body):
        methods.append(
            InterfaceMethod(
                name=function.group(1),
                parameters=_split_parameters(function.group(2)),
                returns=_split_parameters(function.group(4)),
            )
        )
    declared_types: list[str] = []
    for declaration in _DECLARED_TYPE_RE.finditer(body):
        declared_type = declaration.group("struct") or declaration.group("enum") or declaration.group("type")
        if declared_type and declared_type not in declared_types:
            declared_types.append(declared_type)
    return ResolvedInterface(
        name=name,
        source_path=path.relative_to(root).as_posix(),
        resolution_method=resolution_method,
        methods=tuple(methods),
        declared_types=tuple(declared_types),
    )
