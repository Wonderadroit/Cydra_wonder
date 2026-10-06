from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from cydra.web2_adapter import Web2Adapter, Web2Identity, Web2Target
from cydra.web2_discovery import discover_web2_surface
from cydra.web2_reasoning import generate_web2_hypotheses_from_discovery


TARGET = "https://app.aurory.io"
ALLOWED_HOSTS = ("app.aurory.io",)
DEFAULT_BUG_BOUNTY_USERNAME = "cyberwonder"



def _safe_observation_record(observation) -> dict[str, object]:
    """Serialize non-secret HTTP observation metadata for downstream modeling.

    The adapter already computes response metadata; preserve only fields that
    are useful for planning/differential reasoning without copying response
    bodies, cookies, credentials, or headers into the artifact.
    """
    record: dict[str, object] = {
        "action_id": observation.action_id,
        "status": observation.status.value,
        "error": observation.error,
    }
    payload = observation.value
    if observation.status.value != "executed" or not isinstance(payload, dict):
        return record

    body = payload.get("body")
    record.update(
        {
            "method": payload.get("method"),
            "path": payload.get("url"),
            "final_url": payload.get("final_url"),
            "identity_id": payload.get("identity_id"),
            "status_code": payload.get("status_code"),
            "body_length": len(body.encode("utf-8")) if isinstance(body, str) else None,
            "body_sha256": payload.get("body_sha256"),
        }
    )
    return record


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bounded, read-only CYDRA live discovery for the authorized Aurory target."
    )
    parser.add_argument("--seed", action="append", default=["/"], help="Relative seed path; repeatable.")
    parser.add_argument("--max-paths", type=int, default=20)
    parser.add_argument("--max-js-bundles", type=int, default=16)
    parser.add_argument("--output", default="artifacts/aurory-discovery.json")
    args = parser.parse_args()

    if args.max_paths < 1 or args.max_paths > 50:
        raise SystemExit("--max-paths must be between 1 and 50")
    if args.max_js_bundles < 0 or args.max_js_bundles > args.max_paths:
        raise SystemExit("--max-js-bundles must be between 0 and max-paths")

    username = os.environ.get("AURORY_BUG_BOUNTY_USERNAME", DEFAULT_BUG_BOUNTY_USERNAME).strip()
    if not username or any(char.isspace() for char in username):
        raise SystemExit("AURORY_BUG_BOUNTY_USERNAME must be a non-empty single username")

    # The Bugcrowd identifier is a public testing header, not an authentication
    # credential. Keep it separate from the optional authenticated session.
    identity_headers = {"X-Bug-Bounty": f"Bugcrowd-{username}"}
    token = os.environ.get("AURORY_OWNER_AUTHORIZATION", "").strip()
    if token:
        identity_headers["Authorization"] = token

    identity_id = "owner"
    identities = {
        identity_id: Web2Identity(identity_id, identity_headers),
    }

    adapter = Web2Adapter(
        Web2Target(
            base_url=TARGET,
            allowed_hosts=ALLOWED_HOSTS,
            authorized=True,
            timeout_seconds=15.0,
        ),
        identities=identities,
    )

    result = discover_web2_surface(
        adapter,
        target=TARGET,
        seeds=args.seed,
        identity_id=identity_id,
        max_paths=args.max_paths,
        max_js_bundles=args.max_js_bundles,
    )

    hypothesis_planning = generate_web2_hypotheses_from_discovery(result)
    report = {
        "model": {
            "identities": [
                {"identity_id": identity.identity_id, "label": identity.label, "authenticated": identity.authenticated}
                for identity in sorted(result.model.identities.values(), key=lambda item: item.identity_id)
            ],
            "resources": [
                {"resource_id": resource.resource_id, "label": resource.label, "owner_identity_id": resource.owner_identity_id, "identifier": resource.identifier}
                for resource in sorted(result.model.resources.values(), key=lambda item: item.resource_id)
            ],
        },
        "resource_provenance": [
            {"resource_id": item.resource_id, "identifier": item.identifier, "source_endpoint_id": item.source_endpoint_id, "source_observation_id": item.source_observation_id, "field_path": item.field_path}
            for item in result.resource_provenance
        ],
        "materialization_plans": [
            {
                "endpoint_id": plan.endpoint_id, "template": plan.template,
                "requirements": [{"parameter": requirement.parameter, "resource_id": requirement.resource_id} for requirement in plan.requirements],
                "materialized_path": plan.materialized_path, "executable": plan.executable,
            }
            for plan in result.materialization_plans
        ],
        "service_origin_relations": [
            {"source": relation.source, "origin": relation.origin, "relation": relation.relation, "authorized_for_execution": relation.authorized_for_execution}
            for relation in result.service_origin_relations
        ],
        "hypothesis_planning": {
            "plan_count": len(hypothesis_planning.plans),
            "plans": [
                {"hypothesis_id": plan.hypothesis.hypothesis_id, "statement": plan.hypothesis.statement, "target_function": plan.hypothesis.target_function, "expected_impact": plan.hypothesis.expected_impact}
                for plan in hypothesis_planning.plans
            ],
            "capability_gaps": list(hypothesis_planning.capability_gaps),
        },
    },
    report = {        "target": TARGET,
        "authorized_execution": True,
        "mode": "authenticated" if token else "anonymous_with_bugcrowd_header",
        "bug_bounty_username": username,
        "max_paths": args.max_paths,
        "max_js_bundles": args.max_js_bundles,
        "discovered_paths": list(result.discovered_paths),
        "bundle_analyses": [
            {
                "path": bundle.path,
                "classification": bundle.classification,
                "base_urls": list(bundle.base_urls),
                "service_origins": list(bundle.service_origins),
                "unauthorized_origins": list(bundle.unauthorized_origins),
                "request_methods": list(bundle.request_methods),
                "endpoint_candidates": list(bundle.endpoint_candidates),
                "unresolved_request_templates": list(bundle.unresolved_request_templates),
            }
            for bundle in result.bundle_analyses
        ],
        "endpoints": [
            {
                "endpoint_id": endpoint_id,
                "method": endpoint.method,
                "path": endpoint.path,
            }
            for endpoint_id, endpoint in sorted(result.model.endpoints.items())
        ],
        "observations": [
            _safe_observation_record(observation)
            for observation in result.observations
        ],
        "note": (
            "Response bodies, cookies, authorization values, and response headers are intentionally "
            "excluded from the artifact. Safe observation metadata includes request/final URL, "
            "HTTP method/status, body length, and body SHA-256 so downstream reasoning can compare "
            "responses without retaining response content. The Bugcrowd username is non-secret."
        ),
    }

    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "target": TARGET,
                "mode": report["mode"],
                "discovered_count": len(result.discovered_paths),
                "executed_count": sum(
                    o.status.value == "executed" for o in result.observations
                ),
                "artifact": str(destination),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
