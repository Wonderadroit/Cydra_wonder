from __future__ import annotations

from dataclasses import replace

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


def bind_experiment(
    hypothesis: Hypothesis,
    experiment: Experiment,
    *,
    target_function: str,
    planned_inputs: tuple[str, ...] = (),
) -> Experiment:
    """Bind an experiment to its hypothesis and concrete target without class knowledge.

    This is the generic handoff boundary between reasoning and execution. It does
    not inspect invariant IDs or vulnerability classes.
    """
    if experiment.hypothesis_id != hypothesis.hypothesis_id:
        raise ValueError(
            f"experiment/hypothesis mismatch: {experiment.hypothesis_id} != {hypothesis.hypothesis_id}"
        )
    if not target_function.strip():
        raise ValueError("experiment target function must not be empty")
    if planned_inputs and experiment.planned_inputs and tuple(planned_inputs) != tuple(experiment.planned_inputs):
        raise ValueError("conflicting experiment planned inputs")
    if experiment.target_function is not None and experiment.target_function != target_function:
        raise ValueError(
            f"experiment target mismatch: {experiment.target_function} != {target_function}"
        )
    return replace(
        experiment,
        target_function=target_function,
        planned_inputs=tuple(planned_inputs) if planned_inputs else experiment.planned_inputs,
    )
