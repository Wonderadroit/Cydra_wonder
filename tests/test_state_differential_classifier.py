from cydra.foundry import ExecutionResult
from cydra.models import Hypothesis
from cydra.state_relation_evidence import StateRelationObservationEvidence
from cydra.state_differential_classifier import classify_state_differential


def _execution(experiment_id: str, status: str) -> ExecutionResult:
    return ExecutionResult(
        experiment_id=experiment_id,
        target="Target",
        command=("forge", "test"),
        exit_code=1 if status == "FAIL" else 0,
        executed=True,
        tests_run=1,
        tests_failed=1 if status == "FAIL" else 0,
        status=status,
        stdout="",
        stderr="",
    )


def _evidence(experiment_id: str) -> StateRelationObservationEvidence:
    return StateRelationObservationEvidence(
        evidence_id="E-REL-1",
        kind="execution",
        state="counter",
        relation="bump",
        experiment_id=experiment_id,
        expression="after(counter) == before(counter) + 1",
        source="source:Target.sol",
    )


def test_state_differential_requires_relation_evidence():
    hypothesis = Hypothesis(
        "H-STATE-counter", "candidate", "INV-STATE-counter",
        "bump", "attacker", "candidate",
    )
    try:
        classify_state_differential(
            hypothesis,
            _execution("X-vulnerable", "FAIL"),
            _execution("X-patched", "PASS"),
            (),
        )
    except ValueError as exc:
        assert "relation evidence" in str(exc)
    else:
        raise AssertionError("state classification must fail closed without relation evidence")


def test_state_differential_uses_shared_causal_rule_after_relation_verification():
    hypothesis = Hypothesis(
        "H-STATE-counter", "candidate", "INV-STATE-counter",
        "bump", "attacker", "candidate",
    )
    vulnerable = _execution("X-vulnerable", "FAIL")
    patched = _execution("X-patched", "PASS")
    outcome = classify_state_differential(
        hypothesis,
        vulnerable,
        patched,
        (_evidence(vulnerable.experiment_id),),
    )
    assert outcome.hypothesis.status == "confirmed"
    assert outcome.vulnerable is vulnerable
    assert outcome.patched is patched


def test_state_differential_rejects_unrelated_relation_evidence():
    hypothesis = Hypothesis(
        "H-STATE-counter", "candidate", "INV-STATE-counter",
        "bump", "attacker", "candidate",
    )
    try:
        classify_state_differential(
            hypothesis,
            _execution("X-vulnerable", "FAIL"),
            _execution("X-patched", "PASS"),
            (_evidence("X-other-RELATION"),),
        )
    except ValueError as exc:
        assert "not bound" in str(exc)
    else:
        raise AssertionError("unrelated relation evidence must not classify the state hypothesis")
