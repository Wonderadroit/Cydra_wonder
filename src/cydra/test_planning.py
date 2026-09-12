"""Information-gain planning for choosing the next authorized observation."""
from __future__ import annotations
from dataclasses import dataclass
from math import log2
from typing import Iterable
from .hypotheses import Hypothesis
@dataclass(frozen=True)
class ObservationOption:
    observation_id: str
    description: str
    expected_states: tuple[str, ...]
    cost: float = 1.0
    def __post_init__(self) -> None:
        if not self.observation_id.strip() or not self.description.strip(): raise ValueError("observation_id and description must not be empty")
        if not self.expected_states: raise ValueError("observation requires at least one expected state")
        if self.cost <= 0.0: raise ValueError("cost must be positive")
@dataclass(frozen=True)
class TestPlan:
    observation_id: str
    description: str
    information_gain: float
    cost: float
    utility: float
    rationale: str
def _entropy(probabilities: Iterable[float]) -> float: return -sum(p * log2(p) for p in probabilities if p > 0.0)
def rank_observations(hypotheses: Iterable[Hypothesis], observations: Iterable[ObservationOption]) -> tuple[TestPlan, ...]:
    hs = tuple(hypotheses)
    if not hs: return ()
    total = sum(h.belief if h.belief > 0 else 1.0 - h.belief for h in hs)
    if total <= 0.0: total = float(len(hs))
    prior = [max(h.belief, 1.0 - h.belief) / total for h in hs]
    prior_entropy = _entropy(prior)
    plans = []
    for option in observations:
        diversity = min(1.0, (len(set(option.expected_states)) - 1) / max(1, len(option.expected_states)))
        gain = prior_entropy * diversity; utility = gain / option.cost
        plans.append(TestPlan(option.observation_id, option.description, gain, option.cost, utility, "prior uncertainty weighted by distinguishable expected outcomes; no execution performed"))
    return tuple(sorted(plans, key=lambda p: (-p.utility, -p.information_gain, p.observation_id)))
