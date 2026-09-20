from cydra.models import Experiment
from cydra.pipeline import investigate
from cydra.structural_double_debit import generate_double_debit_hypotheses


def _planner(h):
    return Experiment("EXP-" + h.hypothesis_id, h.hypothesis_id, "trace fund flow", ("single charge",), 1.0)


def _fixture():
    return """
    function buy(address from, uint256 amount) external {
        vault.withdraw(address(this), executor, amount);
        executor.getCollateral(amount);
        _addCollateral(from, amount);
    }
    function _addCollateral(address from, uint256 amount) internal {
        token.transferFrom(from, address(this), amount);
    }
    """


def test_double_debit_shape_generates_hypothesis(tmp_path):
    source = tmp_path / "Target.sol"
    source.write_text(_fixture(), encoding="utf-8")
    result = investigate(source, reasoning_surfaces=(generate_double_debit_hypotheses,), experiment_planner=_planner)
    assert any(h.invariant_id.startswith("INV-DOUBLE-DEBIT-") for h in result.hypotheses)


def test_empty_existing_surfaces_do_not_generate_double_debit(tmp_path):
    source = tmp_path / "Target.sol"
    source.write_text(_fixture(), encoding="utf-8")
    result = investigate(source, reasoning_surfaces=(), experiment_planner=_planner)
    assert not any(h.invariant_id.startswith("INV-DOUBLE-DEBIT-") for h in result.hypotheses)
