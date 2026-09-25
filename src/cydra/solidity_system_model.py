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