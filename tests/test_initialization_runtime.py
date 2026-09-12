from cydra.foundry import ExecutionResult
from cydra.initialization_runtime import classify_initialization_execution, parse_forge_human_summary, parse_forge_json
from cydra.models import Hypothesis


def _hypothesis(target="Minter"):
    return Hypothesis(
        hypothesis_id=f"H-INIT-{target}",
        claim="unauthorized caller can initialize",
        invariant_id="INV-INIT-001",
        target_function="initialize",
        attacker_capability="external caller",
        expected_impact="initialization",
    )


def _execution(status, failed=0, exit_code=0):
    return ExecutionResult(
        "X-H-INIT-Minter",
        "Minter",
        ("forge", "test", "--json", "--match-path", "test/cydra_generated/*.t.sol"),
        exit_code,
        True,
        1,
        failed,
        status,
        "{}",
        "",
    )


def test_parse_human_format_a():
    output = """
Ran 1 test for test/cydra_generated/Minter.t.sol:CydraInitializationInvariantTest
[PASS] testInitializationInterfaceIsCallable() (gas: 38056)
Suite result: ok. 1 passed; 0 failed; 0 skipped; finished in 841.65µs (120.02µs CPU time)

Ran 3 test suites in 9.23ms (2.61ms CPU time): 3 tests passed, 0 failed, 0 skipped (3 total tests)
"""
    summary = parse_forge_human_summary(output)
    assert (summary.suites, summary.passed, summary.failed, summary.skipped, summary.total) == (3, 3, 0, 0, 3)


def test_parse_json_requires_object():
    parsed = parse_forge_json('{"suite:test":{"test_results":{"x()":{"status":"Success"}}}}')
    assert parsed["suite:test"]["test_results"]["x()"]["status"] == "Success"


def test_initialization_pass_rejects_and_maps_to_not_confirmed():
    outcome = classify_initialization_execution(_hypothesis(), _execution("PASS"))
    assert outcome.internal_status == "rejected"
    assert outcome.benchmark_status == "not_confirmed"
    assert outcome.hypothesis.status == "rejected"
    assert outcome.hypothesis.evidence_ids == ("E-EXEC-H-INIT-Minter-INITIALIZATION",)
    assert outcome.evidence.evidence_id == "E-EXEC-H-INIT-Minter-INITIALIZATION"
    assert "tests_run=1" in outcome.evidence.claim


def test_initialization_fail_confirms():
    outcome = classify_initialization_execution(_hypothesis(), _execution("FAIL", failed=1, exit_code=1))
    assert outcome.internal_status == "confirmed"
    assert outcome.benchmark_status == "confirmed"
    assert outcome.hypothesis.status == "confirmed"


def test_initialization_unmeasurable_stays_proposed():
    outcome = classify_initialization_execution(_hypothesis(), _execution("UNMEASURABLE", exit_code=1))
    assert outcome.internal_status == "proposed"
    assert outcome.benchmark_status == "proposed"
    assert outcome.hypothesis.status == "proposed"
