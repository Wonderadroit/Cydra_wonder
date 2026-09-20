from pathlib import Path
from cydra.pipeline import investigate
from cydra.structural_transfer_accounting import generate_transfer_accounting_hypotheses
from cydra.reasoning import plan_transfer_accounting_experiment

def test_transfer_accounting_is_blindly_inferred():
    root=Path(__file__).resolve().parents[1]
    r=investigate(root/"benchmarks/013_transfer_accounting/FeeTransferAccountingTarget.sol",reasoning_surfaces=(generate_transfer_accounting_hypotheses,),experiment_planner=plan_transfer_accounting_experiment)
    hs=[h for h in r.hypotheses if h.invariant_id.startswith("INV-TRANSFER-ACCOUNTING-")]
    assert hs and hs[0].target_function=="deposit"
