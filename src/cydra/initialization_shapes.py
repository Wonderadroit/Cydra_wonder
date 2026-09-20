from __future__ import annotations

import logging

from .models import FunctionModel

LOGGER = logging.getLogger(__name__)


def _select_shape(function_model: FunctionModel) -> str:
    """Select the initialization test shape from model evidence only."""
    if function_model.authorization_predicates:
        return "unauthorized_caller"
    if function_model.state_predicates:
        return "lifecycle"
    return "fallback"


def _call(function_model: FunctionModel, target_var: str, initialize_args_str: str) -> str:
    return f"{target_var}.{function_model.name}({initialize_args_str});"


def _unauthorized_caller_shape(
    function_model: FunctionModel,
    target_var: str,
    unauthorized_addr: str,
    initialize_args_str: str,
) -> str:
    return (
        "function testInitializationInterfaceIsCallable() public {\n"
        f"    address unauthorized = address({unauthorized_addr});\n"
        "    vm.prank(unauthorized);\n"
        "    vm.expectRevert();\n"
        f"    {_call(function_model, target_var, initialize_args_str)}\n"
        "}"
    )


def _lifecycle_shape(function_model: FunctionModel, target_var: str, initialize_args_str: str) -> str:
    """Probe first-call initialization and the second-call lifecycle boundary."""
    call = _call(function_model, target_var, initialize_args_str)
    return (
        "function testInitializationInterfaceIsCallable() public {\n"
        f"    {call}\n"
        "    vm.expectRevert();\n"
        f"    {call}\n"
        "}"
    )


def _fallback_shape(
    function_model: FunctionModel,
    target_var: str,
    unauthorized_addr: str,
    initialize_args_str: str,
) -> str:
    """Probe an otherwise unclassified initializer without treating a revert as a finding."""
    LOGGER.warning("shape undetermined; using generic mutation probe")
    call = _call(function_model, target_var, initialize_args_str)
    return (
        "function testInitializationInterfaceIsCallable() public {\n"
        f"    address unauthorized = address({unauthorized_addr});\n"
        "    vm.record();\n"
        "    vm.prank(unauthorized);\n"
        f"    try {call} {{\n"
        "        (bytes32[] memory reads, bytes32[] memory writes) = vm.accesses(address(target));\n"
        "        reads;\n"
        "        assertGt(writes.length, 0, \"initializer call succeeded without observable state mutation\");\n"
        "    } catch {\n"
        "        return;\n"
        "    }\n"
        "}"
    )


def render_initialization_test_body(
    function_model: FunctionModel,
    target_var: str,
    unauthorized_addr: str,
    initialize_args_str: str,
) -> str:
    """Render only the Solidity test function body for initialization."""
    shape = _select_shape(function_model)
    if shape == "unauthorized_caller":
        return _unauthorized_caller_shape(function_model, target_var, unauthorized_addr, initialize_args_str)
    if shape == "lifecycle":
        return _lifecycle_shape(function_model, target_var, initialize_args_str)
    return _fallback_shape(function_model, target_var, unauthorized_addr, initialize_args_str)
