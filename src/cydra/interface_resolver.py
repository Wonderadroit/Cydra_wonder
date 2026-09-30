from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import json


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
    imported_types: tuple[tuple[str, str], ...] = ()
    top_level_types: tuple[str, ...] = ()


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


def _foundry_remappings(root: str | Path) -> tuple[tuple[str, str], ...]:
    """Read explicit remappings from foundry.toml without requiring a TOML package."""
    path = Path(root) / "foundry.toml"
    if not path.exists():
        return ()
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ()
    match = re.search(r"(?m)^\s*remappings\s*=\s*\[([^\]]*)\]", source)
    if not match:
        return ()
    result: list[tuple[str, str]] = []
    for item in re.finditer(r'"([^"]+)"', match.group(1)):
        parsed = _REMAP_RE.match(item.group(1))
        if parsed:
            result.append(parsed.groups())
    return tuple(result)


def _dependency_roots(root: str | Path) -> tuple[Path, ...]:
    """Return bounded Foundry/npm dependency roots used by the target adapter."""
    root = Path(root).resolve()
    roots: list[Path] = []
    for name in ("lib", "node_modules"):
        candidate = root / name
        if candidate.is_dir() and candidate not in roots:
            roots.append(candidate)
    return tuple(roots)


def _dependency_package_dirs(root: str | Path) -> tuple[Path, ...]:
    """Return bounded direct dependency package directories, including npm scopes."""
    result: list[Path] = []
    for dependency_root in _dependency_roots(root):
        try:
            children = tuple(sorted(dependency_root.iterdir(), key=lambda item: item.name))
        except OSError:
            continue
        for child in children:
            if not child.is_dir():
                continue
            result.append(child)
            # npm scoped packages live one level below the scope directory,
            # e.g. node_modules/@openzeppelin/contracts. Keep this bounded to
            # the package-manager's direct scope layout; never recursively scan
            # arbitrary dependency trees.
            if child.name.startswith("@"):
                try:
                    scoped = tuple(sorted(child.iterdir(), key=lambda item: item.name))
                except OSError:
                    continue
                result.extend(item for item in scoped if item.is_dir())
    return tuple(dict.fromkeys(result))


def _package_name(path: Path) -> str | None:
    """Read an optional package manifest name for dependency provenance."""
    manifest = path / "package.json"
    if not manifest.is_file():
        return None
    try:
        value = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    name = value.get("name") if isinstance(value, dict) else None
    return name if isinstance(name, str) and name else None


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


def _resolve_source_path(root: str | Path, source_path: str | Path) -> Path:
    """Resolve a source path relative to the declared project root when needed."""
    root = Path(root).resolve()
    path = Path(source_path)
    if not path.is_absolute():
        path = root / path
    return path.resolve()


def resolve_import(root: str | Path, importer: str | Path, import_path: str) -> tuple[Path, str] | None:
    root = Path(root).resolve()
    importer = _resolve_source_path(root, importer)
    remappings = (*parse_remappings(root), *_foundry_remappings(root))

    for prefix, destination in sorted(dict.fromkeys(remappings), key=lambda item: len(item[0]), reverse=True):
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

    # Foundry's auto-detected dependency remappings may not exist in
    # remappings.txt or foundry.toml. Resolve them only inside declared
    # dependency roots; do not scan the target source tree for symbols.
    parts = import_path.split("/")
    if import_path.startswith("@") and len(parts) >= 2:
        package_candidates = ["/".join(parts[:2])]
        suffix = "/".join(parts[2:])
    elif parts:
        package_candidates = [parts[0]]
        suffix = "/".join(parts[1:])
    else:
        package_candidates = []
        suffix = ""

    for dependency_root in _dependency_roots(root):
        for package_dir in _dependency_package_dirs(root):
            if _package_name(package_dir) not in package_candidates:
                continue
            for source_root in ("", "src", "contracts"):
                candidate = (package_dir / source_root / suffix).resolve()
                if candidate.is_file():
                    return candidate, "dependency_package"

    # Foundry library directories may use a repository directory name that
    # differs from the import package name (for example an OpenZeppelin library).
    # Compare only the path after the import package prefix, and require a unique
    # match across direct dependency roots. Ambiguity remains unresolved.
    candidates: list[Path] = []
    for dependency_root in _dependency_roots(root):
        for package_dir in _dependency_package_dirs(root):
            if not package_dir.is_dir():
                continue
            for source_root in ("", "src", "contracts"):
                candidate = (package_dir / source_root / suffix).resolve()
                if candidate.is_file() and candidate not in candidates:
                    candidates.append(candidate)
    if len(candidates) == 1:
        return candidates[0], "dependency_path"

    return None


