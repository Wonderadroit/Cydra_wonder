from __future__ import annotations

from dataclasses import dataclass

from cydra.adapter_experiment import (
    ExperimentAction,
    bind_adapter_experiment,
    execute_adapter_experiment,
)
from cydra.execution_adapter import (
    AdapterCapability,
    AdapterObservation,
    AdapterRequest,
    AdapterStatus,
)
from cydra.hypotheses import Hypothesis


@dataclass
class RecordingAdapter:
    adapter_id: str = "test"
    calls: list[AdapterRequest] = None

    def __post_init__(self) -> None:
        self.calls = [] if self.calls is None else self.calls

    def capabilities(self):
        return (AdapterCapability("TEST", True),)

    def execute(self, request: AdapterRequest) -> AdapterObservation:
        self.calls.append(request)
        return AdapterObservation(AdapterStatus.EXECUTED, request.action_id, {"ok": True})


@dataclass
class BlockingAdapter:
    adapter_id: str = "blocked"

    def capabilities(self):
        return ()

    def execute(self, request: AdapterRequest) -> AdapterObservation:
        return AdapterObservation(AdapterStatus.UNAVAILABLE, request.action_id, error="missing capability")


def hypothesis() -> Hypothesis:
    return Hypothesis(
        hypothesis_id="H-WEB2-AUTH-1",
        statement="identity B must not access identity A's private resource",
        invariant_id="I-AUTH",
        target_function="resource",
        attacker_capability="authenticated second identity",
        expected_impact="private data disclosure",
    )


def test_experiment_binds_hypothesis_and_executes_in_order() -> None:
    experiment = bind_adapter_experiment(
        hypothesis(),
        target="https://authorized.example",
        actions=(
            ExperimentAction("a1", "http_request", {"method": "GET", "path": "/a"}),
            ExperimentAction("a2", "http_request", {"method": "GET", "path": "/b"}),
        ),
        discriminates=("authorized_access", "cross_identity_access"),
    )
    adapter = RecordingAdapter()
    observations = execute_adapter_experiment(experiment, adapter)

    assert [item.action_id for item in observations] == ["a1", "a2"]
    assert [item.action_id for item in adapter.calls] == ["a1", "a2"]
    assert adapter.calls[1].metadata["hypothesis_id"] == "H-WEB2-AUTH-1"


def test_adapter_gap_stops_experiment_and_is_not_security_evidence() -> None:
    experiment = bind_adapter_experiment(
        hypothesis(),
        target="https://authorized.example",
        actions=(
            ExperimentAction("a1", "unsupported", {}),
            ExperimentAction("a2", "http_request", {"method": "GET", "path": "/never"}),
        ),
        discriminates=("authorized_access", "cross_identity_access"),
    )
    observations = execute_adapter_experiment(experiment, BlockingAdapter())

    assert len(observations) == 1
    assert observations[0].status == AdapterStatus.UNAVAILABLE
    assert observations[0].error == "missing capability"
