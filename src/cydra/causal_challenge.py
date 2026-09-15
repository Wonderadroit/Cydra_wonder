"""Adversarial challenge gates for causal security reasoning.

A hypothesis is not ready for causal graduation merely because supporting evidence
exists. CYDRA should actively ask what competing explanation could also account for
the observation and whether an authorized observation can discriminate between them.
This module does not decide whether a vulnerability exists.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .hypotheses import Hypothesis
from .test_planning import ObservationOption, rank_observations


@dataclass(frozen=True)
class ChallengeAssessment:
    hypothesis_id: str
    challenged: bool
    competing_hypothesis_ids: tuple[str, ...]
    discriminating_observations: tuple[str, ...]
    recommended_observation: str | None
    rationale: str


def assess_hypothesis_challenge(
    hypothesis: Hypothesis,
    competing_hypotheses: Iterable[Hypothesis],
    observations: Iterable[ObservationOption],
) -> ChallengeAssessment:
    """Determine whether a hypothesis has an executable adversarial challenge.

    A challenge exists only when a distinct competing hypothesis predicts a
    different outcome for at least one available observation. Missing prediction
    data fails closed; it is never treated as evidence that the model was
    successfully challenged.
    """
    competitors = tuple(
        candidate for candidate in competing_hypotheses
        if candidate.hypothesis_id != hypothesis.hypothesis_id
    )
    options = tuple(observations)
    discriminating: list[str] = []

    for option in options:
        primary = hypothesis.planning_predictions.get(option.observation_id)
        if not primary:
            continue
        for competitor in competitors:
            alternative = competitor.planning_predictions.get(option.observation_id)
            if not alternative:
                continue
            primary_values = tuple(max(0.0, float(primary.get(state, 0.0))) for state in option.expected_states)
            alternative_values = tuple(max(0.0, float(alternative.get(state, 0.0))) for state in option.expected_states)
            if primary_values != alternative_values and sum(primary_values) > 0.0 and sum(alternative_values) > 0.0:
                discriminating.append(option.observation_id)
                break

    ranked = rank_observations((hypothesis, *competitors), options) if competitors else ()
    recommended = None
    if discriminating:
        candidates = [plan for plan in ranked if plan.observation_id in discriminating and plan.information_gain > 0.0]
        if candidates:
            recommended = candidates[0].observation_id

    challenged = bool(competitors and discriminating and recommended)
    if not competitors:
        rationale = "no distinct competing hypothesis is available; causal challenge is not established"
    elif not discriminating:
        rationale = "competing hypotheses exist, but no available observation has distinct predicted outcomes"
    elif recommended is None:
        rationale = "a potentially discriminating observation exists, but its information gain is not established"
    else:
        rationale = "a competing explanation has a predicted outcome difference and an information-gain-ranked observation can challenge it"

    return ChallengeAssessment(
        hypothesis.hypothesis_id,
        challenged,
        tuple(candidate.hypothesis_id for candidate in competitors),
        tuple(dict.fromkeys(discriminating)),
        recommended,
        rationale,
    )


def assess_all_hypothesis_challenges(
    hypotheses: Iterable[Hypothesis], observations: Iterable[ObservationOption]
) -> tuple[ChallengeAssessment, ...]:
    """Assess every hypothesis against the other hypotheses as competitors."""
    hs = tuple(hypotheses)
    return tuple(
        assess_hypothesis_challenge(hypothesis, (other for other in hs if other.hypothesis_id != hypothesis.hypothesis_id), observations)
        for hypothesis in hs
    )
