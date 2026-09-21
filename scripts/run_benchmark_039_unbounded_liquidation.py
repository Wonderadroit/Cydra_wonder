from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

from cydra.pipeline import investigate


TARGET_REPO = "https://github.com/sherlock-audit/2023-05-ironbank.git"
TARGET_REF = "20527bc2568ef67ca50c5e3c5fa158ce6bee22a3"
TARGET_PATH = "ib-v2/src/protocol/pool/IronBank.sol"


def clone_target(destination: Path) -> Path:
    completed = subprocess.run(
        ("git", "clone", "--no-tags", "--recurse-submodules", TARGET_REPO, str(destination)),
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError("target clone failed:\n" + completed.stdout[-12000:])
    subprocess.run(
        ("git", "-C", str(destination), "checkout", "--detach", TARGET_REF),
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return destination


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("backtest-artifacts/benchmark-039"))
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="cydra-039-") as tmp:
        target = clone_target(Path(tmp) / "ironbank")
        source = target / TARGET_PATH
        result = investigate(source, target=f"{TARGET_REPO}@{TARGET_REF}:{TARGET_PATH}")

    candidates = [
        hypothesis
        for hypothesis in result.hypotheses
        if hypothesis.invariant_id.startswith("INV-UNBOUNDED-ITERATION-")
    ]
    # Selection itself is performed by the same generic selector used by the
    # research loop. Do not inject the historical function name into selection.
    from cydra.hypothesis_selection import select_next_hypothesis

    selection = select_next_hypothesis(
        result.hypotheses, result.invariants, result.experiments
    )
    hypothesis = selection.hypothesis

    payload = {
        "benchmark": "039",
        "target": {"repo": TARGET_REPO, "ref": TARGET_REF, "path": TARGET_PATH},
        "blind_boundary": {
            "vulnerability_class": False,
            "target_function": False,
            "exploit_sequence": False,
            "historical_answer": False,
            "state_surface": False,
            "selector_override": False,
        },
        "candidate_count": len(result.hypotheses),
        "unbounded_candidates": [
            {
                "hypothesis_id": item.hypothesis_id,
                "target_function": item.target_function,
                "claim": item.claim,
                "potential_impact": item.potential_impact,
            }
            for item in candidates
        ],
        "selected": {
            "hypothesis_id": hypothesis.hypothesis_id,
            "target_function": hypothesis.target_function,
            "score": selection.score,
            "invariant_id": hypothesis.invariant_id,
        },
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "result.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload, indent=2))
    if not candidates:
        raise RuntimeError("generic unbounded-iteration surface produced no hypothesis")
    if hypothesis.invariant_id != candidates[0].invariant_id:
        raise RuntimeError("blind selector did not select the unbounded-iteration surface")
    if hypothesis.target_function != "isUserLiquidatable":
        raise RuntimeError(
            "generic unbounded-iteration reasoning did not bind the public liquidation path: "
            + hypothesis.hypothesis_id
            + " / "
            + hypothesis.target_function
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
