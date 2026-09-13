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


def _unauthorized_caller_shape(
    target_var: str,
    unauthorized_addr: str,
    initialize_args_str: str,
) -> str:
    return (
        "function testInitializationInterfaceIsCallable() public {\n"
        f"    address unauthorized = address({unauthorized_addr});\n"
        "    vm.prank(unauthorized);\n"
        "    vm.expectRevert();\n"
        f"    {target_var}.initialize({initialize_args_str});\n"
        "}"
    )


def _lifecycle_shape(target_var: str, unauthorized_addr: str, initialize_args_str: str) -> str:
    """Probe the deployed first-call boundary for a lifecycle invariant.

    A second-call-only assertion proves one-shot behavior but cannot detect an
    attacker-controlled first initialization. A first call by an arbitrary
    caller is therefore the security-relevant experiment for this shape.
    """
    return (
        "function testInitializationInterfaceIsCallable() public {\n"
        f"    address unauthorized = address({unauthorized_addr});\n"
        "    vm.prank(unauthorized);\n"
        "    vm.expectRevert();\n"
        f"    {target_var}.initialize({initialize_args_str});\n"
        "}"
    )


def _fallback_shape(target_var: str, initialize_args_str: str) -> str:
    LOGGER.warning("shape undetermined")
    return (
        "function testInitializationInterfaceIsCallable() public {\n"
        f"    {target_var}.initialize({initialize_args_str});\n"
        "}"
    )


def render_initialization_test_body(
    function_model: FunctionModel,
    target_var: str,
    unauthorized_addr: str,
    initialize_args_str: str,
) -> str:
    """Render only the Solidity initialization test function body."""
    shape = _select_shape(function_model)
    if shape == "unauthorized_caller":
        return _unauthorized_caller_shape(target_var, unauthorized_addr, initialize_args_str)
    if shape == "lifecycle":
        return _lifecycle_shape(target_var, unauthorized_addr, initialize_args_str)
    return _fallback_shape(target_var, initialize_args_str)
