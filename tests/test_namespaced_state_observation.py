from pathlib import Path

from cydra.models import ContractModel, FunctionModel
from cydra.namespaced_state_observation import plan_namespaced_state_observation


def test_erc7201_mapping_observation_resolves_struct_member_slot(tmp_path: Path) -> None:
    source = tmp_path / "Target.sol"
    source.write_text(
        """
        contract Target {
            /// @custom:storage-location erc7201:target.storage
            struct Storage {
                address helper;
                mapping(uint256 => bool) usedMessages;
            }

            bytes32 private constant TargetLocation =
                0x1000000000000000000000000000000000000000000000000000000000000000;

            function verify(uint256 message) internal {
                Storage storage $ = _get();
                if ($.usedMessages[message]) revert();
            }
        }
        """,
        encoding="utf-8",
    )
    function = FunctionModel(
        "verify", "internal", (), (), (), 10,
        parameters=(),
        execution_predicates=("$.usedMessages[message]",),
        execution_predicate_polarities=(("$.usedMessages[message]", "must_not_hold"),),
    )
    plan = plan_namespaced_state_observation(
        ContractModel("Target", str(source), (function,)),
        function,
        "$.usedMessages[message]",
    )
    assert plan is not None
    assert plan.storage_slot == "0x1000000000000000000000000000000000000000000000000000000000000001"
    assert "keccak256(abi.encode(uint256(message)" in plan.assertion


def test_erc7201_observation_fails_closed_on_packed_prefix(tmp_path: Path) -> None:
    source = tmp_path / "Target.sol"
    source.write_text(
        """
        contract Target {
            /// @custom:storage-location erc7201:target.storage
            struct Storage {
                bool flag;
                mapping(uint256 => bool) usedMessages;
            }

            bytes32 private constant TargetLocation =
                0x2000000000000000000000000000000000000000000000000000000000000000;
        }
        """,
        encoding="utf-8",
    )
    function = FunctionModel(
        "verify", "internal", (), (), (), 10,
        execution_predicates=("$.usedMessages[message]",),
        execution_predicate_polarities=(("$.usedMessages[message]", "must_not_hold"),),
    )
    assert plan_namespaced_state_observation(
        ContractModel("Target", str(source), (function,)),
        function,
        "$.usedMessages[message]",
    ) is None


def test_erc7201_mapping_observation_resolves_contract_reference_prefix(tmp_path: Path) -> None:
    helper = tmp_path / "IHinkalHelper.sol"
    helper.write_text(
        """
        interface IHinkalHelper {
            function calculateRelayFee(
                uint256 amount,
                uint256 flatFee,
                uint256 variableRate
            ) external view returns (uint256);
        }
        """,
        encoding="utf-8",
    )
    storage = tmp_path / "EmporiumStorage.sol"
    storage.write_text(
        """
        import {IHinkalHelper} from "./IHinkalHelper.sol";

        contract EmporiumStorage {
            /// @custom:storage-location erc7201:hinkal.storage.Emporium
            struct EmporiumStorageVars {
                IHinkalHelper _hinkalHelper;
                mapping(uint256 => bool) usedMessages;
            }

            bytes32 private constant EmporiumStorageLocation =
                0xf10f423c12af70b7aa31f6f1bd94310f38d85adab8d26b5c90b7f07c98bf0800;
        }
        """,
        encoding="utf-8",
    )
    source = tmp_path / "Target.sol"
    (tmp_path / "foundry.toml").write_text("[profile.default]\n", encoding="utf-8")
    source.write_text(
        """
        import "./EmporiumStorage.sol";

        contract Target is EmporiumStorage {
            function verify(uint256 message) internal {
                if ($.usedMessages[message]) revert();
            }
        }
        """,
        encoding="utf-8",
    )
    function = FunctionModel(
        "verify", "internal", (), (), (), 10,
        execution_predicates=("$.usedMessages[message]",),
        execution_predicate_polarities=(("$.usedMessages[message]", "must_not_hold"),),
    )
    plan = plan_namespaced_state_observation(
        ContractModel("Target", str(source), (function,), inherits=("EmporiumStorage",)),
        function,
        "$.usedMessages[message]",
    )
    assert plan is not None
    assert plan.storage_slot == "0xf10f423c12af70b7aa31f6f1bd94310f38d85adab8d26b5c90b7f07c98bf0801"
