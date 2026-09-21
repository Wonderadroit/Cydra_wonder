"""Generic evidence-driven hypothesis research loop.

This module owns only the orchestration boundary: select a hypothesis, execute
its bound experiment, record the observed status, and feed that observation into
the next selection. It knows nothing about vulnerability classes, target names,
or benchmark answers.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Generic, TypeVar

from .hypothesis_selection import HypothesisSelection, select_next_hypothesis
from .impact_priority import FindingCollection
from .models import Experiment, Hypothesis, Invariant

Observation = TypeVar("Observation")

@dataclass(frozen=True)
class ResearchRound(Generic[Observation]):
    """One auditable selection/execution observation."""
    selection: HypothesisSelection
    observation: Observation
    status: str

@dataclass(frozen=True)
class ResearchLoopResult(Generic[Observation]):
    """The complete sequence of selections and measured observations."""
    rounds: tuple[ResearchRound[Observation], ...]
    findings: FindingCollection | None = None

def run_research_loop(
    hypotheses: tuple[Hypothesis, ...],
    invariants: tuple[Invariant, ...],
    experiments: tuple[Experiment, ...],
    *,
    execute: Callable[[Hypothesis, Experiment], Observation],
    status_of: Callable[[Observation], str],
    stop_when: Callable[[Observation], bool] | None = None,
    finding_of: Callable[[Observation], object | None] | None = None,
    finding_target: str = "",
    max_rounds: int = 2,
) -> ResearchLoopResult[Observation]:
    """Run class-neutral select -> execute -> observe -> reselect cycles."""
    if max_rounds < 1:
        raise ValueError("max_rounds must be at least 1")
    observed_statuses: dict[str, str] = {}
    rounds: list[ResearchRound[Observation]] = []
    findings = FindingCollection(finding_target) if finding_of is not None else None
    experiment_by_id = {item.hypothesis_id: item for item in experiments}
    for _ in range(max_rounds):
        selection = select_next_hypothesis(
            hypotheses, invariants, experiments, observed_statuses=observed_statuses
        )
        experiment = experiment_by_id.get(selection.hypothesis.hypothesis_id)
        if experiment is None:
            raise ValueError("selected hypothesis has no bound experiment: " + selection.hypothesis.hypothesis_id)
        observation = execute(selection.hypothesis, experiment)
        status = status_of(observation)
        if not status:
            raise ValueError("observation status must be non-empty")
        observed_statuses[selection.hypothesis.hypothesis_id] = status
        rounds.append(ResearchRound(selection, observation, status))
        if finding_of is not None:
            finding = finding_of(observation)
            if finding is not None:
                if findings is None:
                    raise AssertionError("finding collection was not initialized")
                findings = findings.add(finding)
        if stop_when is not None and stop_when(observation):
            break
    return ResearchLoopResult(tuple(rounds), findings)
