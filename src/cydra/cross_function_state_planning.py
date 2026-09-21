from __future__ import annotations

from .models import Experiment, Hypothesis


def plan_cross_function_state_experiment(hypothesis: Hypothesis) -> Experiment:
    """Plan a conservative observation for a shared-state transition hypothesis.

    The state reasoning surface intentionally does not encode a vulnerability
    primitive. It asks whether invoking the selected transition can produce a
    state observation inconsistent with the modeled invariant. Related functions
    remain provenance context; the generic runner decides whether the target can
    render and execute the experiment.
    """
    peers = ", ".join(hypothesis.related_functions) or "another externally callable transition"
    return Experiment(
        experiment_id="X-" + hypothesis.hypothesis_id,
        hypothesis_id=hypothesis.hypothesis_id,
        action=hypothesis.target_function,
        discriminates=(
            f"{hypothesis.target_function} preserves the modeled state consistency when composed with {peers}",
            f"{hypothesis.target_function} produces an observable state inconsistency under the modeled transition",
        ),
        cost=1.0,
        target_function=hypothesis.target_function,
        steps=(),
    )
