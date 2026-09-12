"""Information-gain planning bridge; planning never executes tests."""
from __future__ import annotations

from .hypotheses import Hypothesis
from .test_planning import ObservationOption, TestPlan, rank_observations


def rank_next_observations(
    hypotheses: tuple[Hypothesis, ...],
    observations: tuple[ObservationOption, ...],
) -> tuple[TestPlan, ...]:
    return rank_observations(hypotheses, observations)
