from __future__ import annotations

from .models import Experiment, Hypothesis


def plan_resource_authorization_experiment(hypothesis: Hypothesis) -> Experiment:
    return Experiment(
        experiment_id=f"X-{hypothesis.hypothesis_id}",
        hypothesis_id=hypothesis.hypothesis_id,
        action=f"execute {hypothesis.target_function} from an unrelated caller after resource approval and compare the resource/asset transition with an owner-bound control",
        discriminates=(
            "caller is bound to the current resource owner or explicit delegate",
            "approved resource can still be mutated by an unrelated caller",
            "owner-bound control preserves the same resource state and authorization boundary",
        ),
        cost=1.0,
    )
