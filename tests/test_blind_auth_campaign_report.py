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
    contract = SimpleNamespace(
        name="Splitter",
        source="src/Splitter.sol",
        functions=(function,),
    )
    result = SimpleNamespace(contracts=(contract,), invariants=())

    payload = _no_hypothesis_payload(
        "https://example.invalid/repo@deadbeef:src/Splitter.sol",
        compiler,
        result,
    )

    assert payload["disposition"] == "NO_SUPPORTED_HYPOTHESIS"
    assert payload["finding_gate"] == "NOT_READY"
    assert payload["hypotheses"] == []
    assert payload["semantic_state_effects"][0]["target"] == "feeRecipient"
    assert "not evidence that the target is secure" in payload["note"]
