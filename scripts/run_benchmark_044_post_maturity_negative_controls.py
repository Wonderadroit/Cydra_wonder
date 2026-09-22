from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from run_benchmark_043_multi_target_causal_discovery import (
    DEBT_POC,
    RABBIT_POC,
    TARGETS,
    _foundry_remappings,
    _target_solc_version,
    clone,
    evaluate_selection,
    patch_debt,
    patch_rabbit,
    run_blind,
    run_foundry,
)


def _patched_run(
    target: dict,
    output: Path,
    hypothesis_id: str,
    poc: str,
    contract: str,
    test: str,
    patcher,
) -> dict:
    with tempfile.TemporaryDirectory(prefix=f"cydra-044-{target['id']}-") as tmp:
        root = Path(tmp)
        patched = root / "patched"
        clone(target["repo"], target["ref"], patched)

        source = patched / target["source"]
        source.write_text(patcher(source.read_text()))
        (patched / "test").mkdir(parents=True, exist_ok=True)
        (patched / "test" / "Cydra044.t.sol").write_text(poc)

        result = run_foundry(
            patched,
            contract,
            test,
            "patched-negative-control",
            Path(target["source"]),
            Path(target["source"]),
        )

        # Preserve only bounded execution evidence in the campaign artifact.
        bounded = {
            "hypothesis_id": hypothesis_id,
            "status": result["status"],
            "exit_code": result["exit_code"],
            "stdout_tail": result["stdout"][-4000:],
            "stderr_tail": result["stderr"][-4000:],
        }
        (output / "patched-execution.json").write_text(
            json.dumps(bounded, indent=2) + "\n"
        )
        return result


def run_target(target: dict, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)

    # The selection stage remains blind. We do not inject the historical
    # finding into the blind runner. The expected mechanism is used only
    # afterward to bind the already-selected hypothesis to its patched
    # counterfactual control.
    blind = run_blind(target, output / "blind")
    hypotheses = blind.get("hypotheses", [])
    selection = evaluate_selection(target["id"], hypotheses)
    (output / "blind-selection.json").write_text(
        json.dumps(selection, indent=2) + "\n"
    )

    if blind.get("exit_code") != 0 or not selection["matching_hypotheses"]:
        return {
            "status": "BLOCKED",
            "failure_stage": "blind_selection",
            "blind": blind,
            "selection": selection,
            "false_positive": None,
        }

    selected = selection["matching_hypotheses"][0]
    hypothesis_id = selected["hypothesis_id"]

    if target["id"] == "rabbithole":
        result = _patched_run(
            target,
            output,
            hypothesis_id,
            RABBIT_POC,
            "CydraRabbitHole043Test",
            "test_cydra_unauthorized_mint_is_blocked",
            patch_rabbit,
        )
    else:
        result = _patched_run(
            target,
            output,
            hypothesis_id,
            DEBT_POC,
            "CydraDebtDao043Test",
            "test_cydra_invalid_revenue_binding_cannot_capture_push_payment",
            patch_debt,
        )

    # A patched control must not reproduce the vulnerable differential.
    # PASS here means the invariant holds on the safe counterfactual.
    false_positive = result["status"] == "PASS"
    finding_gate = "NOT_READY" if false_positive else "BLOCKED"

    return {
        "status": "PASS" if false_positive else "BLOCKED",
        "blind": {
            "exit_code": blind.get("exit_code"),
            "hypothesis_count": len(hypotheses),
        },
        "selection": {
            "hypothesis_id": hypothesis_id,
            "blind_boundary_preserved": True,
        },
        "patched": {
            "status": result["status"],
            "exit_code": result["exit_code"],
        },
        "false_positive": false_positive,
        "finding_gate": finding_gate,
        "causal_verification": False,
        "independent_reproduction": "NOT_APPLICABLE",
        "blind_boundary_preserved": True,
    }


def main() -> int:
    output = Path("backtest-artifacts/benchmark-044")
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    results = {
        target["id"]: run_target(target, output / target["id"])
        for target in TARGETS
    }

    passed = all(item["status"] == "PASS" for item in results.values())
    result = {
        "status": "PASS" if passed else "NOT_CONFIRMED",
        "campaign": "post-maturity-negative-controls",
        "targets_total": len(results),
        "targets_passed": sum(item["status"] == "PASS" for item in results.values()),
        "false_positive_controls_passed": all(
            item.get("false_positive") is True for item in results.values()
        ),
        "no_ready_findings": all(
            item.get("finding_gate") == "NOT_READY" for item in results.values()
        ),
        "causal_verification_expected": False,
        "targets": results,
        "blind_boundary_preserved": all(
            item.get("blind_boundary_preserved", True) for item in results.values()
        ),
    }
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
