from __future__ import annotations

from pathlib import Path

from cydra.foundry import generate_access_control_test, run_foundry_test, test_path_for
from cydra.pipeline import investigate
from cydra.solidity_model import parse_solidity

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


def main() -> int:
    vulnerable_source = BENCHMARK / "Target.sol"
    patched_source = BENCHMARK / "PatchedTarget.sol"
    result = investigate(vulnerable_source, target="benchmark-001-structural-auth")
    hypothesis = next(h for h in result.hypotheses if h.hypothesis_id == "H-AUTH-setWhitelist")
    vulnerable_model = parse_solidity(vulnerable_source)[0]
    patched_model = parse_solidity(patched_source)[0]

    vulnerable_test = generate_access_control_test(
        hypothesis,
        "../../Target.sol",
        vulnerable_model.name,
        test_path_for(FOUNDRY, "generated/structural_auth_vulnerable.t.sol"),
        contract_model=vulnerable_model,
    )
    patched_test = generate_access_control_test(
        hypothesis,
        "../../PatchedTarget.sol",
        patched_model.name,
        test_path_for(FOUNDRY, "generated/structural_auth_patched.t.sol"),
        contract_model=patched_model,
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
