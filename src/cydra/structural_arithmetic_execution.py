from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from .models import ContractModel, Experiment, Hypothesis
from .planned_call import render_function_arguments
from .foundry import _layout_aware_import_path


@dataclass(frozen=True)
class ArithmeticDivisionShape:
    function_name: str
    parameter_name: str
    multiplier: int
    offset: int
    divisor: int

    @property
    def exact_floor_expression(self) -> str:
        return f"({self.parameter_name} * {self.multiplier}) / {self.divisor}"


def _source(contract_model: ContractModel) -> str:
    try:
        return Path(contract_model.source).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""


def _strip_comments(source: str) -> str:
    return re.sub(r"//[^\n]*|/\*.*?\*/", " ", source, flags=re.DOTALL)


def _constant_values(source: str) -> dict[str, int]:
    values: dict[str, int] = {}
    pattern = re.compile(
        r"\b(?:uint(?:\d+)?|int(?:\d+)?)\s+(?:public|private|internal|external)?\s*"
        r"constant\s+(?P<name>[A-Za-z_]\w*)\s*=\s*(?P<value>\d+)\s*;"
    )
    for match in pattern.finditer(source):
        values[match.group("name")] = int(match.group("value"))
    return values


def _resolve_integer(token: str, constants: dict[str, int]) -> int | None:
    token = token.strip().replace("_", "")
    if token.isdigit():
        return int(token)
    return constants.get(token)


def extract_positive_offset_division(contract_model: ContractModel, function_name: str) -> ArithmeticDivisionShape | None:
    source = _strip_comments(_source(contract_model))
    if not source:
        return None
    function = next((item for item in contract_model.functions if item.name == function_name), None)
    if function is None or function.visibility not in {"public", "external"}:
        return None
    if len(function.parameters) != 1 or function.parameters[0].type.strip() != "uint256":
        return None

    match = re.search(
        rf"\bfunction\s+{re.escape(function_name)}\s*\([^)]*\)[^{{;]*\{{(?P<body>.*?)\}}",
        source,
        re.DOTALL,
    )
    if not match:
        return None
    body = match.group("body")
    parameter = function.parameters[0].name
    expression = re.search(
        rf"\breturn\s*\(\s*{re.escape(parameter)}\s*\*\s*(?P<multiplier>[A-Za-z_]\w*|\d+)\s*\+\s*(?P<offset>[A-Za-z_]\w*|\d+)\s*\)\s*/\s*(?P<divisor>[A-Za-z_]\w*|\d+)\s*;",
        body,
    )
    if not expression:
        return None
    constants = _constant_values(source)
    multiplier = _resolve_integer(expression.group("multiplier"), constants)
    offset = _resolve_integer(expression.group("offset"), constants)
    divisor = _resolve_integer(expression.group("divisor"), constants)
    if multiplier is None or offset is None or divisor is None:
        return None
    if multiplier <= 0 or offset <= 0 or divisor <= 0:
        return None
    return ArithmeticDivisionShape(function_name, parameter, multiplier, offset, divisor)


def choose_boundary_input(shape: ArithmeticDivisionShape, limit: int = 10_000) -> int | None:
    upper = min(max(shape.divisor * 2, 1), limit)
    for value in range(1, upper + 1):
        exact = (value * shape.multiplier) // shape.divisor
        observed = (value * shape.multiplier + shape.offset) // shape.divisor
        if observed > exact:
            return value
    return None


def _planned_arithmetic_input(experiment: Experiment, contract_model: ContractModel, function_name: str) -> str:
    function = next((item for item in contract_model.functions if item.name == function_name), None)
    if function is None:
        raise ValueError(f"model has no arithmetic target function: {function_name}")
    arguments = render_function_arguments(experiment, function)
    if len(arguments) != 1:
        raise ValueError(
            f"arithmetic execution requires exactly one planned argument for {function_name}; "
            f"got {len(arguments)}"
        )
    return arguments[0]


