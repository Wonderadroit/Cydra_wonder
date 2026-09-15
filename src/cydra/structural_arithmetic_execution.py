from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from .models import ContractModel, Hypothesis


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


def generate_structural_arithmetic_test(
    hypothesis: Hypothesis,
    contract_model: ContractModel,
    vulnerable_import: str,
    patched_import: str,
    vulnerable_type: str,
    patched_type: str,
    output_path: str | Path,
) -> Path:
    if hypothesis.invariant_id != "INV-ARITH-001":
        raise ValueError(f"Unsupported invariant for structural arithmetic execution: {hypothesis.invariant_id}")
    shape = extract_positive_offset_division(contract_model, hypothesis.target_function)
    if shape is None:
        raise ValueError("structural arithmetic execution requires a supported one-parameter positive-offset division")
    boundary = choose_boundary_input(shape)
    if boundary is None:
        raise ValueError("could not find a discriminating boundary input for the arithmetic hypothesis")

    pragma = contract_model.pragma or "^0.8.20"
    source = f'''// SPDX-License-Identifier: UNLICENSED
pragma solidity {pragma};
// Hypothesis: {hypothesis.hypothesis_id}
// Structural arithmetic differential experiment. The callable name, input,
// and exact-floor oracle are derived from the observed source expression.
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
        uint256 input = {boundary};
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
