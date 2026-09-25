"""Project the existing Solidity structural model into the canonical SystemModel.

This is an adapter boundary, not a security classifier. It preserves the existing
Solidity parser and turns its observations into canonical graph nodes/edges so later
reasoning can operate on system structure rather than vulnerability-class heuristics.
"""
from __future__ import annotations

from .models import ContractModel
from .system_model import Edge, Node, SystemModel


def _contract_id(contract: ContractModel) -> str:
    return f"contract:{contract.source}:{contract.name}"


def _function_id(contract: ContractModel, function) -> str:
    signature = ",".join(parameter.type for parameter in function.parameters)
    return f"function:{contract.source}:{contract.name}:{function.name}({signature})"


def project_contract_model(contract: ContractModel, system: SystemModel | None = None) -> SystemModel:
    system = system or SystemModel()
    contract_id = _contract_id(contract)
    system.add_node(Node(contract_id, "contract", contract.name, {
        "source": "solidity_model", "source_path": contract.source,
        "state_variables": list(contract.state_variables), "inherits": list(contract.inherits), "pragma": contract.pragma,
    }))
    for state in contract.state_variables:
        state_id = f"state:{contract.source}:{contract.name}:{state}"
        system.add_node(Node(state_id, "state_variable", state, {"source": "solidity_model", "source_path": contract.source, "contract": contract_id}))
        system.add_edge(Edge(state_id, "defined_in", contract_id, {"provenance": "solidity_model"}))
    for function in contract.functions:
        function_id = _function_id(contract, function)
        system.add_node(Node(function_id, "function", function.name, {
            "source": "solidity_model", "source_path": contract.source, "contract": contract.name,
            "visibility": function.visibility, "modifiers": list(function.modifiers), "line": function.line,
            "parameters": [{"name": p.name, "type": p.type, "data_location": p.data_location} for p in function.parameters],
            "authorization_predicates": list(function.authorization_predicates), "state_predicates": list(function.state_predicates),
        }))
        system.add_edge(Edge(function_id, "defined_in", contract_id, {"provenance": "solidity_model"}))
        for modifier in function.modifiers:
            modifier_id = f"authorization:{contract.source}:{contract.name}:{modifier}"
            if modifier_id not in system.nodes:
                system.add_node(Node(modifier_id, "authorization", modifier, {"source": "solidity_model", "source_path": contract.source, "contract": contract.name}))
            system.add_edge(Edge(function_id, "enforces", modifier_id, {"provenance": "solidity_model"}))
        for state in function.writes:
            state_id = f"state:{contract.source}:{contract.name}:{state}"
            if state_id not in system.nodes:
                system.add_node(Node(state_id, "state_variable", state, {"source": "solidity_model", "source_path": contract.source, "contract": contract_id}))
            system.add_edge(Edge(function_id, "writes", state_id, {"provenance": "solidity_model"}))
        for target in function.external_calls:
            target_id = f"dataflow:{contract.source}:{contract.name}:{function.name}:{target}"
            if target_id not in system.nodes:
                system.add_node(Node(target_id, "data_flow", str(target), {"source": "solidity_model", "source_path": contract.source, "contract": contract_id, "function": function_id}))
            system.add_edge(Edge(function_id, "external_call", target_id, {"provenance": "solidity_model"}))
    return system


def project_contracts(contracts: tuple[ContractModel, ...], system: SystemModel | None = None) -> SystemModel:
    system = system or SystemModel()
    for contract in contracts:
        project_contract_model(contract, system)
    return system
