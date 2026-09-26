from __future__ import annotations

from pathlib import Path

from .models import ContractModel, Experiment, Hypothesis
from .foundry import _constructor_argument, _layout_aware_import_path, _write_test


def generate_callback_state_order_test(
    hypothesis: Hypothesis,
    experiment: Experiment,
    target_import: str,
    target_type: str,
    output_path: str | Path,
    contract_model: ContractModel,
) -> Path:
    """Render a generic one-shot reentrant callback experiment.

    The harness treats the caller as the callback-capable contract. It re-enters
    the same externally callable target with the same ABI payload exactly once.
    No target function names, callback interfaces, or vulnerability-specific
    arguments are hard-coded here; all target call shape comes from ContractModel
    and the bound Experiment inputs.
    """
    function = next(
        (item for item in contract_model.functions if item.name == hypothesis.target_function),
        None,
    )
    if function is None:
        raise ValueError(f"model has no callback target: {hypothesis.target_function}")
    if function.visibility not in {"public", "external"}:
        raise ValueError(f"callback target is not externally callable: {function.name}")

    arguments = experiment.planned_inputs
    if len(arguments) != len(function.parameters):
        raise ValueError(
            f"callback input arity mismatch for {function.name}: "
            f"expected {len(function.parameters)}, got {len(arguments)}"
        )

    constructor_arguments = [
        _constructor_argument(parameter)
        for parameter in (contract_model.constructor.parameters if contract_model.constructor else ())
    ]
    constructor_call = (
        f"new {target_type}({', '.join(constructor_arguments)})"
        if constructor_arguments
        else f"new {target_type}()"
    )

    # abi.encodeCall preserves compiler-checked tuple/struct ABI types and avoids
    # inventing canonical signature text for source-defined parameters.
    initial_call = f"abi.encodeCall(target.{function.name}, ({", ".join(arguments)}))"

    pragma = contract_model.pragma or "^0.8.20"
    path = Path(output_path)
    target_import = _layout_aware_import_path(target_import, path)

    source = f'''// SPDX-License-Identifier: UNLICENSED
pragma solidity {pragma};
// Hypothesis: {hypothesis.hypothesis_id}
// Experiment: {experiment.experiment_id}
// Generic callback-order experiment: caller is a contract that re-enters the
// same target call exactly once from its fallback. The harness contains no
// target-specific callback interface or function name.
import {{Test}} from "forge-std/Test.sol";
import {{ {target_type} }} from "{target_import}";

contract CydraReentrantCaller {{
    address internal immutable target;
    bytes internal immutable callData;
    bool public callbackObserved;
    bool public reentrySucceeded;
    bool internal entered;

    constructor(address target_, bytes memory callData_) {{
        target = target_;
        callData = callData_;
    }}

    function invoke() external {{
        (bool ok,) = target.call(callData);
        require(ok, "initial target call reverted");
    }}

    fallback() external {{
        callbackObserved = true;
        if (!entered) {{
            entered = true;
            (reentrySucceeded,) = target.call(callData);
        }}
    }}
}}

contract CydraCallbackStateOrderTest is Test {{
    {target_type} internal target;
    CydraReentrantCaller internal attacker;

    function setUp() public {{
        target = {constructor_call};
        attacker = new CydraReentrantCaller(
            address(target),
            {initial_call}
        );
    }}

    function testCallbackStateOrder() public {{
        attacker.invoke();
        assertTrue(attacker.callbackObserved(), "target did not invoke the caller-controlled callback");
        assertTrue(attacker.reentrySucceeded(), "reentrant call was blocked or reverted");
    }}
}}
'''
    return _write_test(source, path)
