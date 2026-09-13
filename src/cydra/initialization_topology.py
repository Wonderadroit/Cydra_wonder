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
        upgradeable_prefix = "@openzeppelin/contracts-upgradeable/"
        if import_path.startswith(upgradeable_prefix):
            candidate = lib / "openzeppelin-contracts-upgradeable" / "contracts" / import_path[len(upgradeable_prefix):]
            if candidate.exists():
                return candidate.resolve()
        contracts_prefix = "@openzeppelin/contracts/"
        if import_path.startswith(contracts_prefix):
            candidate = lib / "openzeppelin-contracts" / "contracts" / import_path[len(contracts_prefix):]
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


def requires_proxy_initialization(contract_source: str | Path) -> bool:
    """Return true when the target's reachable initialization topology disables direct initialization."""
    if isinstance(contract_source, Path):
        try:
            sources = _reachable_sources(contract_source)
        except (OSError, RuntimeError):
            return False
        for path in sources:
            try:
                if _constructor_disables_initializers(path.read_text(encoding="utf-8")):
                    return True
            except (OSError, UnicodeError):
                continue
        return False

    if _constructor_disables_initializers(contract_source):
        return True
    return _INITIALIZABLE_MARKER in contract_source and _PROXY_MARKER in contract_source


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
        f"        target = {target_type}(address(proxy));"
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
