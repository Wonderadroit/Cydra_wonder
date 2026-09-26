from __future__ import annotations

from pathlib import Path
import re


_PROXY_MARKER = "_disableInitializers()"
_INITIALIZABLE_MARKER = "Initializable"
_MAX_IMPORT_DEPTH = 16


def _constructor_disables_initializers(source: str) -> bool:
    for match in re.finditer(r"\bconstructor\s*\([^)]*\)[^{;]*\{", source, re.MULTILINE):
        body = source[match.end():]
        depth = 1
        for index, char in enumerate(body):
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    if re.search(r"\b_disableInitializers\s*\(\s*\)", body[:index]):
                        return True
                    break
    return False


def _resolve_import(source_path: Path, import_path: str) -> Path | None:
    raw = Path(import_path)
    if raw.is_absolute() and raw.exists():
        return raw
    if import_path.startswith("."):
        candidate = (source_path.parent / raw).resolve()
        return candidate if candidate.exists() else None

    for ancestor in (source_path.parent, *source_path.parents):
        direct = ancestor / raw
        if direct.exists():
            return direct.resolve()

        lib = ancestor / "lib"
        node_modules = ancestor / "node_modules"
        upgradeable_prefix = "@openzeppelin/contracts-upgradeable/"
        if import_path.startswith(upgradeable_prefix):
            relative = import_path[len(upgradeable_prefix):]
            for base in (lib / "openzeppelin-contracts-upgradeable" / "contracts", node_modules / "@openzeppelin" / "contracts-upgradeable"):
                candidate = base / relative
                if candidate.exists():
                    return candidate.resolve()
        contracts_prefix = "@openzeppelin/contracts/"
        if import_path.startswith(contracts_prefix):
            relative = import_path[len(contracts_prefix):]
            for base in (lib / "openzeppelin-contracts" / "contracts", node_modules / "@openzeppelin" / "contracts"):
                candidate = base / relative
                if candidate.exists():
                    return candidate.resolve()
    return None


def _reachable_sources(root: Path) -> tuple[Path, ...]:
    seen: set[Path] = set()
    queue: list[tuple[Path, int]] = [(root.resolve(), 0)]
    ordered: list[Path] = []
    while queue:
        current, depth = queue.pop(0)
        if current in seen or depth > _MAX_IMPORT_DEPTH or not current.exists():
            continue
        seen.add(current)
        ordered.append(current)
        try:
            source = current.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        for import_path in re.findall(r'\bimport\s+(?:[^"\']+\s+from\s+)?["\']([^"\']+)["\']\s*;', source):
            resolved = _resolve_import(current, import_path)
            if resolved is not None and resolved not in seen:
                queue.append((resolved, depth + 1))
    return tuple(ordered)


def _contract_inheritance_graph(sources: tuple[Path, ...]) -> dict[str, tuple[Path, tuple[str, ...], str]]:
    """Build only the contract inheritance graph from the reachable source set."""
    graph: dict[str, tuple[Path, tuple[str, ...], str]] = {}
    declaration = re.compile(r"\b(?:abstract\s+)?contract\s+(?P<name>[A-Za-z_]\w*)(?:\s+is\s+(?P<bases>[^\{]+))?\s*\{", re.MULTILINE)
    for path in sources:
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        for match in declaration.finditer(source):
            body = source[match.end():]
            depth = 1
            end = len(body)
            for index, char in enumerate(body):
                if char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth == 0:
                        end = index
                        break
            bases: list[str] = []
            for raw_base in (match.group("bases") or "").split(","):
                base_match = re.match(r"\s*([A-Za-z_]\w*)", raw_base)
                if base_match:
                    bases.append(base_match.group(1))
            graph[match.group("name")] = (path, tuple(bases), body[:end])
    return graph


def requires_proxy_initialization(contract_source: str | Path) -> bool:
    """Return true when the target contract or an inherited base disables implementation initialization."""
    if isinstance(contract_source, Path):
        try:
            sources = _reachable_sources(contract_source)
        except (OSError, RuntimeError):
            return False
        graph = _contract_inheritance_graph(sources)
        roots = [name for name, (path, _, _) in graph.items() if path.resolve() == contract_source.resolve()]
        queue = list(roots)
        seen: set[str] = set()
        while queue:
            name = queue.pop(0)
            if name in seen:
                continue
            seen.add(name)
            entry = graph.get(name)
            if entry is None:
                continue
            _path, bases, body = entry
            if _constructor_disables_initializers(body):
                return True
            queue.extend(base for base in bases if base not in seen)
        return False

    if _constructor_disables_initializers(contract_source):
        return True
    return _INITIALIZABLE_MARKER in contract_source and _PROXY_MARKER in contract_source


def supports_initializer_disable(contract_source: str | Path) -> bool:
    """Return whether the reachable target topology exposes _disableInitializers()."""
    if isinstance(contract_source, Path):
        try:
            sources = _reachable_sources(contract_source)
        except (OSError, RuntimeError):
            return False
        for path in sources:
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                continue
            if "_disableInitializers(" in text:
                return True
        return False
    return bool("_disableInitializers(" in contract_source)


def adapt_generated_initialization_for_proxy(source: str, target_type: str) -> str:
    """Route initialization through a minimal delegate proxy while preserving msg.sender.

    The implementation contract remains the real target. The proxy owns the separate
    storage used by OpenZeppelin Initializable, so a constructor that calls
    _disableInitializers() does not make the intended proxy deployment untestable.
    """
    if "contract CydraDelegateProxy" in source:
        return source

    declaration = f"    {target_type} internal implementation;\n"
    if declaration not in source:
        anchor = f"    {target_type} internal target;\n"
        if anchor not in source:
            raise ValueError("generated initialization test has no target declaration")
        source = source.replace(anchor, anchor + declaration, 1)

    pattern = re.compile(rf"target\s*=\s*new\s+{re.escape(target_type)}\(([^;]*)\);", re.MULTILINE)
    match = pattern.search(source)
    if match is None:
        raise ValueError("generated initialization test does not contain the expected direct target deployment")
    implementation_args = match.group(1)
    assignment = (
        f"implementation = new {target_type}({implementation_args});\n"
        "        CydraDelegateProxy proxy = new CydraDelegateProxy(address(implementation));\n"
        f"        target = {target_type}(payable(address(proxy)));"
    )
    source = pattern.sub(assignment, source, count=1)

    proxy = '''

contract CydraDelegateProxy {
    address public immutable implementation;

    constructor(address implementation_) {
        require(implementation_ != address(0), "proxy implementation is zero");
        implementation = implementation_;
    }

    fallback() external payable {
        address implementation_ = implementation;
        assembly {
            calldatacopy(0, 0, calldatasize())
            let ok := delegatecall(gas(), implementation_, 0, calldatasize(), 0, 0)
            returndatacopy(0, 0, returndatasize())
            switch ok
            case 0 { revert(0, returndatasize()) }
            default { return(0, returndatasize()) }
        }
    }

    receive() external payable {}
}
'''
    marker = "contract CydraInitializationInvariantTest is Test {"
    if marker not in source:
        raise ValueError("generated initialization test has no expected test contract")
    return source.replace(marker, proxy + "\n" + marker, 1)
