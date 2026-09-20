from pathlib import Path

from cydra.pipeline import investigate
from cydra.signature_replay_planning import plan_signature_replay_experiment
from cydra.structural_signature_replay import generate_signature_replay_hypotheses


def test_signature_replay_surface_finds_unbound_digest():
    source = Path(__file__).resolve().parents[1] / "benchmarks/018_signature_replay/SignatureReplayTarget.sol"
    result = investigate(
        source,
        reasoning_surfaces=(generate_signature_replay_hypotheses,),
        experiment_planner=plan_signature_replay_experiment,
    )
    matches = [h for h in result.hypotheses if h.invariant_id.startswith("INV-SIGNATURE-REPLAY-")]
    assert matches


def test_signature_replay_surface_ignores_domain_bound_digest():
    source = Path(__file__).resolve().parents[1] / "benchmarks/018_signature_replay/SignatureReplayTargetPatched.sol"
    result = investigate(
        source,
        reasoning_surfaces=(generate_signature_replay_hypotheses,),
        experiment_planner=plan_signature_replay_experiment,
    )
    assert not [h for h in result.hypotheses if h.invariant_id.startswith("INV-SIGNATURE-REPLAY-")]