def _imports_for(path: Path) -> tuple[str, ...]:
    source = _strip_comments(path.read_text(encoding="utf-8"))
    return tuple(match.group(1) for match in _IMPORT_RE.finditer(source))


def resolve_interface(root: str | Path, importer: str | Path, name: str) -> ResolvedInterface:
    """Resolve an interface through the target's import/dependency graph.

    Solidity names can be used through an import that is several source units
    away from the target contract (for example Hinkal -> HinkalBase -> IMerkle).
    Resolution follows only declared imports, never a repository-wide filename
    search, so provenance remains bounded to the target's dependency graph.
    """
    root = Path(root).resolve()
    importer = _resolve_source_path(root, importer)
    visited: set[Path] = set()

    def walk(path: Path) -> ResolvedInterface | None:
        path = path.resolve()
        if path in visited or not path.is_file():
            return None
        visited.add(path)

        imports = _imports_for(path)

        # Preserve the existing strict behavior for a direct import whose
        # filename explicitly identifies the requested interface.
        for import_path in imports:
            if Path(import_path).name != f"{name}.sol" and not import_path.endswith(f"/{name}.sol"):
                continue
            resolved = resolve_import(root, path, import_path)
            if resolved is None:
                if path == importer:
                    raise FileNotFoundError(
                        f"Unable to resolve interface {name}: declared import {import_path} "
                        f"from {path} has no remapping or relative target"
                    )
                continue
            resolved_path, method = resolved
            try:
                source = _strip_comments(resolved_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError):
                continue
            if re.search(rf"\binterface\s+{re.escape(name)}\b", source):
                return _extract_interface(name, resolved_path, method, root)

        # A source unit may aggregate or alias the interface without a
        # filename/name match. Inspect the unit itself before descending.
        try:
            source = _strip_comments(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError):
            source = ""
        if re.search(rf"\binterface\s+{re.escape(name)}\b", source):
            method = "dependency_graph" if path != importer else "direct_source"
            return _extract_interface(name, path, method, root)

        # Follow every resolvable declared import. This is the generic
        # transitive dependency case; cycles are bounded by the visited set.
        for import_path in imports:
            resolved = resolve_import(root, path, import_path)
            if resolved is None:
                continue
            result = walk(resolved[0])
            if result is not None:
                return result
        return None

    resolved = walk(importer)
    if resolved is not None:
        return resolved
    raise FileNotFoundError(
        f"Unable to resolve interface {name} through imports from {importer}"
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
    # A Solidity source file may declare ABI structs/enums alongside the
    # interface and use them in interface methods. Preserve only declarations
    # at source scope separately; declarations belonging to an interface body
    # remain in declared_types and must be referenced as Interface.Type.
    top_level_types: list[str] = []
    for declaration in _DECLARED_TYPE_RE.finditer(source):
        prefix = source[:declaration.start()]
        depth = prefix.count("{") - prefix.count("}")
        if depth != 0:
            continue
        declared_type = declaration.group("struct") or declaration.group("enum") or declaration.group("type")
        if declared_type and declared_type not in top_level_types:
            top_level_types.append(declared_type)

    # Preserve provenance for named symbols imported by the interface source.
    # Interface method signatures may use a top-level struct/enum/value type
    # declared in an imported file; a generated runtime stub must import that
    # symbol too or the otherwise-correct signature becomes uncompilable.
    imported_types: list[tuple[str, str]] = []
    for import_match in re.finditer(
        r'import\s*\{([^}]+)\}\s*from\s*"([^"]+)"\s*;',
        source,
        re.MULTILINE,
    ):
        symbols_text, import_path = import_match.groups()
        resolved_import = resolve_import(root, path, import_path)
        if resolved_import is None:
            continue
        imported_path, _ = resolved_import
        for symbol in _split_parameters(symbols_text):
            token = symbol.strip()
            if not token:
                continue
            parts = re.split(r'\s+as\s+', token, maxsplit=1)
            imported_name = parts[-1].strip()
            if imported_name and imported_name not in {item[0] for item in imported_types}:
                imported_types.append(
                    (imported_name, imported_path.relative_to(root).as_posix())
                )

    return ResolvedInterface(
        name=name,
        source_path=path.relative_to(root).as_posix(),
        resolution_method=resolution_method,
        methods=tuple(methods),
        declared_types=tuple(declared_types),
        imported_types=tuple(imported_types),
        top_level_types=tuple(top_level_types),
    )


def resolve_namespaced_struct_fields(root: str | Path, source_path: str | Path, namespace: str, struct_name: str) -> tuple[tuple[str, str], ...]:
    """Resolve a struct nested inside a contract, library, or interface."""
    path = _resolve_source_path(root, source_path)
    try:
        source = _strip_comments(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError):
        return ()
    owner = re.search(rf"\b(?:contract|library|interface)\s+{re.escape(namespace)}\b", source)
    if owner is None:
        return ()
    body_start = source.find("{", owner.end())
    if body_start < 0:
        return ()
    depth = 0
    body_end = len(source)
    for index in range(body_start, len(source)):
        if source[index] == "{": depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                body_end = index
                break
    body = source[body_start + 1:body_end]
    match = re.search(rf"\bstruct\s+{re.escape(struct_name)}\s*\{{(?P<body>.*?)\}}", body, re.DOTALL)
    if match is None:
        return ()
    fields: list[tuple[str, str]] = []
    for statement in match.group("body").split(";"):
        parts = statement.strip().split()
        if len(parts) >= 2:
            fields.append((parts[-1], " ".join(parts[:-1])))
    return tuple(fields)

def resolve_struct_fields(root: str | Path, source_path: str | Path, struct_name: str) -> tuple[tuple[str, str], ...]:
    """Resolve top-level fields of a source-defined Solidity struct."""
    path = _resolve_source_path(root, source_path)
    try:
        source = _strip_comments(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError):
        return ()
    match = re.search(rf"\bstruct\s+{re.escape(struct_name)}\s*\{{(?P<body>.*?)\}}", source, re.DOTALL)
    if not match:
        return ()
    fields: list[tuple[str, str]] = []
    for statement in match.group("body").split(";"):
        statement = statement.strip()
        if not statement:
            continue
        parts = statement.split()
        if len(parts) < 2:
            continue
        fields.append((parts[-1], " ".join(parts[:-1])))
    return tuple(fields)


def resolve_named_type_source(root: str | Path, importer: str | Path, name: str) -> tuple[str, str]:
    """Resolve a user-defined Solidity type through the target's bounded import graph.

    The resolver deliberately separates graph discovery from symbol matching:
    every reachable source unit is discovered from declared imports, then the
    requested declaration is checked in each unit. This handles plain imports,
    named imports, aliases, transitive imports, and files whose names do not
    match the Solidity symbol (for example Nested.sol declaring Outer).
    """
    root = Path(root).resolve()
    start = _resolve_source_path(root, importer)
    visited: set[Path] = set()
    declaration = re.compile(
        rf"\b(?:contract|interface|library|struct|enum|type)\s+{re.escape(name)}\b"
    )
    import_pattern = re.compile(
        r"""import\s+(?:[^"\']+\s+from\s+)?["\']([^"\']+)["\']\s*;"""
        re.MULTILINE,
    )

    def imports_for(path: Path) -> tuple[str, ...]:
        try:
            source = _strip_comments(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError):
            return ()
        return tuple(dict.fromkeys(import_pattern.findall(source)))

    pending = [start]
    while pending:
        path = pending.pop(0).resolve()
        if path in visited or not path.is_file():
            continue
        visited.add(path)
        try:
            source = _strip_comments(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError):
            continue

        if declaration.search(source):
            return path.relative_to(root).as_posix(), "declaration" if path == start else "declared_import"

        for import_path in imports_for(path):
            resolved = resolve_import(root, path, import_path)
            if resolved is None:
                # Explicit relative imports are authoritative for temporary
                # target fixtures even when Foundry metadata is absent.
                direct = (path.parent / import_path).resolve()
                if direct.is_file():
                    resolved = (direct, "direct_declared_import")
            if resolved is not None:
                imported_path = resolved[0].resolve()
                if imported_path not in visited:
                    pending.append(imported_path)

    raise FileNotFoundError(
        f"Unable to resolve user-defined type {name} through imports from {start}"
    )
