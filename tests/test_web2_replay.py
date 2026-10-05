from dataclasses import dataclass

from cydra.adapter_experiment import AdapterExperiment, ExperimentAction
from cydra.execution_adapter import AdapterObservation, AdapterStatus, AdapterRequest
from cydra.web2_replay import replay_authorization_experiment


@dataclass
class FakeAdapter:
    adapter_id: str = "fake"

    def capabilities(self):
        return ()

    def execute(self, request: AdapterRequest):
        return AdapterObservation(AdapterStatus.EXECUTED, request.action_id, {"status_code": 200, "body_sha256": "same"})


def experiment(method="GET"):
    return AdapterExperiment(
        "x", "h1", "https://example.test",
        (ExperimentAction("owner", "http_request", {"method": method, "identity_id": "alice"}),
         ExperimentAction("other", "http_request", {"method": method, "identity_id": "bob"})),
        ("authorization",),
    )


def test_read_replay_runs_twice():
    result = replay_authorization_experiment(experiment(), FakeAdapter())
    assert len(result.owner) == 2
    assert len(result.comparison) == 2


def test_mutating_replay_fails_closed():
    result = replay_authorization_experiment(experiment("POST"), FakeAdapter())
    assert result.owner[0].status == AdapterStatus.UNAVAILABLE
