from __future__ import annotations

from .models import ContractModel, FunctionModel


def effective_writes(contract: ContractModel, function: FunctionModel) -> tuple[str, ...]:
    """Return direct plus transitive state writes through internal calls.

    Same-contract internal calls execute in the caller's context, so their
    direct state effects are part of the caller's reachable transition.
    Cycles are handled with a recursion guard. External/qualified calls are
    intentionally absent from this relation and remain runtime boundaries.
    """
    functions = {item.name: item for item in contract.functions}
    memo: dict[str, tuple[str, ...]] = {}
    active: set[str] = set()

    def visit(item: FunctionModel) -> tuple[str, ...]:
        if item.name in memo:
            return memo[item.name]
        if item.name in active:
            return item.writes
        active.add(item.name)
        writes = set(item.writes)
        for callee_name in item.internal_calls:
            callee = functions.get(callee_name)
            if callee is not None:
                writes.update(visit(callee))
        active.remove(item.name)
        result = tuple(sorted(writes))
        memo[item.name] = result
        return result

    return visit(function)


def internal_call_edges(contract: ContractModel) -> tuple[tuple[str, str], ...]:
    """Return deterministic caller/callee pairs for direct internal calls."""
    names = {item.name for item in contract.functions}
    return tuple(sorted(
        (function.name, callee)
        for function in contract.functions
        for callee in function.internal_calls
        if callee in names
    ))