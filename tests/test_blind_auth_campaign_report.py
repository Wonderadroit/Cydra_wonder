from types import SimpleNamespace

from scripts.run_benchmark_006_blind_auth import _no_hypothesis_payload


def test_no_hypothesis_payload_is_explicitly_not_a_finding():
    effect = SimpleNamespace(
        contract="Splitter",
        function="changeFeeRecipient",
        relation="writes",
        target="feeRecipient",
        source="solc-json-ast-internal-call:src/Splitter.sol",
        source_location=(10, 1, 1),
        metadata={"propagated_from_internal_call": "_changeFeeRecipient"},
    )
    compiler = SimpleNamespace(
        executed=True,
        status="success",
        compiler_versions=("0.8.18",),
        evidence=(effect,),
    )
    function = SimpleNamespace(
        name="changeFeeRecipient",
        visibility="public",
        modifiers=("onlyOwner",),
        writes=(),
    )
    permissionless = SimpleNamespace(
        name="payWhitehat",
        visibility="external",
        modifiers=(),
        writes=(),
    )
    contract = SimpleNamespace(
        name="Splitter",
        source="src/Splitter.sol",
        functions=(function, permissionless),
    )
    result = SimpleNamespace(contracts=(contract,), invariants=())

    payload = _no_hypothesis_payload(
        "https://example.invalid/repo@deadbeef:src/Splitter.sol",
        compiler,
        result,
    )

    assert payload["disposition"] == "BLOCKED"
    assert payload["finding_gate"] == "NOT_READY"
    assert payload["hypotheses"] == []
    assert payload["semantic_state_effects"][0]["target"] == "feeRecipient"
    assert [row["function"] for row in payload["surface_coverage"]] == [
        "changeFeeRecipient",
        "payWhitehat",
    ]
    assert payload["surface_coverage"][0]["heuristic_disposition"] == (
        "MODIFIER_PRESENT_REQUIRES_SEMANTIC_VALIDATION"
    )
    assert payload["surface_coverage"][1]["heuristic_disposition"] == (
        "NOT_SELECTED_BY_ADMIN_NAME_WRITE_HEURISTIC"
    )
    assert all(row["is_finding"] is False for row in payload["surface_coverage"])
    assert "not evidence that the target is secure" in payload["note"]


def test_no_auth_hypothesis_classifies_role_parity_as_outside_specialist():
    candidate = SimpleNamespace(
        hypothesis_id="H-INTENT-PARITY-registerChainEquivalence",
        claim="registerChainEquivalence may enforce a narrower caller boundary than documented role intent",
        invariant_id="INV-INTENT-PARITY-registerChainEquivalence",
        target_function="registerChainEquivalence",
        attacker_capability="a documented-but-excluded caller role",
        expected_impact="a caller permitted by the documented role boundary is rejected",
        evidence_ids=("E-MODEL-registerChainEquivalence",),
    )
    compiler = SimpleNamespace(
        executed=True,
        status="success",
        compiler_versions=("0.8.20",),
        evidence=(),
    )
    result = SimpleNamespace(contracts=(), invariants=(), hypotheses=(candidate,))

    payload = _no_hypothesis_payload(
        "https://example.invalid/repo@deadbeef:contracts/Adapter.sol",
        compiler,
        result,
        related_intent_parity_hypotheses=(candidate,),
    )

    assert payload["classification"] == "UNSUPPORTED_INTENT_PARITY_HYPOTHESIS"
    assert payload["blocker"] == "INTENT_PARITY_OUTSIDE_AUTH_SPECIALIST"
    assert payload["finding_gate"] == "NOT_READY"
    assert payload["related_intent_parity_hypotheses"][0]["hypothesis_id"] == candidate.hypothesis_id
    assert "not a vulnerability finding" in payload["note"]



def test_no_hypothesis_payload_marks_unprotected_admin_name_for_review_not_as_finding():
    function = SimpleNamespace(
        name="setRouter",
        visibility="external",
        modifiers=(),
        writes=("router",),
    )
    contract = SimpleNamespace(
        name="Fixture",
        source="src/Fixture.sol",
        functions=(function,),
    )
    compiler = SimpleNamespace(
        executed=True,
        status="success",
        compiler_versions=("0.8.20",),
        evidence=(),
    )
    result = SimpleNamespace(contracts=(contract,), invariants=(), hypotheses=())

    payload = _no_hypothesis_payload(
        "https://example.invalid/repo@deadbeef:src/Fixture.sol",
        compiler,
        result,
    )

    assert payload["surface_coverage"][0]["heuristic_disposition"] == (
        "ADMIN_NAMED_UNGUARDED_CANDIDATE"
    )
    assert payload["surface_coverage"][0]["is_finding"] is False
    assert payload["finding_gate"] == "NOT_READY"
