from pathlib import Path
from cydra.pipeline import investigate

def test_type_domain_reasoning_finds_narrow_identifier_used_for_wider_mapping(tmp_path: Path):
    source = tmp_path / "Target.sol"
    source.write_text("""
        pragma solidity ^0.8.20;
        contract Target {
            mapping(uint256 => uint8) public numRerolls;
            function reRoll(uint8 tokenId, uint8 fighterType) public {
                numRerolls[tokenId] += 1;
            }
        }
    """, encoding="utf-8")
    result = investigate(source)
    hypothesis = next(item for item in result.hypotheses if item.hypothesis_id == "H-TYPE-DOMAIN-reRoll-tokenId")
    assert hypothesis.invariant_id == "INV-TYPE-DOMAIN-Target"
    experiment = next(item for item in result.experiments if item.hypothesis_id == hypothesis.hypothesis_id)
    assert "boundary" in experiment.action
    assert len(experiment.discriminates) == 3
