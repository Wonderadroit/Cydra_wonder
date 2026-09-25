from pathlib import Path

from cydra.repository_investigation import discover_in_scope_solidity, investigate_repository


def test_repository_inventory_excludes_non_source_security_boundaries(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "test").mkdir()
    (tmp_path / "lib").mkdir()
    (tmp_path / "src" / "A.sol").write_text("pragma solidity ^0.8.0; contract A {}")
    (tmp_path / "test" / "Ignored.sol").write_text("contract Ignored {}")
    (tmp_path / "lib" / "Ignored.sol").write_text("contract Ignored {}")

    files = discover_in_scope_solidity(tmp_path)

    assert [item.relative_to(tmp_path).as_posix() for item in files] == ["src/A.sol"]


def test_repository_investigation_builds_one_canonical_model_from_multiple_contracts(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "A.sol").write_text(
        "pragma solidity ^0.8.0; contract A { uint256 value; function set(uint256 x) external { value = x; } }"
    )
    (src / "B.sol").write_text(
        "pragma solidity ^0.8.0; contract B { uint256 other; function update(uint256 x) external { other = x; } }"
    )

    campaign = investigate_repository(tmp_path)

    assert campaign.source_files == ("src/A.sol", "src/B.sol")
    assert {contract.name for contract in campaign.contracts} == {"A", "B"}
    assert len(campaign.results) == 2
    contract_nodes = [
        node for node in campaign.system_model.nodes.values() if node.kind == "contract"
    ]
    assert {node.label for node in contract_nodes} == {"A", "B"}
    assert any(edge.relation == "defined_in" for edge in campaign.system_model.edges)


def test_repository_namespace_keeps_same_function_names_executable(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    source = "pragma solidity ^0.8.0; contract A { uint256 value; function set(uint256 x) external { value = x; } }"
    (src / "A.sol").write_text(source)
    (src / "B.sol").write_text(source.replace("contract A", "contract B"))

    campaign = investigate_repository(tmp_path)
    ids = [
        hypothesis.hypothesis_id
        for result in campaign.results
        for hypothesis in result.hypotheses
    ]

    assert len(ids) == len(set(ids))


def test_repository_reasoning_surface_receives_canonical_system_model(tmp_path: Path):
    from cydra.models import Hypothesis, Invariant
    from cydra.reasoning_surface import ReasoningContribution

    src = tmp_path / "src"
    src.mkdir()
    (src / "A.sol").write_text(
        "pragma solidity ^0.8.0; contract A { uint256 value; function set(uint256 x) external { value = x; } }"
    )

    seen = []

    def surface(contract, semantic, system_model):
        seen.append((contract.name, system_model))
        return ReasoningContribution(
            invariants=(
                Invariant(
                    "INV-REPO-CONTEXT-001",
                    "repository context is available to this reasoning surface",
                    "system_model",
                    1.0,
                ),
            ),
            hypotheses=(
                Hypothesis(
                    "H-REPO-CONTEXT-001",
                    "the reasoning surface can inspect repository-wide canonical context",
                    "INV-REPO-CONTEXT-001",
                    contract.functions[0].name,
                    "external caller",
                    "context inspection",
                ),
            ),
        )

    campaign = investigate_repository(tmp_path, reasoning_surfaces=(surface,))

    assert seen and seen[0][0] == "A"
    model = seen[0][1]
    assert any(node.kind == "contract" and node.label == "A" for node in model.nodes.values())
    assert any(item.invariant_id == "INV-REPO-CONTEXT-001" for item in campaign.invariants)