def generate_structural_arithmetic_test(
    hypothesis: Hypothesis,
    contract_model: ContractModel,
    vulnerable_import: str,
    patched_import: str,
    vulnerable_type: str,
    patched_type: str,
    output_path: str | Path,
    experiment: Experiment | None = None,
) -> Path:
    if hypothesis.invariant_id != "INV-ARITH-001":
        raise ValueError(f"Unsupported invariant for structural arithmetic execution: {hypothesis.invariant_id}")
    if experiment is not None and experiment.hypothesis_id != hypothesis.hypothesis_id:
        raise ValueError(
            f"experiment/hypothesis mismatch: {experiment.hypothesis_id} != {hypothesis.hypothesis_id}"
        )
    shape = extract_positive_offset_division(contract_model, hypothesis.target_function)
    if shape is None:
        raise ValueError("structural arithmetic execution requires a supported one-parameter positive-offset division")

    if experiment is not None and experiment.planned_inputs:
        boundary_value = _planned_arithmetic_input(experiment, contract_model, hypothesis.target_function)
    else:
        boundary = choose_boundary_input(shape)
        if boundary is None:
            raise ValueError("could not find a discriminating boundary input for the arithmetic hypothesis")
        boundary_value = str(boundary)

    pragma = contract_model.pragma or "^0.8.20"
    source = f'''// SPDX-License-Identifier: UNLICENSED
pragma solidity {pragma};
// Hypothesis: {hypothesis.hypothesis_id}
// Structural arithmetic differential experiment. The callable name and
// complete ABI input vector come from the canonical Experiment plan when present.
import {{Test}} from "forge-std/Test.sol";
import {{ {vulnerable_type} as VulnerableTarget }} from "{vulnerable_import}";
import {{ {patched_type} as PatchedTarget }} from "{patched_import}";

contract CydraArithmeticInvariantTest is Test {{
    VulnerableTarget internal vulnerable;
    PatchedTarget internal patched;

    function setUp() public {{
        vulnerable = new VulnerableTarget();
        patched = new PatchedTarget();
    }}

    function testBoundaryDistinguishesUpwardRounding() public {{
        uint256 input = {boundary_value};
        uint256 vulnerableValue = vulnerable.{shape.function_name}(input);
        uint256 patchedValue = patched.{shape.function_name}(input);
        uint256 exactFloor = (input * {shape.multiplier}) / {shape.divisor};

        assertEq(patchedValue, exactFloor, "patched control violates exact-floor oracle");
        assertGt(vulnerableValue, exactFloor, "vulnerable control did not exceed exact floor");
        assertGt(vulnerableValue, patchedValue, "differential behavior not demonstrated");
    }}
}}
'''
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def generate_structural_arithmetic_security_test(
    hypothesis: Hypothesis,
    contract_model: ContractModel,
    target_import: str,
    target_type: str,
    output_path: str | Path,
    experiment: Experiment | None = None,
) -> Path:
    """Generate a one-sided security assertion for the derived arithmetic invariant.

    The test deliberately contains no vulnerable/patched comparison.  It asks whether
    the target itself satisfies the independently derived exact-floor invariant, so
    vulnerable and control executions can be classified by the shared causal cycle.
    """
    if hypothesis.invariant_id != "INV-ARITH-001":
        raise ValueError(
            f"Unsupported invariant for structural arithmetic security execution: {hypothesis.invariant_id}"
        )
    if experiment is not None and experiment.hypothesis_id != hypothesis.hypothesis_id:
        raise ValueError(
            f"experiment/hypothesis mismatch: {experiment.hypothesis_id} != {hypothesis.hypothesis_id}"
        )

    shape = extract_positive_offset_division(contract_model, hypothesis.target_function)
    if shape is None:
        raise ValueError(
            "structural arithmetic security execution requires a supported "
            "one-parameter positive-offset division"
        )

    if experiment is not None and experiment.planned_inputs:
        boundary_value = _planned_arithmetic_input(
            experiment, contract_model, hypothesis.target_function
        )
    else:
        boundary = choose_boundary_input(shape)
        if boundary is None:
            raise ValueError("could not find a discriminating boundary input")
        boundary_value = str(boundary)

    function = next(
        (item for item in contract_model.functions if item.name == hypothesis.target_function),
        None,
    )
    if function is None or len(function.parameters) != 1:
        raise ValueError("arithmetic security execution requires one target parameter")

    pragma = contract_model.pragma or "^0.8.20"
    target_import = _layout_aware_import_path(target_import, output_path)
    source = f'''// SPDX-License-Identifier: UNLICENSED
pragma solidity {pragma};
// Hypothesis: {hypothesis.hypothesis_id}
// Security invariant derived from the structural arithmetic reasoning surface.
// No patched target or benchmark answer is consulted by this test.
import {{Test}} from "forge-std/Test.sol";
import {{ {target_type} }} from "{target_import}";

contract CydraArithmeticSecurityTest is Test {{
    {target_type} internal target;

    function setUp() public {{
        target = new {target_type}();
    }}

    function testArithmeticInvariant() public {{
        uint256 input = {boundary_value};
        uint256 observed = target.{shape.function_name}(input);
        uint256 exactFloor = (input * {shape.multiplier}) / {shape.divisor};

        assertLe(observed, exactFloor, "derived arithmetic invariant violated");
    }}
}}
'''
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path
