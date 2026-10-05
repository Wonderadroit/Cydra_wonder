from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from cydra.web2_adapter import Web2Adapter, Web2Identity, Web2Target
from cydra.web2_discovery import discover_web2_surface


TARGET = "https://app.aurory.io"
ALLOWED_HOSTS = ("app.aurory.io",)
DEFAULT_BUG_BOUNTY_USERNAME = "cyberwonder"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bounded, read-only CYDRA live discovery for the authorized Aurory target."
    )
    parser.add_argument("--seed", action="append", default=["/"], help="Relative seed path; repeatable.")
    parser.add_argument("--max-paths", type=int, default=20)
    parser.add_argument("--output", default="artifacts/aurory-discovery.json")
    args = parser.parse_args()

    if args.max_paths < 1 or args.max_paths > 50:
        raise SystemExit("--max-paths must be between 1 and 50")

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
    )

    report = {
        "target": TARGET,
        "authorized_execution": True,
        "mode": "authenticated" if token else "anonymous_with_bugcrowd_header",
        "bug_bounty_username": username,
        "max_paths": args.max_paths,
        "discovered_paths": list(result.discovered_paths),
        "endpoints": [
            {
                "endpoint_id": endpoint_id,
                "method": endpoint.method,
                "path": endpoint.path,
            }
            for endpoint_id, endpoint in sorted(result.model.endpoints.items())
        ],
        "observations": [
            {
                "action_id": observation.action_id,
                "status": observation.status.value,
                "error": observation.error,
            }
            for observation in result.observations
        ],
        "note": (
            "Bodies, cookies, authorization values, and response headers are intentionally "
            "excluded from the artifact. The Bugcrowd username is non-secret."
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
