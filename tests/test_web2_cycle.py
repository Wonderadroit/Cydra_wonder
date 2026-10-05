from dataclasses import dataclass

from cydra.adapter_experiment import AdapterExperiment, ExperimentAction
from cydra.execution_adapter import AdapterCapability, AdapterObservation, AdapterRequest, AdapterStatus
from cydra.hypotheses import Hypothesis, HypothesisState
from cydra.web2_cycle import run_web2_authorization_cycle


@dataclass
class FakeAuthorizationAdapter:
    adapter_id: str = "fake-web2"
    owner_status: int = 200
    comparison_status: int = 200
    body_hash: str = "same"

    def capabilities(self):
        return (AdapterCapability("HTTP_REQUEST", True),)

    def execute(self, request: AdapterRequest) -> AdapterObservation:
        status = self.owner_status if request.inputs["identity_id"] == "alice" else self.comparison_status
        body = self.body_hash if status == 200 else "denied"
        return AdapterObservation(
            AdapterStatus.EXECUTED,
            request.action_id,
            {"status_code": status, "body_sha256": body},
        )


def hypothesis() -> Hypothesis:
    return Hypothesis(
        hypothesis_id="web2-auth:resource:1:endpoint:get",
        statement="owner and comparison identity should have distinct authorization outcomes",
    )


def experiment() -> AdapterExperiment:
    return AdapterExperiment(
        experiment_id="X-web2-auth:resource:1:endpoint:get",
        hypothesis_id=hypothesis().hypothesis_id,
        target="https://authorized.example",
        actions=(
            ExperimentAction("owner", "http_request", {"identity_id": "alice"}),
            ExperimentAction("comparison", "http_request", {"identity_id": "bob"}),
        ),
        discriminates=("authorization",),
    )


def test_cycle_updates_belief_from_observed_differential():
    result = run_web2_authorization_cycle(
        hypothesis(),
        experiment(),
        FakeAuthorizationAdapter(owner_status=200, comparison_status=200, body_hash="same"),
    )

    assert result.verification.state.value == "contradicted"
    assert result.hypothesis.state == HypothesisState.CONTRADICTED
    assert result.hypothesis.belief < 0.5


def test_cycle_does_not_turn_adapter_failure_into_security_evidence():
    class Blocked(FakeAuthorizationAdapter):
        def execute(self, request):
            return AdapterObservation(AdapterStatus.UNAVAILABLE, request.action_id, error="blocked")

    result = run_web2_authorization_cycle(hypothesis(), experiment(), Blocked())

    assert result.verification.state.value == "unresolved"
    assert result.hypothesis.state == HypothesisState.UNRESOLVED
    assert result.hypothesis.belief == 0.5
