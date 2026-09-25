from pathlib import Path

from cydra.pipeline import investigate


def test_guard_parity_finds_unchecked_shared_state_transition():
    result = investigate(Path("benchmarks/009_guard_parity_euler/GuardParityTarget.sol"))
    matches = [
        h
        for h in result.hypotheses
        if h.target_function == "donateToReserves"
        and h.invariant_id == "INV-GUARD-PARITY-donateToReserves"
    ]
    assert len(matches) == 1
    assert matches[0].invariant_id == "INV-GUARD-PARITY-donateToReserves"
    assert "withdraw" in matches[0].related_functions
    assert "burn" in matches[0].related_functions


def test_guard_parity_does_not_flag_patched_counterpart():
    result = investigate(Path("benchmarks/009_guard_parity_euler/GuardParityTargetPatched.sol"))
    assert not [h for h in result.hypotheses if h.target_function == "donateToReserves" and h.invariant_id.startswith("INV-GUARD-PARITY-")]
