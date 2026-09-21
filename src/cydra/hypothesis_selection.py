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
    excluded_hypothesis_ids: tuple[str, ...] = (),
    observed_statuses: dict[str, str] | None = None,
) -> HypothesisSelection:
    """Choose the next experiment without knowing or naming a vulnerability class."""
    if not hypotheses:
        raise ValueError("no hypotheses available")
    excluded = set(excluded_hypothesis_ids)
    # Only an explicit contradiction removes a candidate. Ambiguous and
    # non-terminal observations remain available for further information gain.
    observed = observed_statuses or {}
    # Classifiers may use "rejected" for a hypothesis disproved by an
    # executable observation. Normalize that terminal classifier outcome to the
    # canonical contradiction state; ambiguous/not-confirmed outcomes remain
    # eligible for further information-gain testing.
    contradictory_statuses = {"contradicted", "rejected"}
    excluded.update(hid for hid, status in observed.items() if status in contradictory_statuses)
    invariant_by_id = {item.invariant_id: item for item in invariants}
    experiment_by_id = {item.hypothesis_id: item for item in experiments}
    ranked = []
    for hypothesis in hypotheses:
        if hypothesis.hypothesis_id in excluded:
            continue
        invariant = invariant_by_id.get(hypothesis.invariant_id)
        experiment = experiment_by_id.get(hypothesis.hypothesis_id)
        if invariant is None or experiment is None:
            continue
        score = _information_score(hypothesis, invariant, experiment)
        # A non-terminal observation is evidence, not disqualification. Keep the
        # hypothesis eligible, but prefer an untested candidate when it offers
        # comparable information gain. This prevents the loop from spending every
        # round repeating the same unresolved experiment.
        status = observed.get(hypothesis.hypothesis_id)
        if status is not None:
            score *= 0.5
        ranked.append((
            score,
            -experiment.cost,
            hypothesis.hypothesis_id,
            hypothesis,
        ))
    if not ranked:
        if excluded:
            raise ValueError("no non-excluded hypothesis has a bound invariant and experiment")
        raise ValueError("no hypothesis has a bound invariant and experiment")
    ranked.sort(reverse=True)
    score, _, _, hypothesis = ranked[0]
    return HypothesisSelection(hypothesis, score)
