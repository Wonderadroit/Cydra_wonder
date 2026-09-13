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

def _entropy(probabilities: Iterable[float]) -> float:
    return -sum(p * log2(p) for p in probabilities if p > 0.0)

def _predicted_distribution(hypothesis: Hypothesis, option: ObservationOption) -> dict[str, float] | None:
    raw = hypothesis.planning_predictions.get(option.observation_id)
    if not raw:
        return None
    values = {state: max(0.0, float(raw.get(state, 0.0))) for state in option.expected_states}
    total = sum(values.values())
    if total <= 0.0:
        return None
    return {state: value / total for state, value in values.items()}

def _prediction_information_gain(hypotheses: tuple[Hypothesis, ...], option: ObservationOption, prior: list[float], prior_entropy: float) -> float | None:
    predictions = [_predicted_distribution(hypothesis, option) for hypothesis in hypotheses]
    if any(prediction is None for prediction in predictions):
        return None
    outcome_probability = {state: 0.0 for state in option.expected_states}
    for weight, prediction in zip(prior, predictions):
        for state, probability in prediction.items():
            outcome_probability[state] += weight * probability

    expected_posterior_entropy = 0.0
    for state, probability in outcome_probability.items():
        if probability <= 0.0:
            continue
        posterior = [
            weight * prediction[state] / probability
            for weight, prediction in zip(prior, predictions)
        ]
        expected_posterior_entropy += probability * _entropy(posterior)
    return max(0.0, prior_entropy - expected_posterior_entropy)

def rank_observations(hypotheses: Iterable[Hypothesis], observations: Iterable[ObservationOption]) -> tuple[TestPlan, ...]:
    hs = tuple(hypotheses)
    if not hs: return ()
    weights = [h.belief for h in hs]
    total = sum(weights)
    if total <= 0.0:
        prior = [1.0 / len(hs)] * len(hs)
    else:
        prior = [weight / total for weight in weights]
    prior_entropy = _entropy(prior)
    plans = []
    for option in observations:
        prediction_gain = _prediction_information_gain(hs, option, prior, prior_entropy)
        if prediction_gain is None:
            gain = 0.0
            rationale = "hypothesis-specific outcome predictions are incomplete; information gain conservatively set to zero; no execution performed"
        else:
            gain = prediction_gain
            rationale = "expected posterior entropy from hypothesis-specific outcome predictions; no execution performed"
        utility = gain / option.cost
        plans.append(TestPlan(option.observation_id, option.description, gain, option.cost, utility, rationale))
    return tuple(sorted(plans, key=lambda p: (-p.utility, -p.information_gain, p.observation_id)))
