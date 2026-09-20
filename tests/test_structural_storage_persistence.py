from cydra.models import Experiment
from cydra.pipeline import investigate
from cydra.structural_storage_persistence import generate_storage_persistence_hypotheses


def _planner(h):
    return Experiment(
        "EXP-" + h.hypothesis_id,
        h.hypothesis_id,
        "persist",
        ("state persists",),
        1.0,
    )


def test_memory_alias_storage_mutation_generates_hypothesis(tmp_path):
    source = tmp_path / "Target.sol"
    source.write_text(
        """
        contract Target {\n        contract Target {\n        struct Item { bool active; }
        mapping(uint256 => Item) public items;

        function update(uint256 id) external {
            _update(id);
        }

        function _update(uint256 id) internal returns (Item memory item) {
            item = items[id];
            item.active = true;
        }
        """,
        encoding="utf-8",
    )
    result = investigate(
        source,
        reasoning_surfaces=(generate_storage_persistence_hypotheses,),
        experiment_planner=_planner,
    )
    assert any(
        h.invariant_id.startswith("INV-STORAGE-PERSISTENCE-")
        for h in result.hypotheses
    )


def test_existing_surfaces_do_not_recognize_storage_persistence_shape(tmp_path):
    source = tmp_path / "Target.sol"
    source.write_text(
        """
        struct Item { bool active; }
        mapping(uint256 => Item) public items;
        function update(uint256 id) external { _update(id); }
        function _update(uint256 id) internal returns (Item memory item) {
            item = items[id];
            item.active = true;
        }
        """,
        encoding="utf-8",
    )
    result = investigate(source, reasoning_surfaces=(), experiment_planner=_planner)
    assert not any(
        h.invariant_id.startswith("INV-STORAGE-PERSISTENCE-")
        for h in result.hypotheses
    )
