"""Project the existing Solidity structural model into the canonical SystemModel.

This is an adapter boundary, not a security classifier. It preserves the existing
Solidity parser and turns its observations into canonical graph nodes/edges so later
reasoning can operate on system structure rather than vulnerability-class heuristics.
"""
from __future__ import annotations

from .models import ContractModel
from .system_model import Edge, Node, SystemModel


def project_contract_model(contract: ContractModel, system: SystemModel | None = None) -> SystemModel:
    system = system or SystemModel()
    contract_id = f"contract:{contract.name}"
    system.add_node(Node(contract_id, "contract", contract.name, {
        "source": "solidity_model",
        "source_path": contract.source,
    }))

    for function in contract.functions:
        function_id = f"function:{contract.name}:{function.name}"
        system.add_node(Node(function_id, "function", function.name, {
            "source": "solidity_model",
            "contract": contract.name,
            "visibility": function.visibility,
            "modifiers": list(function.modifiers),
        }))
        system.add_edge(Edge(function_id, "defined_in", contract_id, {"provenance": "solidity_model"}))

        for modifier in function.modifiers:
            modifier_id = f"authorization:{contract.name}:{modifier}"
            if modifier_id not in system.nodes:
                system.add_node(Node(modifier_id, "authorization", modifier, {
                    "source": "solidity_model",
                    "contract": contract.name,
                }))
            system.add_edge(Edge(function_id, "enforces", modifier_id, {"provenance": "solidity_model"}))

    return system


def project_contracts(contracts: tuple[ContractModel, ...], system: SystemModel | None = None) -> SystemModel:
    system = system or SystemModel()
    for contract in contracts:
        project_contract_model(contract, system)
    return system
