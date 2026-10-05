from __future__ import annotations

"""Technology-neutral adapter experiment bridge.

The hypothesis object here is the canonical evidence-driven hypothesis model.
"""

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .execution_adapter import AdapterObservation, AdapterRequest, ExecutionAdapter
from .hypotheses import Hypothesis


@dataclass(frozen=True)
class ExperimentAction:
    action_id: str
    operation: str
    inputs: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AdapterExperiment:
    experiment_id: str
    hypothesis_id: str
    target: str
    actions: tuple[ExperimentAction, ...]
    discriminates: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.experiment_id.strip(): raise ValueError("experiment_id must not be empty")
        if not self.hypothesis_id.strip(): raise ValueError("hypothesis_id must not be empty")
        if not self.target.strip(): raise ValueError("target must not be empty")
        if not self.actions: raise ValueError("adapter experiment requires at least one action")
        if not self.discriminates: raise ValueError("adapter experiment must discriminate at least one outcome")


def bind_adapter_experiment(hypothesis: Hypothesis, *, target: str, actions: Sequence[ExperimentAction], discriminates: Sequence[str]) -> AdapterExperiment:
    if not actions: raise ValueError("actions must not be empty")
    if not discriminates: raise ValueError("discriminates must not be empty")
    return AdapterExperiment(
        experiment_id=f"X-{hypothesis.hypothesis_id}",
        hypothesis_id=hypothesis.hypothesis_id,
        target=target,
        actions=tuple(actions),
        discriminates=tuple(discriminates),
    )


def execute_adapter_experiment(experiment: AdapterExperiment, adapter: ExecutionAdapter) -> tuple[AdapterObservation, ...]:
    observations: list[AdapterObservation] = []
    for action in experiment.actions:
        observation = adapter.execute(AdapterRequest(
            action_id=action.action_id,
            operation=action.operation,
            inputs=action.inputs,
            metadata={**dict(action.metadata), "experiment_id": experiment.experiment_id,
                      "hypothesis_id": experiment.hypothesis_id, "target": experiment.target},
        ))
        observations.append(observation)
        if observation.status.value != "executed":
            break
    return tuple(observations)
