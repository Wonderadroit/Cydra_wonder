from __future__ import annotations

import re
from pathlib import Path

from .models import ContractModel, FunctionModel


_CONTRACT_RE = re.compile(r"\bcontract\s+(\w+)")
_FUNCTION_RE = re.compile(
    r"\bfunction\s+(\w+)\s*\([^)]*\)\s*([^\{;]*)\{", re.MULTILINE
)


def _line_number(source: str, offset: int) -> int:
    return source.count("\n", 0, offset) + 1


def _body(source: str, opening: int) -> str:
    depth = 0
    for i in range(opening, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[opening + 1 : i]
    return source[opening + 1 :]


def parse_solidity(path: str | Path) -> tuple[ContractModel, ...]:
    """Minimal deterministic model extractor used before compiler integration.

    It intentionally extracts only facts needed by the first CYDRA milestone.
    It is not a Solidity parser and must not be treated as one.
    """
    path = Path(path)
    source = path.read_text(encoding="utf-8")
    contracts: list[ContractModel] = []

    for contract_match in _CONTRACT_RE.finditer(source):
        contract_name = contract_match.group(1)
        contract_start = contract_match.end()
        next_contract = _CONTRACT_RE.search(source, contract_start)
        contract_source = source[contract_start : next_contract.start() if next_contract else len(source)]
        functions: list[FunctionModel] = []

        for match in _FUNCTION_RE.finditer(contract_source):
            name = match.group(1)
            signature_tail = match.group(2)
            opening = match.end() - 1
            body = _body(contract_source, opening)
            modifiers = tuple(
                token
                for token in re.findall(r"\b[A-Za-z_]\w*\b", signature_tail)
                if token in {"onlyGov", "onlyOwner", "onlyAdmin", "onlyKeeper", "onlyWhitelisted"}
            )
            visibility_match = re.search(r"\b(public|external|internal|private)\b", signature_tail)
            visibility = visibility_match.group(1) if visibility_match else "unspecified"
            writes = tuple(sorted(set(re.findall(r"\b(\w+)\s*(?:\[[^]]+\])?\s*=", body))))
            external_calls = tuple(sorted(set(re.findall(r"\b(\w+)\.(\w+)\s*\(", body))))
            functions.append(
                FunctionModel(
                    name=name,
                    visibility=visibility,
                    modifiers=modifiers,
                    writes=writes,
                    external_calls=external_calls,
                    line=_line_number(source, contract_start + match.start()),
                )
            )

        contracts.append(
            ContractModel(name=contract_name, source=str(path), functions=tuple(functions))
        )

    return tuple(contracts)
