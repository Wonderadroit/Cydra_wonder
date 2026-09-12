from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class SourceFunction:
    name: str
    file: str
    line: int | None = None
    visibility: str | None = None
    modifiers: tuple[str, ...] = ()
    external_calls: tuple[str, ...] = ()


@dataclass(frozen=True)
class SourceContract:
    name: str
    file: str
    functions: tuple[SourceFunction, ...] = ()
    state_variables: tuple[str, ...] = ()


@dataclass
class RepositoryModel:
    root: str
    contracts: list[SourceContract] = field(default_factory=list)

    @property
    def files(self) -> tuple[str, ...]:
        return tuple(sorted({c.file for c in self.contracts}))


def discover_source_files(root: str | Path, extensions: Iterable[str] = (".sol",)) -> list[Path]:
    """Return deterministic source-file inventory; parsing remains a separate concern."""
    base = Path(root)
    allowed = {e if e.startswith(".") else f".{e}" for e in extensions}
    if not base.exists():
        raise FileNotFoundError(base)
    return sorted(p for p in base.rglob("*") if p.is_file() and p.suffix in allowed)
