from cydra.foundry import ExecutionResult
from cydra.initialization_runtime import _json_execution_results, classify_initialization_execution, parse_forge_human_summary, parse_forge_json
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


def _execution(status, failed=0, exit_code=0, stdout="{}"):
    return ExecutionResult(
        "X-H-INIT-Minter",
        "Minter",
        ("forge", "test", "--json", "--match-path", "test/cydra_generated/*.t.sol"),
        exit_code,
        True,
        1,
        failed,
        status,
        stdout,
        "",
    )


def test_parse_human_format_a():
    output = """
Ran 1 test for test/cydra_generated/Voter.t.sol:CydraInitializationInvariantTest
[PASS] testInitializationInterfaceIsCallable() (gas: 32968)
Suite result: ok. 1 passed; 0 failed; 0 skipped; finished in 814.58µs (100.36µs CPU time)

Ran 1 test for test/cydra_generated/Minter.t.sol:CydraInitializationInvariantTest
[PASS] testInitializationInterfaceIsCallable() (gas: 38056)
Suite result: ok. 1 passed; 0 failed; 0 skipped; finished in 841.65µs (120.02µs CPU time)

Ran 1 test for test/cydra_generated/Pool.t.sol:CydraInitializationInvariantTest
[PASS] testInitializationInterfaceIsCallable() (gas: 591244)
Suite result: ok. 1 passed; 0 failed; 0 skipped; finished in 951.23µs (177.74µs CPU time)

Ran 3 test suites in 9.23ms (2.61ms CPU time): 3 tests passed, 0 failed, 0 skipped (3 total tests)
"""
    summary = parse_forge_human_summary(output)
    assert (summary.suites, summary.passed, summary.failed, summary.skipped, summary.total) == (3, 3, 0, 0, 3)


def test_parse_json_requires_object():
    parsed = parse_forge_json('{"suite:test":{"test_results":{"x()":{"status":"Success"}}}}')
    assert parsed["suite:test"]["test_results"]["x()"]["status"] == "Success"


def test_json_target_derivation_strips_t_sol_suffix():
    suites = {
        f"test/cydra_generated/{target}.t.sol:CydraInitializationInvariantTest": {
            "test_results": {"testInitializationInterfaceIsCallable()": {"status":"Success"}}
        }
        for target in ("Minter", "Voter", "Pool")
    }
    results = _json_execution_results(suites, "{}", "", 0)
    assert [result.target for result in results] == ["Minter", "Voter", "Pool"]


def test_initialization_pass_rejects_and_maps_to_not_confirmed():
    outcome = classify_initialization_execution(_hypothesis(), _execution("PASS"))
    assert outcome.internal_status == "rejected"
    assert outcome.benchmark_status == "not_confirmed"
    assert outcome.hypothesis.status == "rejected"
    assert outcome.hypothesis.evidence_ids == ("E-EXEC-H-INIT-Minter-INITIALIZATION",)
    assert outcome.evidence.evidence_id == "E-EXEC-H-INIT-Minter-INITIALIZATION"
    assert "tests_run=1" in outcome.evidence.claim
    assert "semantics=successful_execution" in outcome.evidence.claim


def test_initialization_security_assertion_failure_confirms():
    stdout = "[FAIL: expected revert, but no revert was received] testInitializationInterfaceIsCallable()"
    outcome = classify_initialization_execution(_hypothesis(), _execution("FAIL", failed=1, exit_code=1, stdout=stdout))
    assert outcome.internal_status == "confirmed"
    assert outcome.benchmark_status == "confirmed"
    assert outcome.hypothesis.status == "confirmed"
    assert "semantics=security_assertion_failure" in outcome.evidence.claim


def test_initialization_generic_mutation_assertion_confirms():
    stdout = "Error: arbitrary initializer call mutated target storage\nError: a == b not satisfied"
    outcome = classify_initialization_execution(_hypothesis(), _execution("FAIL", failed=1, exit_code=1, stdout=stdout))
    assert outcome.internal_status == "confirmed"
    assert outcome.benchmark_status == "confirmed"
    assert "semantics=security_assertion_failure" in outcome.evidence.claim


def test_initialization_guard_revert_does_not_confirm():
    stdout = "[FAIL: InvalidInitialization()] testInitializationInterfaceIsCallable()"
    outcome = classify_initialization_execution(_hypothesis(), _execution("FAIL", failed=1, exit_code=1, stdout=stdout))
    assert outcome.internal_status == "proposed"
    assert outcome.benchmark_status == "proposed"
    assert outcome.hypothesis.status == "proposed"
    assert "semantics=deployment_guard_revert" in outcome.evidence.claim


def test_initialization_unclassified_failure_stays_proposed():
    outcome = classify_initialization_execution(_hypothesis(), _execution("FAIL", failed=1, exit_code=1, stdout="[FAIL: SomeCustomError()] testInitializationInterfaceIsCallable()"))
    assert outcome.internal_status == "proposed"
    assert outcome.benchmark_status == "proposed"
    assert outcome.hypothesis.status == "proposed"


def test_initialization_unmeasurable_stays_proposed():
    outcome = classify_initialization_execution(_hypothesis(), _execution("UNMEASURABLE", exit_code=1))
    assert outcome.internal_status == "proposed"
    assert outcome.benchmark_status == "proposed"
    assert outcome.hypothesis.status == "proposed"
