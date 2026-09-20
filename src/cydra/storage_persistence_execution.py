from __future__ import annotations

from pathlib import Path

from .foundry import _layout_aware_import_path
from .models import ContractModel, Experiment, Hypothesis


def generate_storage_persistence_test(
    hypothesis: Hypothesis,
    contract_model: ContractModel,
    target_import: str,
    target_type: str,
    output_path: str | Path,
    *,
    experiment: Experiment,
) -> Path:
    if not hypothesis.invariant_id.startswith("INV-STORAGE-PERSISTENCE-"):
        raise ValueError("unsupported invariant")
    target_import = _layout_aware_import_path(target_import, output_path)
    pragma = contract_model.pragma or "^0.8.20"
    source = f'''// SPDX-License-Identifier: UNLICENSED
pragma solidity {pragma};

import {{ {target_type} }} from "{target_import}";
import {{Node, NodeType, Target}} from "../src/shared/Common.sol";

contract CydraStoragePersistenceTest {{
    {target_type} internal target;

    function setUp() public {{
        target = new {target_type}(address(this), address(this));
    }}

    function testStateTransitionPersists() public {{
        Node memory from = Node({{
            nodeType: NodeType.ACCOUNT,
            entity: Target({{chainId: block.chainid, target: address(this)}}),
            creator: Target({{chainId: block.chainid, target: address(this)}}),
            data: ""
        }});
        Node memory to = Node({{
            nodeType: NodeType.ACCOUNT,
            entity: Target({{chainId: block.chainid, target: address(this)}}),
            creator: Target({{chainId: block.chainid, target: address(this)}}),
            data: hex"2a"
        }});

        target.createEdge(from, to, "");
        bytes32 id = target.getEdgeId(from, to);
        target.acknowledgeEdge(id, "");

        (, , bool acknowledged, ) = target.edges(id);
        require(
            acknowledged,
            "CYDRA_SECURITY_ASSERTION: state transition was not persisted"
        );
    }}
}}
'''
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path
