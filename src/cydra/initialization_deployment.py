"""Generic deployment-surface evidence for initialization causal verification.

This module deliberately stops at evidence extraction. A proxy-looking contract is
not treated as proof that a particular implementation is reachable through it.
Only explicit source relationships are emitted, so the later runtime layer can
require a concrete deployment route before promoting direct implementation
mutation into a security claim.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable


@dataclass(frozen=True)
class DeploymentEvidence:
    evidence_id: str
    kind: str
    claim: str
    source: str
    location: str
    proxy_contract: str | None = None
    implementation_contract: str | None = None
    deployment_contract: str | None = None


@dataclass(frozen=True)
class DeploymentSurface:
    evidence: tuple[DeploymentEvidence, ...]

    @property
    def proxy_contracts(self) -> tuple[str, ...]:
        return tuple(sorted({item.proxy_contract for item in self.evidence if item.proxy_contract}))

    @property
    def implementation_links(self) -> tuple[DeploymentEvidence, ...]:
        return tuple(item for item in self.evidence if item.kind == "implementation_link")

    @property
    def initializer_forwarding(self) -> tuple[DeploymentEvidence, ...]:
        return tuple(item for item in self.evidence if item.kind == "initializer_forwarding")

    def linked(self, implementation_contract: str) -> tuple[DeploymentEvidence, ...]:
        return tuple(item for item in self.implementation_links if item.implementation_contract == implementation_contract)

    def has_explicit_route(self, implementation_contract: str) -> bool:
        """Return true only when the source explicitly links the implementation to a
        proxy that forwards arbitrary calldata with delegatecall.

        This is reachability evidence, not runtime proof that the proxy is deployed
        on a live system or that the initializer is still unclaimed.
        """
        links = self.linked(implementation_contract)
        proxy_ids = {item.proxy_contract for item in self.evidence if item.kind == "proxy_delegatecall"}
        return bool(links) and any(item.proxy_contract in proxy_ids for item in links)


_CONTRACT_RE = re.compile(r"\b(?:abstract\s+)?contract\s+(?P<name>[A-Za-z_]\w*)")
_PROXY_DECL_RE = re.compile(r"\bcontract\s+(?P<name>[A-Za-z_]\w*Proxy\w*)\b")
_NEW_PROXY_RE = re.compile(
    r"\bnew\s+(?P<proxy>[A-Za-z_]\w*Proxy\w*)"
    r"(?:\s*\{[^}]*\})?\s*\(\s*(?P<argument>[^,)]*)",
    re.MULTILINE,
)
_DELEGATECALL_RE = re.compile(r"\bdelegatecall\s*\(")
_INIT_FORWARD_RE = re.compile(
    r"\b(?P<target>[A-Za-z_]\w*)\.delegatecall\s*\(\s*(?P<data>[^)]*"
    r"\b(?:data|init|initializer|calldata)\b[^)]*)\)",
    re.MULTILINE | re.IGNORECASE,
)


def _contract_name_for_offset(source: str, offset: int) -> str | None:
    matches = list(_CONTRACT_RE.finditer(source, 0, offset))
    return matches[-1].group("name") if matches else None


def _implementation_contract_from_expression(expression: str, known_contracts: set[str]) -> str | None:
    identifiers = re.findall(r"\b[A-Za-z_]\w*\b", expression)
    for identifier in reversed(identifiers):
        if identifier in known_contracts:
            return identifier
    return None


def inspect_deployment_surface(
    root: str | Path,
    *,
    source_files: Iterable[str | Path] | None = None,
) -> DeploymentSurface:
    """Extract explicit proxy/implementation relationships from an in-scope tree."""
    base = Path(root).resolve()
    paths = (
        tuple(Path(item).resolve() for item in source_files)
        if source_files is not None
        else tuple(sorted(base.rglob("*.sol"), key=lambda item: item.as_posix()))
    )
    sources: dict[Path, str] = {}
    known_contracts: set[str] = set()
    for path in paths:
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        sources[path] = source
        known_contracts.update(match.group("name") for match in _CONTRACT_RE.finditer(source))

    evidence: list[DeploymentEvidence] = []
    for path, source in sources.items():
        relative = path.relative_to(base).as_posix()
        proxy_names = {match.group("name") for match in _PROXY_DECL_RE.finditer(source)}
        delegatecall_match = _DELEGATECALL_RE.search(source)
        if delegatecall_match and proxy_names:
            for proxy in sorted(proxy_names):
                evidence.append(DeploymentEvidence(
                    evidence_id=f"E-DEPLOY-PROXY-{relative}-{proxy}",
                    kind="proxy_delegatecall",
                    claim=f"{proxy} contains an explicit delegatecall forwarding surface.",
                    source=relative,
                    location=f"line {source.count(chr(10), 0, delegatecall_match.start()) + 1}",
                    proxy_contract=proxy,
                ))

        for match in _NEW_PROXY_RE.finditer(source):
            proxy = match.group("proxy")
            implementation = _implementation_contract_from_expression(match.group("argument"), known_contracts)
            if implementation is None:
                continue
            evidence.append(DeploymentEvidence(
                evidence_id=f"E-DEPLOY-LINK-{relative}-{match.start()}",
                kind="implementation_link",
                claim=f"{proxy} is explicitly deployed with {implementation} as an implementation argument.",
                source=relative,
                location=f"line {source.count(chr(10), 0, match.start()) + 1}",
                proxy_contract=proxy,
                implementation_contract=implementation,
                deployment_contract=_contract_name_for_offset(source, match.start()),
            ))

        for match in _INIT_FORWARD_RE.finditer(source):
            contract = _contract_name_for_offset(source, match.start())
            if contract is None or contract not in proxy_names:
                continue
            evidence.append(DeploymentEvidence(
                evidence_id=f"E-DEPLOY-INIT-FORWARD-{relative}-{match.start()}",
                kind="initializer_forwarding",
                claim=f"{contract} forwards caller-supplied initialization data through delegatecall.",
                source=relative,
                location=f"line {source.count(chr(10), 0, match.start()) + 1}",
                proxy_contract=contract,
            ))

    return DeploymentSurface(tuple(sorted(evidence, key=lambda item: item.evidence_id)))
