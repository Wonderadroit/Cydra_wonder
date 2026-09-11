from __future__ import annotations

import json
import shutil
from pathlib import Path

from cydra.foundry import classify_initialization_outcome, generate_initialization_test, run_foundry_test
from cydra.pipeline import investigate

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "benchmarks" / "wormhole_uninitialized"
FOUNDRY = BENCH / "foundry"


def prepare(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def main() -> int:
    vulnerable_source = BENCH / "Target.sol"
    patched_source = BENCH / "PatchedTarget.sol"
    result = investigate(vulnerable_source, target="benchmark-002")
    hypotheses = [h for h in result.hypotheses if h.invariant_id == "INV-INIT-001"]
    if len(hypotheses) != 1:
        raise SystemExit(f"expected one initialization hypothesis, got {len(hypotheses)}")
    hypothesis = hypotheses[0]

    prepare(vulnerable_source, FOUNDRY / "Target.sol")
    prepare(patched_source, FOUNDRY / "PatchedTarget.sol")
    vuln_test = FOUNDRY / "test" / "generated" / "H_INIT_initialize_vulnerable.t.sol"
    patched_test = FOUNDRY / "test" / "generated" / "H_INIT_initialize_patched.t.sol"
    generate_initialization_test(hypothesis, "../../Target.sol", "WormholeInitializationFixture", vuln_test)
    generate_initialization_test(hypothesis, "../../PatchedTarget.sol", "WormholeInitializationFixture", patched_test)
    vuln_test.write_text(vuln_test.read_text().replace("CydraInitializationInvariantTest", "CydraInitializationInvariantTestVulnerable"), encoding="utf-8")
    patched_test.write_text(patched_test.read_text().replace("CydraInitializationInvariantTest", "CydraInitializationInvariantTestPatched"), encoding="utf-8")

    vulnerable = run_foundry_test(FOUNDRY, vuln_test, "X-H-INIT-initialize", "vulnerable")
    patched = run_foundry_test(FOUNDRY, patched_test, "X-H-INIT-initialize", "patched")
    outcome = classify_initialization_outcome(hypothesis, vulnerable, patched)
    payload = {
        "benchmark": "002",
        "prediction": "require a new rule but no structural change",
        "invariants": [i.__dict__ for i in result.invariants],
        "hypothesis": outcome.hypothesis.__dict__,
        "vulnerable": {"exit_code": vulnerable.exit_code, "passed": vulnerable.passed, "stdout": vulnerable.stdout, "stderr": vulnerable.stderr},
        "patched": {"exit_code": patched.exit_code, "passed": patched.passed, "stdout": patched.stdout, "stderr": patched.stderr},
        "evidence": [e.__dict__ for e in outcome.evidence],
    }
    print(json.dumps(payload, indent=2))
    return 0 if outcome.hypothesis.status == "confirmed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
