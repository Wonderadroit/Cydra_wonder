from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .models import Hypothesis, Invariant

if TYPE_CHECKING:
    from .ast_dataflow import SemanticRelationshipEvidence
    from .models import ContractModel


@dataclass(frozen=True)
class ReasoningContribution:
    """Class-neutral output shared by reasoning surfaces and orchestration.

    Keeping this transport type outside the pipeline prevents reasoning surfaces
    from importing orchestration code and makes them independently reusable in
    blind discovery, benchmarks, and future adapters.
    """

    invariants: tuple[Invariant, ...]
    hypotheses: tuple[Hypothesis, ...]


ReasoningSurface = object
