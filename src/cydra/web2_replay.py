from __future__ import annotations
from dataclasses import dataclass
from .adapter_experiment import AdapterExperiment, execute_adapter_experiment
from .execution_adapter import AdapterObservation, AdapterStatus, ExecutionAdapter

@dataclass(frozen=True)
class ReplayResult:
    owner: tuple[AdapterObservation,...]
    comparison: tuple[AdapterObservation,...]

def replay_authorization_experiment(experiment: AdapterExperiment, adapter: ExecutionAdapter, *, replay_safe: bool=False) -> ReplayResult:
    if not replay_safe:
        unsafe=[str(a.inputs.get("method","GET")).upper() for a in experiment.actions if str(a.inputs.get("method","GET")).upper() not in {"GET","HEAD","OPTIONS"}]
        if unsafe:
            return ReplayResult((AdapterObservation(AdapterStatus.UNAVAILABLE,"replay",error="automatic replay refused for mutating HTTP operation"),), ())
    first=execute_adapter_experiment(experiment,adapter); second=execute_adapter_experiment(experiment,adapter)
    if len(first)<2 or len(second)<2: return ReplayResult(first,second)
    return ReplayResult((first[0],second[0]),(first[1],second[1]))
