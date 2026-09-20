from pathlib import Path
from cydra.pipeline import investigate
from cydra.reasoning import plan_temporal_precondition_experiment
from cydra.structural_temporal import generate_temporal_precondition_hypotheses

def test_temporal_precondition_is_discovered_blindly():
    source=Path("benchmarks/010_temporal_precondition/TemporalPreconditionTarget.sol")
    result=investigate(source,reasoning_surfaces=(generate_temporal_precondition_hypotheses,),experiment_planner=plan_temporal_precondition_experiment)
    h=next(h for h in result.hypotheses if h.invariant_id.startswith("INV-TEMPORAL-PRECONDITION-"))
    assert h.target_function=="execute"
    e=next(e for e in result.experiments if e.hypothesis_id==h.hypothesis_id)
    assert e.hypothesis_id==h.hypothesis_id
