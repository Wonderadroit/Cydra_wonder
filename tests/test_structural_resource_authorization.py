from pathlib import Path

from cydra.pipeline import investigate


def test_resource_authorization_finds_unbound_owned_resource_action(tmp_path: Path):
    source = tmp_path / "Target.sol"
    source.write_text(
        """
        pragma solidity ^0.8.20;
        interface Manager {
            function ownerOf(uint256 id) external view returns (address);
            function positions(uint256 id) external view returns (uint256);
            function decreaseLiquidity(uint256 id) external;
        }
        contract Target {
            Manager manager;
            function execute(uint256 tokenId) external {
                manager.positions(tokenId);
                manager.decreaseLiquidity(tokenId);
            }
        }
        """,
        encoding="utf-8",
    )
    result = investigate(source)
    hypothesis = next(
        item for item in result.hypotheses
        if item.hypothesis_id == "H-RESOURCE-AUTH-execute-tokenId"
    )
    assert hypothesis.invariant_id == "INV-RESOURCE-AUTH-Target"
    experiment = next(item for item in result.experiments if item.hypothesis_id == hypothesis.hypothesis_id)
    assert "unrelated caller" in experiment.action
    assert len(experiment.discriminates) == 3
