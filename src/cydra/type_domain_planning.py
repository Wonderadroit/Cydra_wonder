from __future__ import annotations
from .models import Experiment, Hypothesis

def plan_type_domain_experiment(hypothesis: Hypothesis) -> Experiment:
    return Experiment(
        experiment_id=f"X-{hypothesis.hypothesis_id}",
        hypothesis_id=hypothesis.hypothesis_id,
        action=f"call {hypothesis.target_function} with an identifier at the declared type boundary and compare reachability against a widened control",
        discriminates=("boundary identifier is accepted by the ABI", "underlying identifier/state domain remains reachable", "widened control changes only the parameter width"),
        cost=1.0,
    )
