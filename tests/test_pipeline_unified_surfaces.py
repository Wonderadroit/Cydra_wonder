from pathlib import Path

from cydra.pipeline import investigate


def test_unbounded_iteration_hypotheses_survive_unified_pipeline(tmp_path: Path):
    source = tmp_path / "Target.sol"
    source.write_text(
        """
        pragma solidity ^0.8.20;
        contract Target {
            uint256[] public items;

            function add(uint256 value) external {
                items.push(value);
            }

            function process() external {
                for (uint256 i = 0; i < items.length; i++) {
                    uint256 value = items[i];
                    value;
                }
            }
        }
        """,
        encoding="utf-8",
    )

    result = investigate(source)

    assert any(
        item.invariant_id.startswith("INV-UNBOUNDED-ITERATION-")
        for item in result.hypotheses
    )
    assert any(
        item.hypothesis_id == "H-UNBOUNDED-ITERATION-process"
        for item in result.hypotheses
    )
    assert any(
        item.hypothesis_id == "H-UNBOUNDED-ITERATION-process"
        for item in result.experiments
    )


def test_temporal_signature_replay_double_debit_and_storage_surfaces_are_default(tmp_path: Path):
    temporal = tmp_path / "Temporal.sol"
    temporal.write_text(
        """
        pragma solidity ^0.8.20;
        contract Temporal {
            uint256 public ready;
            function transition() external {
                this.touch();
                require(ready == 1);
                ready = 2;
            }
            function touch() external { ready = 1; }
        }
        """,
        encoding="utf-8",
    )
    signature = tmp_path / "Signature.sol"
    signature.write_text(
        """
        pragma solidity ^0.8.20;
        contract Signature {
            function execute(bytes calldata signature) external {
                verifySignature(signature, keccak256(abi.encode(msg.sender)));
            }
            function verifySignature(bytes calldata signature, bytes32 digest) internal pure returns (bool) {
                signature; digest;
                return true;
            }
        }
        """,
        encoding="utf-8",
    )
    double_debit = tmp_path / "DoubleDebit.sol"
    double_debit.write_text(
        """
        pragma solidity ^0.8.20;
        contract DoubleDebit {
            function acquire(address from) external {
                withdraw();
                getCollateral();
                _addCollateral(from);
            }
            function withdraw() internal {}
            function getCollateral() internal {}
            function _addCollateral(address from) internal { from; }
        }
        """,
        encoding="utf-8",
    )
    storage = tmp_path / "Storage.sol"
    storage.write_text(
        """
        pragma solidity ^0.8.20;
        contract Storage {
            struct Position { uint256 value; }
            mapping(address => Position) public positions;
            function update() external { _mutate(positions[msg.sender]); }
            function _mutate(Position memory position) internal returns (Position memory) {
                Position storage alias = positions[msg.sender];
                alias.value = 7;
                return position;
            }
        }
        """,
        encoding="utf-8",
    )

    temporal_result = investigate(temporal)
    signature_result = investigate(signature)
    double_result = investigate(double_debit)
    storage_result = investigate(storage)

    assert any(h.invariant_id.startswith("INV-TEMPORAL-PRECONDITION-") for h in temporal_result.hypotheses)
    assert any(h.invariant_id.startswith("INV-SIGNATURE-REPLAY-") for h in signature_result.hypotheses)
    assert any(h.invariant_id.startswith("INV-DOUBLE-DEBIT-") for h in double_result.hypotheses)
    assert any(h.invariant_id.startswith("INV-STORAGE-PERSISTENCE-") for h in storage_result.hypotheses)

    for result in (temporal_result, signature_result, double_result, storage_result):
        assert {h.hypothesis_id for h in result.hypotheses}.intersection(
            {e.hypothesis_id for e in result.experiments}
        )
