from __future__ import annotations

import json
import sys
from pathlib import Path

from cydra.pipeline import investigate

TARGET_COMMIT = "58bed220236e8cdd8d279ef7259b3298a71aac0b"
TARGET_REPOSITORY = "Jc-asastu/liquidclaw-bsc"
SCOPE = (
    "contracts/Pool.sol",
    "contracts/Router.sol",
    "contracts/factories/FactoryRegistry.sol",
    "contracts/VotingEscrow.sol",
    "contracts/Minter.sol",
    "contracts/RewardsDistributor.sol",
    "contracts/Voter.sol",
    "contracts/ProtocolGovernor.sol",
)
EXPECTED_INITIALIZATION = {
    "contracts/Pool.sol": 1,
    "contracts/Router.sol": 0,
    "contracts/factories/FactoryRegistry.sol": 0,
    "contracts/VotingEscrow.sol": 0,
    "contracts/Minter.sol": 1,
    "contracts/RewardsDistributor.sol": 0,
    "contracts/Voter.sol": 1,
    "contracts/ProtocolGovernor.sol": 0,
}


def serialize(result):
    return {
        "target": result.target,
        "contracts": [
            {
                "name": contract.name,
                "source": contract.source,
                "functions": [
                    {
                        "name": fn.name,
                        "visibility": fn.visibility,
                        "modifiers": list(fn.modifiers),
                        "writes": list(fn.writes),
                        "external_calls": list(fn.external_calls),
                        "line": fn.line,
                    }
                    for fn in contract.functions
                ],
            }
            for contract in result.contracts
        ],
        "invariants": [
            {
                "invariant_id": item.invariant_id,
                "statement": item.statement,
                "provenance": item.provenance,
                "confidence": item.confidence,
            }
            for item in result.invariants
        ],
        "hypotheses": [
            {
                "hypothesis_id": item.hypothesis_id,
                "claim": item.claim,
                "invariant_id": item.invariant_id,
                "target_function": item.target_function,
                "attacker_capability": item.attacker_capability,
                "expected_impact": item.expected_impact,
                "status": item.status,
                "evidence_ids": list(item.evidence_ids),
            }
            for item in result.hypotheses
        ],
        "experiments": [
            {
                "experiment_id": item.experiment_id,
                "hypothesis_id": item.hypothesis_id,
                "action": item.action,
                "discriminates": list(item.discriminates),
                "cost": item.cost,
            }
            for item in result.experiments
        ],
        "evidence": [
            {
                "evidence_id": item.evidence_id,
                "kind": item.kind,
                "claim": item.claim,
                "source": item.source,
                "location": item.location,
                "payload": item.payload,
                "source_verification": item.source_verification,
            }
            for item in result.evidence
        ],
    }


def main() -> int:
    target_root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path("/tmp/liquidclaw").resolve()
    if not target_root.is_dir():
        raise SystemExit(f"Target checkout missing: {target_root}")

    records = []
    scope_set = set(SCOPE)
    for relative_path in SCOPE:
        path = target_root / relative_path
        record = {
            "path": relative_path,
            "expected_initialization_hypotheses": EXPECTED_INITIALIZATION[relative_path],
        }
        if not path.is_file():
            record.update({"status": "PARSE_FAILED", "error": "declared scope file missing"})
            records.append(record)
            continue
        try:
            result = investigate(
                path,
                target=f"{TARGET_REPOSITORY}@{TARGET_COMMIT}:{relative_path}",
            )
            payload = serialize(result)
            hypothesis_sources = {
                item["source"] for item in payload["evidence"]
            }
            scope_violation = any(
                source.startswith(str(target_root))
                and str(Path(source).resolve().relative_to(target_root)) not in scope_set
                for source in hypothesis_sources
            )
            record.update(
                {
                    "status": "PARSED",
                    "result": payload,
                    "scope_violation": scope_violation,
                    "initialization_hypothesis_count": sum(
                        item["invariant_id"] == "INV-INIT-001"
                        for item in payload["hypotheses"]
                    ),
                    "hypothesis_count": len(payload["hypotheses"]),
                    "experiment_count": len(payload["experiments"]),
                }
            )
        except Exception as exc:  # benchmark records the pipeline failure; it does not repair it
            record.update({"status": "PARSE_OR_PIPELINE_FAILED", "error": repr(exc)})
        records.append(record)

    all_hypotheses = [
        hypothesis
        for record in records
        if record.get("status") == "PARSED"
        for hypothesis in record["result"]["hypotheses"]
    ]
    all_experiments = [
        experiment
        for record in records
        if record.get("status") == "PARSED"
        for experiment in record["result"]["experiments"]
    ]
    output = {
        "benchmark": "005_liquidclaw_blind_discovery",
        "target_repository": TARGET_REPOSITORY,
        "target_commit": TARGET_COMMIT,
        "declared_scope": list(SCOPE),
        "source_of_truth": "frozen target source executed through existing CYDRA pipeline",
        "records": records,
        "summary": {
            "contracts_declared": len(SCOPE),
            "contracts_parsed": sum(r.get("status") == "PARSED" for r in records),
            "contracts_failed": sum(r.get("status") != "PARSED" for r in records),
            "initialization_hypotheses": sum(
                item["invariant_id"] == "INV-INIT-001" for item in all_hypotheses
            ),
            "authorization_hypotheses": sum(
                item["invariant_id"] == "INV-AUTH-001" for item in all_hypotheses
            ),
            "arithmetic_hypotheses": sum(
                item["invariant_id"] == "INV-ARITH-001" for item in all_hypotheses
            ),
            "accounting_hypotheses": sum(
                item["invariant_id"] == "INV-ACCOUNT-001" for item in all_hypotheses
            ),
            "total_hypotheses": len(all_hypotheses),
            "total_experiments": len(all_experiments),
            "scope_violations": sum(r.get("scope_violation", False) for r in records),
        },
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
