from __future__ import annotations

"""Safe replay execution for Web2 causal verification.

Automatic causal replay is restricted to read-like HTTP methods. Mutating
requests require an explicit replay-safe contract and are otherwise refused.
"""

from dataclasses import dataclass

from .adapter_experiment import AdapterExperiment, ExperimentAction, execute_adapter_experiment
from .execution_adapter import AdapterObservation, AdapterStatus, ExecutionAdapter


@dataclass(frozen=True)
class ReplayResult:
    owner: tuple[AdapterObservation, ...]
    comparison: tuple[AdapterObservation, ...]


def replay_authorization_experiment(
    experiment: AdapterExperiment,
    adapter: ExecutionAdapter,
    *,
    replay_safe: bool = False,
) -> ReplayResult:
    if not replay_safe:
        unsafe = [
            action.inputs.get("method", "GET").upper()
            for action in experiment.actions
            if str(action.inputs.get("method", "GET")).upper() not in {"GET", "HEAD", "OPTIONS"}
        ]
        if unsafe:
            return ReplayResult(
                owner=(AdapterObservation(AdapterStatus.UNAVAILABLE, "replay", error="automatic replay refused for mutating HTTP operation"),),
                comparison=(),
            )

    first = execute_adapter_experiment(experiment, adapter)
    second = execute_adapter_experiment(experiment, adapter)

    if len(first) < 2 or len(second) < 2:
        return ReplayResult(first, second)

    return ReplayResult(
        owner=(first[0], second[0]),
        comparison=(first[1], second[1]),
    )
