from __future__ import annotations

from pathlib import Path

from cydra.foundry import generate_access_control_test, require_executed, run_foundry_test, test_path_for
from cydra.pipeline import investigate
from cydra.solidity_model import parse_solidity

ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "benchmarks" / "alchemix_missing_access_control"
FOUNDRY = BENCHMARK / "foundry"


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

    vulnerable = require_executed(
        run_foundry_test(FOUNDRY, vulnerable_test, "X-STRUCTURAL-AUTH-VULNERABLE", "vulnerable")
    )
    patched = require_executed(
        run_foundry_test(FOUNDRY, patched_test, "X-STRUCTURAL-AUTH-PATCHED", "patched")
    )

    print(f"vulnerable={vulnerable.status} tests={vulnerable.tests_run} failed={vulnerable.tests_failed}")
    print(f"patched={patched.status} tests={patched.tests_run} failed={patched.tests_failed}")

    if vulnerable.status != "PASS":
        raise SystemExit("structural authorization generator did not execute the vulnerable control path")
    if patched.status != "FAIL":
        raise SystemExit("structural authorization generator did not distinguish the patched authorization boundary")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
