from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from .models import ContractModel, FunctionModel
from .interface_resolver import resolve_named_type_source


@dataclass(frozen=True)
class NamespacedStateObservationPlan:
    """A verified observation plan for a simple ERC-7201 storage-pointer member."""

    state: str
    key_expression: str
    storage_slot: str
    value_type: str
    source: str

    def assertion_for(self, key_expression: str) -> str:
        """Render a read-only Foundry assertion for a bound mapping key."""
        return (
            f'assertEq(uint256(vm.load(address(target), '
            f'keccak256(abi.encode(uint256({key_expression}), '
            f'uint256({self.storage_slot}))))), 0, '
            f'"unverified prerequisite: $.{self.state}[{key_expression}]");'
        )

    @property
    def assertion(self) -> str:
        return self.assertion_for(self.key_expression)

_MAPPING_RE = re.compile(
    r"mapping\s*\(\s*(?P<key>[^=]+?)\s*=>\s*(?P<value>[^)]+?)\s*\)"
    r"\s+(?P<name>[A-Za-z_]\w*)\s*;"
)
_STRUCT_RE = re.compile(
    r"(?:///\s*|/\*\*?\s*\*?\s*)?@custom:storage-location\s+erc7201:[^\s\n]+\s*"
    r"(?:\*/\s*)?struct\s+(?P<name>[A-Za-z_]\w*)\s*\{(?P<body>.*?)\}",
    re.DOTALL,
)
_LOCATION_RE = re.compile(
    r"\b(?:bytes32\s+)?(?:private\s+)?constant\s+"
    r"(?P<name>[A-Za-z_]\w*Location)\s*=\s*(?P<value>0x[0-9A-Fa-f]{64})\s*;"
)
_FIELD_RE = re.compile(
    r"(?P<type>mapping\\s*\\([^;]+?\\)|[A-Za-z_]\\w*(?:\\s*\\[[^\\]]*\\])?)\\s+"
    r"(?P<name>[A-Za-z_]\\w*)\\s*;"
)
def _candidate_sources(contract: ContractModel) -> tuple[Path, ...]:
    """Follow compiler-model inheritance provenance to locate storage declarations."""
    source_path = Path(contract.source).resolve()
    project_root = next(
        (
            parent
            for parent in (source_path.parent, *source_path.parents)
            if (parent / "foundry.toml").exists()
        ),
        source_path.parent,
    )
    paths: list[Path] = [source_path]
    for inherited_name in contract.inherits:
        try:
            resolved, _ = resolve_named_type_source(
                project_root,
                source_path,
                inherited_name,
            )
        except (FileNotFoundError, ValueError, OSError, UnicodeError):
            continue
        candidate = Path(resolved)
        if not candidate.is_absolute():
            candidate = (project_root / candidate).resolve()
        if candidate not in paths:
            paths.append(candidate)
    return tuple(paths)

def _source(contract: ContractModel) -> str:
    try:
        return Path(contract.source).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""


def _whole_slot_field(type_name: str) -> bool:
    base = type_name.strip()
    if base.startswith("mapping") or "[" in base:
        return False
    if base == "address":
        return True
    return bool(re.fullmatch(r"(?:u?int|bytes)256", base))


def _struct_layout_offset(struct_body: str, target_name: str) -> int | None:
    """Return a conservative whole-slot offset for one struct member."""
    offset = 0
    for match in _FIELD_RE.finditer(struct_body):
        field_type = match.group("type")
        name = match.group("name")
        if name == target_name:
            return offset
        if not _whole_slot_field(field_type):
            return None
        offset += 1
    return None


def plan_namespaced_state_observation(
    contract: ContractModel,
    function: FunctionModel,
    predicate: str,
) -> NamespacedStateObservationPlan | None:
    """Plan read-only observation for $.mapping[key] backed by ERC-7201 storage.

    Only an ERC-7201 storage struct, a literal namespace base slot, and a
    mapping whose preceding members occupy complete storage slots are supported.
    """
    match = re.fullmatch(
        r"\$\.(?P<state>[A-Za-z_]\w*)\s*\[\s*(?P<key>[^\]]+)\s*\]",
        predicate.strip(),
    )
    if match is None:
        return None

    sources = [_source(contract)]
    for candidate in _candidate_sources(contract):
        if candidate == Path(contract.source).resolve():
            continue
        try:
            sources.append(candidate.read_text(encoding="utf-8"))
        except (OSError, UnicodeError):
            continue
    source = "\n".join(sources)


    state = match.group("state")
    key = match.group("key").strip()
    mapping_match = next(
        (item for item in _MAPPING_RE.finditer(source) if item.group("name") == state),
        None,
    )
    if mapping_match is None:
        return None

    struct_match = next(
        (item for item in _STRUCT_RE.finditer(source)
         if re.search(rf"\b{re.escape(state)}\s*;", item.group("body"))),
        None,
    )
    if struct_match is None:
        return None

    offset = _struct_layout_offset(struct_match.group("body"), state)
    if offset is None:
        return None

    location_candidates = list(_LOCATION_RE.finditer(source, struct_match.end()))
    location = location_candidates[0].group("value") if location_candidates else None

    if not location:
        return None

    try:
        base = int(location, 16)
        mapping_slot = base + offset
        if mapping_slot >= 1 << 256:
            return None
    except ValueError:
        return None

    return NamespacedStateObservationPlan(
        state=state,
        key_expression=key,
        storage_slot=hex(mapping_slot),
        value_type=mapping_match.group("value").strip(),
        source=f"{contract.source}:{function.line}",
    )
