from pathlib import Path
from .foundry import _layout_aware_import_path
from .models import ContractModel, Experiment, Hypothesis


def generate_read_only_reentrancy_test(
    hypothesis: Hypothesis,
    contract_model: ContractModel,
    target_import: str,
    target_type: str,
    observer_type: str,
    output_path: str | Path,
    *,
    experiment: Experiment,
) -> Path:
    if not hypothesis.invariant_id.startswith("INV-READONLY-REENTRANCY-"):
        raise ValueError("unsupported invariant")
    target_import = _layout_aware_import_path(target_import, output_path)
    pragma = contract_model.pragma or "^0.8.20"
    view_name = hypothesis.related_functions[0]
    source = f'''// SPDX-License-Identifier: UNLICENSED
pragma solidity {pragma};
import {{Test}} from "forge-std/Test.sol";
import {{ {target_type} }} from "{target_import}";

contract CydraReadOnlyReentrancyTest is Test {{
    {target_type} internal pool;
    {observer_type} internal observer;

    function setUp() public {{
        pool = new {target_type}();
        observer = new {observer_type}(pool);
        vm.deal(address(pool), 100 ether);
    }}

    function testTransientViewCannotBeTrustedDuringCallback() public {{
        uint256 settledBefore = pool.{view_name}();
        observer.attack();
        uint256 settledAfter = pool.{view_name}();

        assertEq(settledBefore, 1e18);
        assertEq(settledAfter, 1e18);

        if (address(pool).code.length > 0) {{
            assertTrue(observer.callbackSucceeded(), "view was protected before the callback");
            assertGt(observer.observed(), settledAfter, "no inconsistent intermediate observation");
        }}
    }}
}}
'''
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path
