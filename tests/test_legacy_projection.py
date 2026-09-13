from pathlib import Path
from cydra.legacy_projection import project_investigation_result
from cydra.pipeline import investigate


def test_benchmark_001_legacy_result_projects_into_canonical_graph_without_classification():
    root = Path(__file__).resolve().parents[1]
    result = investigate(root / "benchmarks/alchemix_missing_access_control/Target.sol", target="benchmark-001")
    model = project_investigation_result(result)
    assert any(node.kind == "contract" for node in model.nodes.values())
    assert any(node.kind == "function" for node in model.nodes.values())
    assert any(node.kind == "invariant" for node in model.nodes.values())
    assert any(node.kind == "hypothesis" for node in model.nodes.values())
    assert any(node.kind == "observation" for node in model.nodes.values())
    assert any(node.kind == "evidence" for node in model.nodes.values())
    assert not any(node.kind == "finding" for node in model.nodes.values())
    assert model.validate() == []
