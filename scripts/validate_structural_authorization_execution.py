from __future__ import annotations

from pathlib import Path

from cydra.foundry import run_foundry_test, test_path_for
from cydra.pipeline import investigate
from cydra.solidity_model import parse_solidity
from cydra.structural_auth_execution import generate_structural_authorization_test

ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "benchmarks" / "alchemix_missing_access_control"
FOUNDRY = BENCHMARK / "foundry"


def _print_execution(label, result) -> None:
    print(f"=== {label} ===")
    print(f"status={result.status} executed={result.executed} tests_run={result.tests_run} tests_failed={result.tests_failed} exit={result.exit_code}")
    print(f"command={' '.join(result.command)}")
    if result.stdout:
        print("--- stdout ---")
        print(result.stdout)
    if result.stderr:
        print("--- stderr ---")
        print(result.stderr)


def _stage_targets(vulnerable_source: Path, patched_source: Path) -> tuple[Path, Path]:
    """Stage historical targets under Foundry's test root."""
    test_dir = test_path_for(FOUNDRY, "generated/structural_auth_vulnerable.t.sol").parent.parent
    test_dir.mkdir(parents=True, exist_ok=True)
    staged_vulnerable = test_dir / "Target.sol"
    staged_patched = test_dir / "PatchedTarget.sol"
    staged_vulnerable.write_text(vulnerable_source.read_text(encoding="utf-8"), encoding="utf-8")
    staged_patched.write_text(patched_source.read_text(encoding="utf-8"), encoding="utf-8")
    return staged_vulnerable, staged_patched


def main() -> int:
    vulnerable_source = BENCHMARK / "Target.sol"
    patched_source = BENCHMARK / "PatchedTarget.sol"
    result = investigate(vulnerable_source, target="benchmark-001-structural-auth")
    hypothesis = next(h for h in result.hypotheses if h.hypothesis_id == "H-AUTH-setWhitelist")
    vulnerable_model = parse_solidity(vulnerable_source)[0]
    patched_model = parse_solidity(patched_source)[0]
    _stage_targets(vulnerable_source, patched_source)

    # Targets are staged beside the generated test directory so the generated
    # Solidity interface call is resolved entirely inside the Foundry project.
    vulnerable_test = generate_structural_authorization_test(
        hypothesis,
        vulnerable_model,
        "../Target.sol",
        vulnerable_model.name,
        test_path_for(FOUNDRY, "generated/structural_auth_vulnerable.t.sol"),
    )
    patched_test = generate_structural_authorization_test(
        hypothesis,
        patched_model,
        "../PatchedTarget.sol",
        patched_model.name,
        test_path_for(FOUNDRY, "generated/structural_auth_patched.t.sol"),
    )

    vulnerable = run_foundry_test(FOUNDRY, vulnerable_test, "X-STRUCTURAL-AUTH-VULNERABLE", "vulnerable")
    patched = run_foundry_test(FOUNDRY, patched_test, "X-STRUCTURAL-AUTH-PATCHED", "patched")
    _print_execution("vulnerable", vulnerable)
    _print_execution("patched", patched)

    if not vulnerable.executed or not patched.executed:
        raise SystemExit("structural authorization execution was not measurable; inspect Foundry diagnostics above")
    if vulnerable.status != "PASS":
        raise SystemExit("structural authorization generator did not execute the vulnerable control path")
    if patched.status != "FAIL":
        raise SystemExit("structural authorization generator did not distinguish the patched authorization boundary")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
