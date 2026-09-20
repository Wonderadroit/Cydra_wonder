from pathlib import Path

import pytest

from cydra.models import ContractModel, Experiment, FunctionModel, Hypothesis, ParameterModel
from cydra.structural_arithmetic_execution import (
    choose_boundary_input,
    extract_positive_offset_division,
    generate_structural_arithmetic_test,
)


def _model(tmp_path: Path, source_text: str, function_name: str = "calculate") -> ContractModel:
    source = tmp_path / "Target.sol"
    source.write_text(source_text, encoding="utf-8")
    return ContractModel(
        name="RenamedTarget",
        source=str(source),
        functions=(
            FunctionModel(
                name=function_name,
                visibility="external",
                modifiers=(),
                writes=(),
                external_calls=(),
                line=5,
                parameters=(ParameterModel("amount", "uint256"),),
            ),
        ),
        pragma="^0.8.20",
    )


def _hypothesis(function_name: str = "calculate") -> Hypothesis:
    return Hypothesis(
        hypothesis_id=f"H-ARITH-{function_name}",
        claim="output may exceed the exact integer floor",
        invariant_id="INV-ARITH-001",
        target_function=function_name,
        attacker_capability="boundary input",
        expected_impact="observed output exceeds exact floor",
    )


def _experiment(hypothesis_id: str = "H-ARITH-calculate", inputs=("777",), target_function="calculate") -> Experiment:
    return Experiment(
        experiment_id=f"X-{hypothesis_id}",
        hypothesis_id=hypothesis_id,
        action="execute candidate function",
        discriminates=("boundary behavior",),
        cost=1.0,
        planned_inputs=tuple(inputs),
        target_function=target_function,
    )


def test_extracts_renamed_function_and_constants(tmp_path: Path):
    model = _model(
        tmp_path,
        """pragma solidity ^0.8.20;
contract RenamedTarget {
    uint256 constant MULTIPLIER = 1000;
    uint256 constant OFFSET = 996;
    uint256 constant DIVISOR = 997;
    function calculate(uint256 amount) external pure returns (uint256) {
        return (amount * MULTIPLIER + OFFSET) / DIVISOR;
    }
}
""",
    )
    shape = extract_positive_offset_division(model, "calculate")
    assert shape is not None
    assert (shape.multiplier, shape.offset, shape.divisor) == (1000, 996, 997)
    assert choose_boundary_input(shape) == 1


def test_comment_only_expression_is_not_executable_candidate(tmp_path: Path):
    model = _model(
        tmp_path,
        """pragma solidity ^0.8.20;
contract RenamedTarget {
    function calculate(uint256 amount) external pure returns (uint256) {
        // return (amount * 1000 + 996) / 997;
        return amount / 997;
    }
}
""",
    )
    assert extract_positive_offset_division(model, "calculate") is None


def test_small_offset_can_require_nontrivial_boundary_search(tmp_path: Path):
    model = _model(
        tmp_path,
        """pragma solidity ^0.8.20;
    contract RenamedTarget {
    uint256 constant MULTIPLIER = 1000;
    uint256 constant OFFSET = 1;
    uint256 constant DIVISOR = 997;
    function calculate(uint256 amount) external pure returns (uint256) {
        return (amount * MULTIPLIER + OFFSET) / DIVISOR;
    }
}
""",
    )
    shape = extract_positive_offset_division(model, "calculate")
    assert shape is not None
    assert choose_boundary_input(shape) == 332


def test_generator_rejects_other_invariants(tmp_path: Path):
    model = _model(
        tmp_path,
        """pragma solidity ^0.8.20;
contract RenamedTarget {
    function calculate(uint256 amount) external pure returns (uint256) {
        return (amount * 10 + 9) / 7;
    }
}
""",
    )
    hypothesis = Hypothesis(
        "H-AUTH-nope", "claim", "INV-AUTH-001", "calculate", "capability", "impact"
    )
    with pytest.raises(ValueError, match="Unsupported invariant"):
        generate_structural_arithmetic_test(
            hypothesis,
            model,
            "../Target.sol",
            "../PatchedTarget.sol",
            "RenamedTarget",
            "RenamedTarget",
            tmp_path / "generated.t.sol",
        )


def test_generator_contains_differential_floor_oracle(tmp_path: Path):
    model = _model(
        tmp_path,
        """pragma solidity ^0.8.20;
contract RenamedTarget {
    function calculate(uint256 amount) external pure returns (uint256) {
        return (amount * 10 + 9) / 7;
    }
}
""",
    )
    path = generate_structural_arithmetic_test(
        _hypothesis(),
        model,
        "../Target.sol",
        "../PatchedTarget.sol",
        "RenamedTarget",
        "RenamedTarget",
        tmp_path / "generated.t.sol",
    )
    source = path.read_text(encoding="utf-8")
    assert "exactFloor" in source
    assert "vulnerableValue > exactFloor" in source or "assertGt(vulnerableValue, exactFloor" in source
    assert "quoteMint" not in source


def test_generator_uses_canonical_planned_input(tmp_path: Path):
    model = _model(
        tmp_path,
        """pragma solidity ^0.8.20;
contract RenamedTarget {
    function calculate(uint256 amount) external pure returns (uint256) {
        return (amount * 10 + 9) / 7;
    }
}
""",
    )
    path = generate_structural_arithmetic_test(
        _hypothesis(),
        model,
        "../Target.sol",
        "../PatchedTarget.sol",
        "RenamedTarget",
        "RenamedTarget",
        tmp_path / "planned.t.sol",
        experiment=_experiment(),
    )
    source = path.read_text(encoding="utf-8")
    assert "uint256 input = 777;" in source
    assert "uint256 input = 1;" not in source


def test_generator_rejects_planned_input_for_wrong_target_function(tmp_path: Path):
    model = _model(
        tmp_path,
        """pragma solidity ^0.8.20;
contract RenamedTarget {
    function calculate(uint256 amount) external pure returns (uint256) {
        return (amount * 10 + 9) / 7;
    }
}
""",
    )
    with pytest.raises(ValueError, match="experiment target mismatch"):
        generate_structural_arithmetic_test(
            _hypothesis(),
            model,
            "../Target.sol",
            "../PatchedTarget.sol",
            "RenamedTarget",
            "RenamedTarget",
            tmp_path / "wrong-target.t.sol",
            experiment=_experiment(target_function="other"),
        )


def test_security_generator_uses_derived_invariant_without_patched_target(tmp_path: Path):
    model = _model(
        tmp_path,
        """pragma solidity ^0.8.20;
contract RenamedTarget {
    function calculate(uint256 amount) external pure returns (uint256) {
        return (amount * 10 + 9) / 7;
    }
}
""",
    )
    from cydra.structural_arithmetic_execution import generate_structural_arithmetic_security_test

    path = generate_structural_arithmetic_security_test(
        _hypothesis(),
        model,
        "../Target.sol",
        "RenamedTarget",
        tmp_path / "security.t.sol",
        experiment=_experiment(),
    )
    source = path.read_text(encoding="utf-8")
    assert "assertLe(observed, exactFloor" in source
    assert "PatchedTarget" not in source
    assert "vulnerableValue" not in source
    assert "calculate(777)" not in source
    assert "uint256 input = 777;" in source
