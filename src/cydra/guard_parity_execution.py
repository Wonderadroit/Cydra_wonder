from __future__ import annotations

from pathlib import Path

from .foundry import _layout_aware_import_path
from .models import ContractModel, Experiment, Hypothesis


def generate_guard_parity_test(
    hypothesis: Hypothesis,
    contract_model: ContractModel,
    target_import: str,
    target_type: str,
    output_path: str | Path,
    *,
    experiment: Experiment,
) -> Path:
    if not hypothesis.invariant_id.startswith("INV-GUARD-PARITY-"):
        raise ValueError("unsupported invariant for guard-parity execution")
    function = next(
        (item for item in contract_model.functions if item.name == hypothesis.target_function),
        None,
    )
    if function is None or len(function.parameters) != 1:
        raise ValueError("guard-parity execution requires one target parameter")
    if not function.parameters[0].type.startswith("uint"):
        raise ValueError("guard-parity execution requires an unsigned integer parameter")
    if len(experiment.planned_inputs) != 1:
        raise ValueError("guard-parity execution requires one planned argument")

    target_import = _layout_aware_import_path(target_import, output_path)
    pragma = contract_model.pragma or "^0.8.20"
    source = f'''// SPDX-License-Identifier: UNLICENSED
pragma solidity {pragma};
import {{ {target_type} }} from "{target_import}";

contract CydraGuardParityTest {{
    {target_type} internal target;

    function setUp() public {{
        target = new {target_type}();
    }}

    function testObservedPostconditionRejectsInvalidTransition() public {{
        bool reverted;
        try target.{hypothesis.target_function}({experiment.planned_inputs[0]}) {{
        }} catch {{
            reverted = true;
        }}
        require(reverted, "state transition returned without observed postcondition enforcement");
    }}
}}
'''
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path
