from __future__ import annotations

from .models import Experiment, Hypothesis


def plan_signed_metadata_experiment(hypothesis: Hypothesis) -> Experiment:
    return Experiment(
        experiment_id=f"X-{hypothesis.hypothesis_id}",
        hypothesis_id=hypothesis.hypothesis_id,
        action=(
            f"Create one valid signed authorization for {hypothesis.target_function}, "
            "let its metadata become invalid, then change only the metadata while "
            "keeping the signed bytes unchanged and compare signature validation."
        ),
        discriminates=(
            "metadata is authenticated by the signer and changing it invalidates the authorization",
            "metadata can be changed without invalidating the authorization",
        ),
        cost=1.0,
        planned_inputs=(
            "one valid signed authorization containing auxiliary validity metadata",
            "same signature bytes with only the metadata changed",
            "same signer and base authorization payload",
        ),
    )
