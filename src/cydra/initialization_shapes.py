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
    """Test the deployed lifecycle boundary, not merely one-shot behavior.

    A second-call-only test proves only that initialization is one-shot. It
    cannot distinguish a safely pre-initialized deployment from an
    attacker-callable first initialization. For the lifecycle invariant, the
    security-relevant observation is whether an arbitrary first caller is
    rejected in the deployed state.
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
    """Render only the Solidity test function body for initialization.

    ``initialize_args_str`` is intentionally supplied by the existing Foundry
    argument builder. This module owns test shape, not stub deployment or ABI
    argument construction.

    State evidence selects the deployed lifecycle boundary. The generated
    test therefore asks the causal question represented by the invariant:
    can an arbitrary caller perform the first initialization after deployment?
    """
    shape = _select_shape(function_model)
    if shape == "unauthorized_caller":
        return _unauthorized_caller_shape(target_var, unauthorized_addr, initialize_args_str)
    if shape == "lifecycle":
        return _lifecycle_shape(target_var, unauthorized_addr, initialize_args_str)
    return _fallback_shape(target_var, initialize_args_str)
