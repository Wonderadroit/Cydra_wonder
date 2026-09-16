from __future__ import annotations

from .models import Experiment, Hypothesis


def plan_experiment(
    hypothesis: Hypothesis,
    action: str,
    discriminates: tuple[str, ...],
    cost: float,
) -> Experiment:
    """Construct the canonical experiment envelope without knowing its invariant class.

    Class-specific reasoning decides what the action means and what outcomes it
    discriminates. This layer only preserves the causal link from hypothesis to
    executable experiment and performs generic input validation.
    """
    if not action.strip():
        raise ValueError("experiment action must not be empty")
    if not discriminates:
        raise ValueError("experiment must discriminate at least one outcome")
    if cost < 0:
        raise ValueError("experiment cost must be non-negative")
    return Experiment(
        experiment_id=f"X-{hypothesis.hypothesis_id}",
        hypothesis_id=hypothesis.hypothesis_id,
        action=action,
        discriminates=tuple(discriminates),
        cost=cost,
    )
