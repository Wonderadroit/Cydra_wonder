from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from cydra.canonical_cycle import run_canonical_differential_cycle
from cydra.foundry import require_executed, run_foundry_test, test_path_for
from cydra.finding_gate import FindingCandidate, evaluate_finding_graph
from cydra.hypotheses import Hypothesis as CanonicalHypothesis
from cydra.impact import ImpactAssessment, ImpactLevel
from cydra.models import Experiment
from cydra.pipeline import investigate
from cydra.solidity_model import parse_solidity
from cydra.structural_double_debit import generate_double_debit_hypotheses
from cydra.system_model import Edge, Node, SystemModel

TARGET_REPO = "https://github.com/sherlock-audit/2024-02-tapioca.git"
TARGET_REF = "main"
TARGET_SOURCE = "Tapioca-bar/contracts/markets/bigBang/BBLeverage.sol"


def _clone(root: Path) -> Path:
    checkout = root / "target"
    subprocess.run(["git", "clone", "--quiet", "--no-tags", "--no-checkout", TARGET_REPO, str(checkout)], check=True)
    subprocess.run(["git", "-C", str(checkout), "checkout", "--quiet", TARGET_REF], check=True)
    source = checkout / TARGET_SOURCE
    if not source.exists():
        raise RuntimeError("historical target source missing")
    return source


def _write_harness(target: Path, root: Path, patched: bool) -> Path:
    source = target.read_text(encoding="utf-8")
    required = (
        "function buyCollateral",
        "_borrow(",
        "leverageExecutor.getCollateral",
        "_addCollateral(",
    )
    missing = [x for x in required if x not in source]
    common_source = target.parent / "BBLendingCommon.sol"
    common_base_source = target.parent / "BBCommon.sol"
    common_text = (
        (common_source.read_text(encoding="utf-8") if common_source.exists() else "")
        + (common_base_source.read_text(encoding="utf-8") if common_base_source.exists() else "")
    )
    if "_addTokens(" not in common_text:
        missing.append("BBCommon._addTokens")
    if missing:
        raise RuntimeError(f"target mechanism anchors missing: {missing}")

