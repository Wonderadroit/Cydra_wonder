from pathlib import Path

from cydra.pipeline import investigate


def test_default_investigation_discovers_shared_state_surface(tmp_path: Path):
    source = tmp_path / "Target.sol"
    source.write_text(
        """
        pragma solidity ^0.8.20;
        contract Target {
            uint256 public balance;
            function increase(uint256 amount) external { balance += amount; }
            function decrease(uint256 amount) external { balance -= amount; }
        }
        """,
        encoding="utf-8",
    )

    result = investigate(source)

    state_hypotheses = [h for h in result.hypotheses if h.invariant_id == "INV-STATE-balance"]
    assert len(state_hypotheses) == 2
    assert all(h.related_functions for h in state_hypotheses)
    assert {e.hypothesis_id for e in result.experiments} >= {h.hypothesis_id for h in state_hypotheses}
    assert all(e.steps for e in result.experiments if e.hypothesis_id in {h.hypothesis_id for h in state_hypotheses})
