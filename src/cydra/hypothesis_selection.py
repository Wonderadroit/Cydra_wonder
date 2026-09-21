from __future__ import annotations

from dataclasses import dataclass
import math

from .models import Experiment, Hypothesis, Invariant


@dataclass(frozen=True)
class HypothesisSelection:
    hypothesis: Hypothesis
    score: float


def _information_score(
    hypothesis: Hypothesis,
    invariant: Invariant,
    experiment: Experiment,
) -> float:
    evidence_weight = 1.0 + math.log1p(len(hypothesis.evidence_ids))
    discrimination_weight = max(1, len(experiment.discriminates))
    cost = max(experiment.cost, 0.1)
    return invariant.confidence * evidence_weight * discrimination_weight / cost


def select_next_hypothesis(
    hypotheses: tuple[Hypothesis, ...],
    invariants: tuple[Invariant, ...],
    experiments: tuple[Experiment, ...],
) -> HypothesisSelection:
    """Choose the next experiment without knowing or naming a vulnerability class."""
    if not hypotheses:
        raise ValueError("no hypotheses available")
    invariant_by_id = {item.invariant_id: item for item in invariants}
    experiment_by_id = {item.hypothesis_id: item for item in experiments}
    ranked = []
    for hypothesis in hypotheses:
        invariant = invariant_by_id.get(hypothesis.invariant_id)
        experiment = experiment_by_id.get(hypothesis.hypothesis_id)
        if invariant is None or experiment is None:
            continue
        ranked.append((
            _information_score(hypothesis, invariant, experiment),
            -experiment.cost,
            hypothesis.hypothesis_id,
            hypothesis,
        ))
    if not ranked:
        raise ValueError("no hypothesis has a bound invariant and experiment")
    ranked.sort(reverse=True)
    score, _, _, hypothesis = ranked[0]
    return HypothesisSelection(hypothesis, score)
