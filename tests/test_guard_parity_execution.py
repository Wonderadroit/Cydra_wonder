from pathlib import Path

from cydra.guard_parity_execution import generate_guard_parity_test
from cydra.models import Experiment, Hypothesis
from cydra.solidity_model import parse_solidity


def test_guard_parity_renderer_binds_only_reasoned_target(tmp_path: Path):
    model = parse_solidity("benchmarks/009_guard_parity_euler/GuardParityTarget.sol")[0]
    hypothesis = Hypothesis(
        "H-GUARD-donateToReserves",
        "candidate",
        "INV-GUARD-PARITY-donateToReserves",
        "donateToReserves",
        "arbitrary external caller",
        "candidate impact",
    )
    experiment = Experiment(
        "X-H-GUARD-donateToReserves",
        hypothesis.hypothesis_id,
        "Execute donateToReserves(30)",
        ("missing postcondition", "guarded"),
        2.0,
        ("30",),
    )
    path = generate_guard_parity_test(
        hypothesis,
        model,
        "../src/GuardParityTarget.sol",
        "GuardParityTarget",
        tmp_path / "test.t.sol",
        experiment=experiment,
    )
    text = path.read_text()
    assert "donateToReserves(30)" in text
    assert "GuardParityTarget" in text
